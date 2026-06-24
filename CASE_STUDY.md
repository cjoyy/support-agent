# Case Study: Customer Support Agent

## Problem

This project simulates a customer support workflow where one assistant needs to answer FAQ-style questions, check known order IDs, create follow-up tickets, and escalate uncertain or frustrated cases to a human agent. The interesting part is not only answering text. The system also has to decide when to retrieve policy information, when to call a deterministic local tool, when to refuse out-of-scope requests, and when to stop trying to answer and hand off.

An agentic approach is useful here because the flow is conditional. A rule-based chatbot can cover a few keywords, but it becomes brittle when the user phrases the same intent in many ways or when multiple steps are needed in one conversation. The agent loop lets the model interpret intent, choose tools, use fresh tool results, and keep conversation history while still being constrained by guardrails and explicit tool schemas.

## Design Decisions & Trade-offs

### Kenapa no-framework (bukan LangChain)

I kept the agent loop framework-free on purpose. That meant writing more manual code for provider calls, tool dispatch, logging, retries, and conversation history, but it also made every step visible. For a portfolio project, that visibility matters: if a tool is not called, if a provider returns malformed content, or if a fallback path is used, the code path is easy to inspect without digging through framework abstractions.

The trade-off is that the project owns more glue code. A mature framework would provide built-in chains, memory primitives, callbacks, and integrations. For this scale, I preferred explicit control because debugging production issues usually starts with the question, "What exactly happened on this request?"

### Kenapa Gemini (bukan Claude/OpenAI)

Gemini was a practical fit because it supports function calling and has a free tier that is approachable for a portfolio deployment. It allowed the project to demonstrate real provider integration without requiring paid infrastructure from day one.

The cost is quota pressure. The recorded eval run hit Gemini free-tier rate limits before completing the full dataset, which is exactly the kind of failure mode a demo app needs to handle. To reduce blast radius, the agent has a circuit breaker and a fallback provider path through Groq so provider failures do not have to take down the whole support flow.

### Kenapa ChromaDB (bukan vector DB managed seperti Pinecone)

ChromaDB keeps the RAG layer local and simple. It is a good match for a small FAQ knowledge base because setup is lightweight, development is fast, and the entire retrieval pipeline can run without provisioning a managed vector database.

The trade-off is scalability and operations. For production scale, a managed vector database would give better durability, monitoring, replication, and query performance controls. ChromaDB is enough for this demo, but it would need a clearer deployment and persistence strategy before becoming the main retrieval store for a larger support product.

### Kenapa SQLite (bukan Postgres)

SQLite is the smallest useful persistence step beyond in-memory dictionaries and JSON files. It lets sessions and tickets survive process restarts, works inside Docker with a mounted volume, and does not add another service to run locally.

The trade-off is concurrent write capacity and multi-instance deployment. SQLite is fine for a single small container, but it is not the database I would choose for many replicas or high write throughput. For production, Postgres with connection pooling would be the natural upgrade.

## What I'd Do Differently for Production Scale

- Replace SQLite with Postgres and connection pooling, plus migrations for schema changes.
- Add authentication, per-user rate limiting, and request quotas so the public demo cannot be abused.
- Use OpenTelemetry for distributed tracing instead of relying only on manual JSONL logs.
- Move RAG to a managed vector database or a hosted search stack with backups and operational metrics.
- Add an offline eval mode with mocked providers so CI can test tool-selection behavior without spending LLM quota.
- Add streaming responses and clearer error responses for quota, missing secrets, and provider outages.

## Results

- Tool-call accuracy: last recorded eval was `0/1` because Gemini returned a `429 quota exceeded` error before any tool call. The repo contains a 20-case golden set covering FAQ, order status, ticket creation, escalation, out-of-scope refusal, and multi-turn cases.
- Avg latency: `6.59s` across the two recorded trace entries in `logs/agent_log.jsonl` (`10.44s` and `2.75s`).
- Cost per conversation: `0.0000729 USD` for the recorded successful Gemini trace in `logs/usage_log.jsonl`; one fallback/error trace recorded `0.0 USD` token cost.
- Test coverage: 13 automated tests pass locally with `pytest tests -v`. No line-coverage percentage is configured yet.

## What I Learned

The hardest part was making the agent feel flexible without letting it become vague. It is tempting to let the model "figure it out," but a support agent needs crisp boundaries: use the knowledge base for policy, use deterministic tools for orders and tickets, refuse unrelated requests, and escalate when the system does not know enough.

I also learned that reliability work shows up earlier than expected. Even in a small demo, quota limits, persistence, fallback behavior, and observability became real concerns. The most useful engineering choice was keeping the loop explicit. It made the system less magical, and that made it much easier to explain, test, and debug.
