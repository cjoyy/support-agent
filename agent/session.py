from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent.storage import database_path


class PersistentHistory(list[Any]):
    def __init__(self, manager: "SessionManager", session_id: str, values: list[Any]) -> None:
        super().__init__(values)
        self._manager = manager
        self._session_id = session_id

    def append(self, item: Any) -> None:
        super().append(item)
        self._manager._save_history(self._session_id, list(self))

    def clear(self) -> None:
        super().clear()
        self._manager._save_history(self._session_id, list(self))

    def extend(self, iterable: Any) -> None:
        super().extend(iterable)
        self._manager._save_history(self._session_id, list(self))


class SessionManager:
    def __init__(self, ttl_seconds: int = 30 * 60, db_path: Path | None = None) -> None:
        self.ttl_seconds = ttl_seconds
        self.db_path = db_path or database_path()
        self._initialize_database()

    def get_history(self, session_id: str) -> list[Any]:
        self._cleanup_expired_sessions()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT history FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

            if row is None:
                history: list[Any] = []
                connection.execute(
                    "INSERT INTO sessions (session_id, history, last_active) VALUES (?, ?, ?)",
                    (session_id, json.dumps(history), self._now()),
                )
            else:
                history = json.loads(row["history"])
                connection.execute(
                    "UPDATE sessions SET last_active = ? WHERE session_id = ?",
                    (self._now(), session_id),
                )

        return PersistentHistory(self, session_id, history)

    def append_message(self, session_id: str, message: Any) -> None:
        history = self.get_history(session_id)
        history.append(message)

    def clear_session(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def _cleanup_expired_sessions(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.ttl_seconds)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE last_active < ?",
                (cutoff.isoformat(),),
            )

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    history TEXT NOT NULL,
                    last_active TIMESTAMP NOT NULL
                )
                """
            )

    def _save_history(self, session_id: str, history: list[Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (session_id, history, last_active)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    history = excluded.history,
                    last_active = excluded.last_active
                """,
                (session_id, json.dumps(history, ensure_ascii=False), self._now()),
            )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
