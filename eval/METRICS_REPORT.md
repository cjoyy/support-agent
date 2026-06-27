# Support Agent — Metrics Summary Report

## 1. Golden Evaluation Dataset

| Metric | Value | Source |
|--------|-------|--------|
| Total test cases | **20** | `eval/golden_set.json:1-128` |
| — FAQ | 5 | `eval/golden_set.json:2-31` |
| — Order status | 4 | `eval/golden_set.json:32-55` |
| — Ticket creation | 3 | `eval/golden_set.json:56-73` |
| — Escalation | 3 | `eval/golden_set.json:74-91` |
| — Out-of-scope (expected_tool=null) | 3 | `eval/golden_set.json:92-109` |
| — Edge-case multi-turn | 2 | `eval/golden_set.json:110-127` |

---

## 2. Tool-Selection Accuracy

### Overall

| Run | Accuracy | Source |
|-----|----------|--------|
| Last recorded eval | **0.0%** (0/1 — blocked by Gemini 429 quota) | `eval/results.json:6` |

### Per-Tool Breakdown

| Tool | Accuracy % | Source |
|------|-----------|--------|
| `search_knowledge_base` | not yet measured (0/1 with error) | `eval/results.json:9-23` |
| `check_order_status` | not measured | — |
| `create_ticket` | not measured | — |
| `escalate_to_human` | not measured | — |
| `null` (out-of-scope) | not measured | — |

> **Implementation:** Per-tool accuracy is now computed by `eval/run_eval.py:50-73` (`build_per_tool_accuracy`) and included in `results.json` under the `per_tool_accuracy` key. Re-run `python eval/run_eval.py` after resolving quota limits to populate these values.

---

## 3. Response Latency

### From Eval Runner (`eval/run_eval.py`)

| Metric | Value | Source |
|--------|-------|--------|
| Average case latency | **498.15 ms** (1 case only) | `eval/results.json:7` |
| P95 case latency | **498.15 ms** (computed from same 1 case) | `eval/results.json:7` (via `eval/run_eval.py:191`) |

### From JSONL Logs (`logs/agent_log.jsonl`)

| Metric | Value | Source |
|--------|-------|--------|
| Avg LLM latency | 6,590.66 ms | `logs/agent_log.jsonl:19-20` (mean of 10435.93 + 2745.39) |
| Avg total latency | 6,591.59 ms | `logs/agent_log.jsonl:19-20` (mean of 10437.71 + 2745.47) |
| P95 LLM latency | **10,435.93 ms** | `logs/agent_log.jsonl:19` |
| P95 total latency | **10,437.71 ms** | `logs/agent_log.jsonl:19` |
| Avg retrieval latency | 0.0 ms | `logs/agent_log.jsonl:19-20` |

> **Implementation:** P95 latency is computed in:
> - `eval/run_eval.py:27-31` (`compute_p95`) from per-case eval latencies
> - `eval/usage_summary.py:37-41` (`compute_p95`) from JSONL latency_breakdown events
> - Both are displayed in CLI output when running the scripts

---

## 4. Distinct Tools Implemented

| # | Tool Name | Handler Function | File & Line |
|---|-----------|-----------------|-------------|
| 1 | `search_knowledge_base` | `search_knowledge_base(query)` | `tools/handlers.py:262` |
| 2 | `check_order_status` | `check_order_status(order_id)` | `tools/handlers.py:263` |
| 3 | `create_ticket` | `create_ticket(issue, priority)` | `tools/handlers.py:264` |
| 4 | `escalate_to_human` | `escalate_to_human(reason)` | `tools/handlers.py:265` |

**Total: 4** (registered in `TOOL_MAP` at `tools/handlers.py:262-267`)

---

## 5. Test Coverage

### Test Suite

