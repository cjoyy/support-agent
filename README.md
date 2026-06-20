---
title: Support Agent
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Support Agent

Customer support agent berbasis FastAPI yang memakai Gemini function calling, ChromaDB retrieval, session memory, guardrails, structured tool logging, dan eval golden set.

## Demo

Deployed URL: 

Swagger UI: 

Screenshot/GIF Swagger UI:

## Architecture Diagram

Flow aplikasi:

1. Client mengirim request ke `POST /chat` dengan `session_id` dan `message`.
2. FastAPI menerima request melalui `main.py`, lalu mengambil conversation history dari `SessionManager`.
3. `SupportAgent` mengirim message + history ke Gemini dengan tool schema function calling.
4. Gemini memilih apakah perlu memanggil tool:
   - `search_knowledge_base` untuk FAQ/support policy.
   - `check_order_status` untuk order ID spesifik.
   - `create_ticket` untuk tracking issue formal.
   - `escalate_to_human` untuk handoff ke agent manusia.
5. Tool handler mengeksekusi logic lokal. Knowledge base memakai Voyage embedding + ChromaDB.
6. Setiap tool call dicatat ke stdout dan `logs/agent_log.jsonl`.
7. Agent mengirim tool result kembali ke Gemini jika perlu, lalu mengembalikan final response ke client.
8. History disimpan kembali per session ID untuk multi-turn conversation.

## Tech Stack

- FastAPI: dipilih untuk API sederhana, typed request/response via Pydantic, dan Swagger UI otomatis. Aplikasi agent core tetap ringan tanpa framework agent besar agar flow function calling mudah di-debug.
- Google Gemini (`google-generativeai`): dipakai karena mendukung function calling, cepat untuk support flow, dan punya free tier yang cocok untuk prototype.
- ChromaDB: vector database lokal yang praktis untuk RAG kecil/menengah tanpa perlu managed service.
- VoyageAI embeddings: dipakai untuk embedding knowledge base dengan kualitas retrieval yang baik.
- In-memory session store: cukup untuk prototype dan local demo; lebih sederhana daripada Redis/database.
- JSONL structured logging: mudah dianalisis, bisa diproses ulang untuk eval, debugging, dan observability awal.
- Docker: memudahkan deploy ke Hugging Face Spaces sebagai Docker Space dan menjaga runtime konsisten.

## Run Lokal

Siapkan `.env`:

```env
GEMINI_API_KEY=...
VOYAGE_API_KEY=...
```

Build image:

```bash
docker build -t support-agent .
```

Run container:

```bash
docker run -p 8000:8000 --env-file .env support-agent
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Chat request:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo-1","message":"Status order ORD123?"}'
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## Hugging Face Spaces Deploy

Rencana deploy: Hugging Face Spaces dengan SDK `Docker`.

Langkah ringkas:

1. Buat Space baru di Hugging Face.
2. Pilih SDK `Docker`.
3. Push repo ini ke Space.
4. Tambahkan secrets:
   - `GEMINI_API_KEY`
   - `VOYAGE_API_KEY`
5. Pastikan Space expose port `8000` lewat CMD di `Dockerfile`.

Catatan: `.env`, `.venv`, `logs`, dan `chroma_db` tidak ikut masuk image karena sudah diatur di `.dockerignore`. Jika knowledge base Chroma perlu tersedia di deploy, ada dua pilihan:

1. Build ulang index saat startup/deploy.
2. Commit artefak database yang sudah diperkecil, jika ukurannya masih masuk akal.

## Eval Results Summary

Eval dataset ada di `eval/golden_set.json` dengan 20 test case:

- FAQ: 5 case.
- Order status: 4 case.
- Ticket creation: 3 case.
- Escalation: 3 case.
- Out-of-scope guardrail: 3 case.
- Multi-turn edge case: 2 case.

Cara menjalankan eval:

```bash
python eval/run_eval.py
```

Smoke test:

```bash
python eval/run_eval.py --limit 3
```

Current result: eval belum menghasilkan accuracy final karena run terakhir terblokir quota Gemini free tier sebelum tool call pertama. File `eval/results.json` menyimpan hasil parsial dengan error `429 quota exceeded`.

Target setelah quota/API key siap: tool-selection accuracy minimal 80%+. Contoh kasus yang ditangani oleh golden set:

- Pertanyaan refund umum harus memanggil `search_knowledge_base`.
- `Status order ORD123?` harus memanggil `check_order_status`.
- Permintaan “buatkan tiket” harus memanggil `create_ticket`.
- Permintaan bicara dengan manusia harus memanggil `escalate_to_human`.
- Pertanyaan di luar customer support harus ditolak sopan tanpa tool call.

## Limitations & Next Steps

- Session masih in-memory, jadi hilang saat server restart dan belum cocok untuk multi-replica deployment.
- Quota Gemini free tier bisa cepat habis saat eval atau demo intensif.
- ChromaDB lokal perlu strategi deploy yang lebih jelas untuk Hugging Face Spaces: rebuild index, commit artefak kecil, atau pindah ke vector DB managed.
- Eval saat ini mengecek tool selection dan refusal keyword, belum menilai kualitas jawaban secara semantik.
- Logging sudah JSONL lokal, tetapi belum ada dashboard/trace viewer.
- Error handling API masih sederhana; production API perlu response code yang lebih rapi untuk quota, missing env, dan dependency failure.

Next steps:

- Tambahkan persistent session store seperti Redis atau SQLite.
- Tambahkan startup job untuk memastikan Chroma collection tersedia.
- Tambahkan CI yang menjalankan lint, compile, dan eval smoke test.
- Tambahkan screenshot/GIF Swagger UI setelah Space deploy.
- Tambahkan streaming response untuk UX chat yang lebih nyaman.
- Tambahkan offline/mock eval mode agar tool-selection bisa dites tanpa menghabiskan quota LLM.
