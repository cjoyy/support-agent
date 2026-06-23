from __future__ import annotations

import json

import pytest

from tools import handlers


@pytest.fixture(autouse=True)
def isolated_files(tmp_path, monkeypatch):
    monkeypatch.setattr(handlers, "tickets_path", lambda: tmp_path / "tickets.json")
    monkeypatch.setattr(handlers, "agent_log_path", lambda: tmp_path / "agent_log.jsonl")


def test_check_order_status_valid_order_has_status():
    result = handlers.check_order_status("ORD123")

    assert result["order_id"] == "ORD123"
    assert "status" in result


def test_check_order_status_unknown_order_returns_unknown_or_error():
    result = handlers.check_order_status("ORD999")

    assert result.get("status") == "unknown" or "error" in result


def test_create_ticket_persists_with_auto_increment(monkeypatch, tmp_path):
    monkeypatch.setattr(
        handlers,
        "classify_ticket_severity",
        lambda issue_text: {
            "severity": "high",
            "category": "damaged_item",
            "reasoning": "item arrived damaged",
        },
    )

    first = handlers.create_ticket("Paket rusak saat diterima", "high")
    second = handlers.create_ticket("Refund belum masuk ke rekening", "medium")

    assert first["id"] == 1
    assert second["id"] == 2
    assert second["severity"] == "high"
    assert second["category"] == "damaged_item"

    stored = json.loads((tmp_path / "tickets.json").read_text(encoding="utf-8"))
    assert [ticket["id"] for ticket in stored] == [1, 2]


def test_escalate_to_human_returns_confirmation():
    result = handlers.escalate_to_human("customer asked for a human agent")

    assert result == {
        "escalated": True,
        "reason": "customer asked for a human agent",
    }


def test_create_ticket_invalid_priority_returns_error_dict_not_crash():
    result = handlers.create_ticket("Need help with refund", "urgent")

    assert "error" in result
    assert result["error"].startswith("invalid input:")
