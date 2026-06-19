from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from data.ingest import query_knowledge_base as ingest_query_knowledge_base


ORDER_FIXTURES = {
    "ORD123": {"status": "processing", "eta": "2026-06-26"},
    "ORD124": {"status": "shipped", "eta": "2026-06-24"},
    "ORD125": {"status": "delivered", "eta": "2026-06-22"},
}
MIN_KB_SIMILARITY = 0.45


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def tickets_path() -> Path:
    return project_root() / "tickets.json"


def agent_log_path() -> Path:
    return project_root() / "logs" / "agent_log.jsonl"


def log_tool_call(func: Callable[..., dict[str, object]]) -> Callable[..., dict[str, object]]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, object]:
        started_at = time.perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat()
        params = {"args": args, "kwargs": kwargs}
        output: dict[str, object]
        error: str | None = None

        try:
            output = func(*args, **kwargs)
            return output
        except Exception as exc:
            error = str(exc)
            output = {"error": error}
            raise
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            log_record = {
                "timestamp": timestamp,
                "tool": func.__name__,
                "params": params,
                "output": output,
                "duration_ms": duration_ms,
            }
            if error is not None:
                log_record["error"] = error

            print(json.dumps(log_record, ensure_ascii=False, default=str))

            path = agent_log_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(log_record, ensure_ascii=False, default=str) + "\n")

    return wrapper


@log_tool_call
def search_knowledge_base(query: str) -> dict[str, object]:
    matches = ingest_query_knowledge_base(query, top_k=3)
    matches = [
        match
        for match in matches
        if float(match.get("similarity", 0.0)) >= MIN_KB_SIMILARITY
    ]
    return {"query": query, "matches": matches}


@log_tool_call
def check_order_status(order_id: str) -> dict[str, object]:
    normalized_order_id = order_id.strip().upper()
    record = ORDER_FIXTURES.get(normalized_order_id)

    if record is None:
        return {"order_id": normalized_order_id, "status": "unknown", "eta": None}

    return {"order_id": normalized_order_id, "status": record["status"], "eta": record["eta"]}


@log_tool_call
def create_ticket(issue: str, priority: str) -> dict[str, object]:
    priority = priority.lower().strip()
    if priority not in {"low", "medium", "high"}:
        raise ValueError("priority must be one of: low, medium, high")

    path = tickets_path()
    if path.exists():
        tickets = json.loads(path.read_text(encoding="utf-8"))
    else:
        tickets = []

    next_id = max((ticket.get("id", 0) for ticket in tickets), default=0) + 1
    ticket = {
        "id": next_id,
        "issue": issue,
        "priority": priority,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    tickets.append(ticket)
    path.write_text(json.dumps(tickets, indent=2, ensure_ascii=False), encoding="utf-8")
    return ticket


@log_tool_call
def escalate_to_human(reason: str) -> dict[str, object]:
    print(f"ESCALATED: {reason}")
    return {"escalated": True, "reason": reason}


TOOL_MAP = {
    "search_knowledge_base": search_knowledge_base,
    "check_order_status": check_order_status,
    "create_ticket": create_ticket,
    "escalate_to_human": escalate_to_human,
}
