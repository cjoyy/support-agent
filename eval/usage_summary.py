from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


AGENT_LOG_PATH = PROJECT_ROOT / "logs" / "agent_log.jsonl"
USAGE_LOG_PATH = PROJECT_ROOT / "logs" / "usage_log.jsonl"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def average(records: list[dict[str, Any]], key: str) -> float:
    values = [float(record[key]) for record in records if record.get(key) is not None]
    return round(mean(values), 2) if values else 0.0


def compute_p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = min(int(len(sorted_values) * 0.95), len(sorted_values) - 1)
    return round(sorted_values[idx], 2)


def main() -> None:
    usage_records = read_jsonl(USAGE_LOG_PATH)
    agent_records = read_jsonl(AGENT_LOG_PATH)

    latency_records = [
        record
        for record in agent_records
        if record.get("event") == "latency_breakdown"
    ]
    tool_records = [
        record
        for record in agent_records
        if record.get("event") == "tool_call" or record.get("tool")
    ]

    request_ids = {
        record.get("request_id")
        for record in usage_records
        if record.get("request_id")
    }
    total_cost = sum(float(record.get("estimated_cost_usd") or 0.0) for record in usage_records)

    successful_tool_calls = [
        record
        for record in tool_records
        if not isinstance(record.get("output"), dict) or "error" not in record["output"]
    ]
    tool_success_rate = (
        round((len(successful_tool_calls) / len(tool_records)) * 100, 2)
        if tool_records
        else 0.0
    )

    # Per-tool success rate
    per_tool_total: dict[str, int] = defaultdict(int)
    per_tool_ok: dict[str, int] = defaultdict(int)
    for record in tool_records:
        tool_name = record.get("tool", "unknown")
        per_tool_total[tool_name] += 1
        if not isinstance(record.get("output"), dict) or "error" not in record["output"]:
            per_tool_ok[tool_name] += 1

    # P95 latency from latency_breakdown events
    all_total_latencies = [
        float(r["total_time_ms"])
        for r in latency_records
        if r.get("total_time_ms") is not None
    ]
    p95_total_latency_ms = compute_p95(all_total_latencies)

    all_llm_latencies = [
        float(r["llm_time_ms"])
        for r in latency_records
        if r.get("llm_time_ms") is not None
    ]
    p95_llm_latency_ms = compute_p95(all_llm_latencies)

    print("=== Usage Summary ===")
    print(f"Total request: {len(request_ids) or len(usage_records)}")
    print(f"Total cost USD: ${total_cost:.10f}")
    print(f"Avg retrieval latency: {average(latency_records, 'retrieval_time_ms')} ms")
    print(f"Avg LLM latency: {average(latency_records, 'llm_time_ms')} ms")
    print(f"Avg total latency: {average(latency_records, 'total_time_ms')} ms")
    print(f"P95 LLM latency: {p95_llm_latency_ms} ms")
    print(f"P95 total latency: {p95_total_latency_ms} ms")
    print(f"Tool-call success rate: {tool_success_rate}% ({len(successful_tool_calls)}/{len(tool_records)})")
    print("Per-tool success rate:")
    for tool_name in sorted(per_tool_total):
        ok = per_tool_ok[tool_name]
        tot = per_tool_total[tool_name]
        rate = round((ok / tot) * 100, 2) if tot else 0.0
        print(f"  {tool_name}: {rate}% ({ok}/{tot})")


if __name__ == "__main__":
    main()
