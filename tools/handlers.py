from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from data.ingest import query_knowledge_base as ingest_query_knowledge_base


ORDER_FIXTURES = {
    "ORD123": {"status": "processing", "eta": "2026-06-26"},
    "ORD124": {"status": "shipped", "eta": "2026-06-24"},
    "ORD125": {"status": "delivered", "eta": "2026-06-22"},
}


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def tickets_path() -> Path:
    return project_root() / "tickets.json"


def search_knowledge_base(query: str) -> dict[str, object]:
    matches = ingest_query_knowledge_base(query, top_k=3)
    return {"query": query, "matches": matches}


def check_order_status(order_id: str) -> dict[str, object]:
    normalized_order_id = order_id.strip().upper()
    record = ORDER_FIXTURES.get(normalized_order_id)

    if record is None:
        return {"order_id": normalized_order_id, "status": "unknown", "eta": None}

    return {"order_id": normalized_order_id, "status": record["status"], "eta": record["eta"]}


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


def escalate_to_human(reason: str) -> dict[str, object]:
    print(f"ESCALATED: {reason}")
    return {"escalated": True, "reason": reason}


TOOL_MAP = {
    "search_knowledge_base": search_knowledge_base,
    "check_order_status": check_order_status,
    "create_ticket": create_ticket,
    "escalate_to_human": escalate_to_human,
}
