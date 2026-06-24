from __future__ import annotations

from unittest.mock import Mock

from fastapi.testclient import TestClient

import main
from agent.session import SessionManager


def test_chat_response_includes_tools_used(monkeypatch, tmp_path):
    fake_agent = Mock()
    fake_agent.chat.return_value = ("Ticket dibuat.", ["create_ticket"])
    monkeypatch.setattr(main, "agent", fake_agent)
    monkeypatch.setattr(main, "session_manager", SessionManager(db_path=tmp_path / "sessions.db"))

    client = TestClient(main.app)
    response = client.post(
        "/chat",
        json={"session_id": "api-test", "message": "buatkan tiket refund"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == "Ticket dibuat."
    assert payload["session_id"] == "api-test"
    assert payload["tools_used"] == ["create_ticket"]


def test_static_root_is_served_without_breaking_api_routes():
    client = TestClient(main.app)

    root_response = client.get("/")
    health_response = client.get("/health")

    assert root_response.status_code == 200
    assert "Support Agent" in root_response.text
    assert health_response.json() == {"status": "ok"}
