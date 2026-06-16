from __future__ import annotations

import argparse
import os
from pathlib import Path

import chromadb
import voyageai
from dotenv import load_dotenv


COLLECTION_NAME = "support_faq"
EMBED_MODEL = "voyage-3-lite"


def distance_to_similarity(distance: float) -> float:
    if distance <= 0:
        return 1.0
    return 1.0 / (1.0 + distance)


def main() -> None:
    parser = argparse.ArgumentParser(description="Query support FAQ chunks stored in ChromaDB.")
    parser.add_argument("--question", default="bagaimana cara refund?", help="Pertanyaan yang akan di-query")
    parser.add_argument("--top-k", type=int, default=3, help="Jumlah hasil teratas yang ditampilkan")
    args = parser.parse_args()

    load_dotenv()

    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY is not set")

    project_root = Path(__file__).resolve().parent.parent
    chroma_dir = project_root / "chroma_db"

    voyage_client = voyageai.Client(api_key=api_key)
    embedding = voyage_client.embed([args.question], model=EMBED_MODEL).embeddings[0]

    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = chroma_client.get_collection(name=COLLECTION_NAME)

    result = collection.query(
        query_embeddings=[embedding],
        n_results=args.top_k,
        include=["documents", "distances", "metadatas"],
    )

    documents = result.get("documents", [[]])[0]
    distances = result.get("distances", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]

    print(f"Pertanyaan: {args.question}")
    print()

    for index, (document, distance, metadata) in enumerate(zip(documents, distances, metadatas), start=1):
        similarity = distance_to_similarity(distance)
        source = metadata.get("source", "unknown") if isinstance(metadata, dict) else "unknown"
        chunk_index = metadata.get("chunk_index", "-") if isinstance(metadata, dict) else "-"
        print(f"#{index} similarity={similarity:.4f} distance={distance:.4f} source={source} chunk={chunk_index}")
        print(document)
        print()


if __name__ == "__main__":
    main()