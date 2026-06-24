from __future__ import annotations

import json
import os
import sqlite3
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Literal

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field, ValidationError

from agent.storage import database_path, project_root
from data.ingest import query_knowledge_base as ingest_query_knowledge_base


ORDER_FIXTURES = {
    "ORD123": {"status": "processing", "eta": "2026-06-26"},
    "ORD124": {"status": "shipped", "eta": "2026-06-24"},
    "ORD125": {"status": "delivered", "eta": "2026-06-22"},
}
MIN_KB_SIMILARITY = 0.45
CLASSIFIER_MODEL = "gemini-2.5-flash-lite"
CURRENT_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)


class CheckOrderStatusInput(BaseModel):
    order_id: str = Field(pattern=r"^ORD\d+$")


class CreateTicketInput(BaseModel):
    issue: str = Field(min_length=5)
    priority: Literal["low", "medium", "high"]


class EscalateInput(BaseModel):
    reason: str = Field(min_length=5)


class TicketSeverityClassification(BaseModel):
    severity: Literal["low", "medium", "high"]
    category: str
    reasoning: str


def agent_log_path() -> Path:
    return project_root() / "logs" / "agent_log.jsonl"


def usage_log_path() -> Path:
    return project_root() / "logs" / "usage_log.jsonl"


def set_request_id(request_id: str | None) -> object:
    return CURRENT_REQUEST_ID.set(request_id)


def reset_request_id(token: object) -> None:
    CURRENT_REQUEST_ID.reset(token)


def current_request_id() -> str | None:
    return CURRENT_REQUEST_ID.get()


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def initialize_ticket_table() -> None:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue TEXT NOT NULL,
                priority TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
            """
        )


def print_and_log_agent_event(record: dict[str, Any]) -> None:
    print(json.dumps(record, ensure_ascii=False, default=str))
    append_jsonl(agent_log_path(), record)


def validation_error_response(exc: ValidationError) -> dict[str, object]:
    messages = [
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    ]
    return {"error": f"invalid input: {'; '.join(messages)}"}


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
                "event": "tool_call",
                "request_id": current_request_id(),
                "timestamp": timestamp,
                "tool": func.__name__,
                "params": params,
                "output": output,
                "duration_ms": duration_ms,
            }
            if error is not None:
                log_record["error"] = error

            print_and_log_agent_event(log_record)

    return wrapper


def classify_ticket_severity(issue_text: str) -> dict[str, str]:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "severity": "medium",
            "category": "unclassified",
            "reasoning": "classification unavailable: GEMINI_API_KEY is not set",
        }

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=CLASSIFIER_MODEL,
        contents=(
            "Classify this customer support ticket. "
            "Return only the structured JSON requested by the schema.\n\n"
            f"Issue: {issue_text}"
        ),
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TicketSeverityClassification,
        ),
    )

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, TicketSeverityClassification):
        return parsed.model_dump()

    if isinstance(parsed, dict):
        return TicketSeverityClassification.model_validate(parsed).model_dump()

    return TicketSeverityClassification.model_validate_json(response.text).model_dump()


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
    try:
        validated = CheckOrderStatusInput(order_id=normalized_order_id)
    except ValidationError as exc:
        return validation_error_response(exc)

    normalized_order_id = validated.order_id
    record = ORDER_FIXTURES.get(normalized_order_id)

    if record is None:
        return {"order_id": normalized_order_id, "status": "unknown", "eta": None}

    return {"order_id": normalized_order_id, "status": record["status"], "eta": record["eta"]}


@log_tool_call
def create_ticket(issue: str, priority: str) -> dict[str, object]:
    try:
        validated = CreateTicketInput(issue=issue.strip(), priority=priority.lower().strip())
    except ValidationError as exc:
        return validation_error_response(exc)

    try:
        classification = classify_ticket_severity(validated.issue)
    except Exception as exc:
        classification = {
            "severity": validated.priority,
            "category": "unclassified",
            "reasoning": f"classification unavailable: {exc}",
        }

    created_at = datetime.now(timezone.utc).isoformat()
    initialize_ticket_table()
    with sqlite3.connect(database_path()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO tickets (issue, priority, severity, category, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                validated.issue,
                validated.priority,
                classification["severity"],
                classification["category"],
                created_at,
            ),
        )
        ticket_id = cursor.lastrowid

    ticket = {
        "id": ticket_id,
        "issue": validated.issue,
        "priority": validated.priority,
        "severity": classification["severity"],
        "category": classification["category"],
        "classification_reasoning": classification["reasoning"],
        "status": "open",
        "created_at": created_at,
    }
    return ticket


@log_tool_call
def escalate_to_human(reason: str) -> dict[str, object]:
    try:
        validated = EscalateInput(reason=reason.strip())
    except ValidationError as exc:
        return validation_error_response(exc)

    print(f"ESCALATED request_id={current_request_id()} reason={validated.reason}")
    return {"escalated": True, "reason": validated.reason}


TOOL_MAP = {
    "search_knowledge_base": search_knowledge_base,
    "check_order_status": check_order_status,
    "create_ticket": create_ticket,
    "escalate_to_human": escalate_to_human,
}
