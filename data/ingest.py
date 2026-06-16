from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import chromadb
import tiktoken
import voyageai
from dotenv import load_dotenv


CHUNK_SIZE = 300
CHUNK_OVERLAP = 50
EMBED_BATCH_SIZE = 64
COLLECTION_NAME = "support_faq"
EMBED_MODEL = "voyage-3-lite"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def chunk_tokens(tokens: list[int], chunk_size: int, overlap: int) -> Iterable[list[int]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between 0 and chunk_size - 1")

    step = chunk_size - overlap
    for start in range(0, len(tokens), step):
        end = start + chunk_size
        chunk = tokens[start:end]
        if not chunk:
            break
        yield chunk
        if end >= len(tokens):
            break


def load_documents(raw_dir: Path) -> list[tuple[Path, str]]:
    documents: list[tuple[Path, str]] = []
    for path in sorted(raw_dir.glob("**/*")):
        if path.suffix.lower() not in {".md", ".txt"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if text:
            documents.append((path, text))
    return documents


def build_chunks(documents: list[tuple[Path, str]], encoding: tiktoken.Encoding) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []

    for doc_index, (path, text) in enumerate(documents):
        token_ids = encoding.encode(text)
        for chunk_index, token_chunk in enumerate(chunk_tokens(token_ids, CHUNK_SIZE, CHUNK_OVERLAP)):
            chunk_text = encoding.decode(token_chunk).strip()
            if not chunk_text:
                continue
            chunks.append(
                {
                    "id": f"{path.stem}-{doc_index}-{chunk_index}",
                    "text": chunk_text,
                    "metadata": {
                        "source": str(path.relative_to(path.parents[1])),
                        "file_name": path.name,
                        "chunk_index": chunk_index,
                        "token_count": len(token_chunk),
                    },
                }
            )

    return chunks


def embed_texts(client: voyageai.Client, texts: list[str]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        response = client.embed(batch, model=EMBED_MODEL)
        embeddings.extend(response.embeddings)
    return embeddings


def distance_to_similarity(distance: float) -> float:
    if distance <= 0:
        return 1.0
    return 1.0 / (1.0 + distance)


def query_knowledge_base(question: str, top_k: int = 3) -> list[dict[str, object]]:
    load_dotenv()

    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY is not set")

    client = voyageai.Client(api_key=api_key)
    embedding = client.embed([question], model=EMBED_MODEL).embeddings[0]

    chroma_client = chromadb.PersistentClient(path=str(project_root() / "chroma_db"))
    collection = chroma_client.get_collection(name=COLLECTION_NAME)

    result = collection.query(
        query_embeddings=[embedding],
        n_results=top_k,
        include=["documents", "distances", "metadatas"],
    )

    documents = result.get("documents", [[]])[0]
    distances = result.get("distances", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]

    matches: list[dict[str, object]] = []
    for document, distance, metadata in zip(documents, distances, metadatas):
        matches.append(
            {
                "text": document,
                "distance": distance,
                "similarity": distance_to_similarity(distance),
                "metadata": metadata,
            }
        )
    return matches


def main() -> None:
    load_dotenv()

    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY is not set")

    root = project_root()
    raw_dir = root / "data" / "raw"
    chroma_dir = root / "chroma_db"

    encoding = tiktoken.get_encoding("cl100k_base")
    documents = load_documents(raw_dir)
    chunks = build_chunks(documents, encoding)

    if not chunks:
        print("Ingested 0 chunks into ChromaDB.")
        return

    voyage_client = voyageai.Client(api_key=api_key)
    texts = [chunk["text"] for chunk in chunks]
    embeddings = embed_texts(voyage_client, texts)

    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

    collection.upsert(
        ids=[chunk["id"] for chunk in chunks],
        documents=texts,
        embeddings=embeddings,
        metadatas=[chunk["metadata"] for chunk in chunks],
    )

    print(f"Ingested {len(chunks)} chunks into ChromaDB.")


if __name__ == "__main__":
    main()
