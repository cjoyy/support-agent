from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from agent.session import SessionManager


def test_session_history_persists_across_manager_instances(tmp_path):
    db_path = tmp_path / "sessions.db"
    first_manager = SessionManager(db_path=db_path)

    history = first_manager.get_history("session-1")
    history.append({"role": "user", "content": "hello"})

    second_manager = SessionManager(db_path=db_path)

    assert second_manager.get_history("session-1") == [{"role": "user", "content": "hello"}]


def test_append_message_and_clear_session_use_sqlite(tmp_path):
    db_path = tmp_path / "sessions.db"
    manager = SessionManager(db_path=db_path)

    manager.append_message("session-1", {"role": "assistant", "content": "hi"})
    assert manager.get_history("session-1") == [{"role": "assistant", "content": "hi"}]

    manager.clear_session("session-1")

    assert manager.get_history("session-1") == []


def test_expired_sessions_are_removed(tmp_path):
    db_path = tmp_path / "sessions.db"
    manager = SessionManager(ttl_seconds=30 * 60, db_path=db_path)
    expired_at = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO sessions (session_id, history, last_active) VALUES (?, ?, ?)",
            ("expired", "[]", expired_at),
        )

    manager.get_history("active")

    with sqlite3.connect(db_path) as connection:
        session_ids = [
            row[0]
            for row in connection.execute("SELECT session_id FROM sessions ORDER BY session_id")
        ]

    assert session_ids == ["active"]