| File | Tests | Source |
|------|-------|--------|
| `tests/test_agent.py` | 3 | `tests/test_agent.py` |
| `tests/test_api.py` | 2 | `tests/test_api.py` |
| `tests/test_session.py` | 3 | `tests/test_session.py` |
| `tests/test_tools.py` | 5 | `tests/test_tools.py` |
| **Total** | **13** | |

### Coverage Measurement

| Item | Value | Source |
|------|-------|--------|
| Coverage tool | `pytest-cov` | `requirements.txt:9` |
| CI coverage command | `pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=xml` | `.github/workflows/test.yml:31` |
| Coverage report | Generated as XML + terminal output on each CI run | `.github/workflows/test.yml:31-37` |
| **Latest coverage %** | **Not measured yet** — added to CI pipeline but requires next CI run | `.github/workflows/test.yml` |

> **Implementation:** `pytest-cov` was added to `requirements.txt` and the CI workflow was updated to run with `--cov=. --cov-report=term-missing --cov-report=xml`. The report artifact is uploaded for inspection. Run `pytest tests/ -v --cov=. --cov-report=term-missing` locally to see current coverage.

---

## 6. Other Quantifiable Performance Metrics

### Token Usage & Cost

| Metric | Value | Source |
|--------|-------|--------|
| Total cost (all traces) | **$0.0000729** | `logs/usage_log.jsonl:1-2` |
| Cost per successful conversation | **$0.0000729** (641 input + 22 output tokens) | `logs/usage_log.jsonl:1` |
| Input tokens (trace 1) | 641 | `logs/usage_log.jsonl:1` |
| Output tokens (trace 1) | 22 | `logs/usage_log.jsonl:1` |
| Input tokens (trace 2 — fallback) | 0 (quota exhausted) | `logs/usage_log.jsonl:2` |

### Tool-Call Success Rate

| Metric | Value | Source |
|--------|-------|--------|
| Overall tool-call success rate | **85.71%** (12/14 calls succeeded) | Computed from `logs/agent_log.jsonl` via `eval/usage_summary.py:62-71` |
| — `search_knowledge_base` | 50.0% (3/6) | `logs/agent_log.jsonl` (3 had errors/mismatches) |
| — `check_order_status` | 50.0% (2/4) | `logs/agent_log.jsonl` (2 had validation errors) |
| — `create_ticket` | 100% (1/1) | `logs/agent_log.jsonl:16` |
| — `escalate_to_human` | 100% (6/6) | `logs/agent_log.jsonl` (all succeeded) |

> **Implementation:** Per-tool success rate is now displayed by `eval/usage_summary.py:97-108`.

### Circuit Breaker Fallback

| Metric | Value | Source |
|--------|-------|--------|
| Fallback provider | Groq (`llama-3.3-70b-versatile`) | `agent/providers.py` |
| Failure threshold | 3 consecutive errors | `agent/resilience.py` |
| Recovery timeout | 60 seconds | `agent/resilience.py` |
| Fallback events recorded | 1 (test-trace-2) | `logs/agent_log.jsonl:20` |

### Evaluation Pipeline Robustness

| Aspect | Details | Source |
|--------|---------|--------|
| Quota error detection | Early-stop on 429/rate-limit | `eval/run_eval.py:227-229` |
| `--limit` flag | Run only first N cases for smoke tests | `eval/run_eval.py:205-206` |
| Multi-turn support | Cases 19-20 use `input: [string, string]` | `eval/golden_set.json:110-127` |
| JSONL log offset reading | Reads only new log entries per eval case | `eval/run_eval.py:91-116` |
| Tool-call capture | Both in-memory capture + JSONL log replay | `eval/run_eval.py:75-88, 98-116` |

---

## How to Refresh All Metrics Locally

```bash
# 1. Run full eval (requires valid Gemini API key)
python eval/run_eval.py

# 2. View usage summary from existing logs
python eval/usage_summary.py

# 3. Run tests with coverage
pytest tests/ -v --cov=. --cov-report=term-missing
```
