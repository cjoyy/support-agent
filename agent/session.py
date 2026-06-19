from __future__ import annotations

import time
from typing import Any


class SessionManager:
    def __init__(self, ttl_seconds: int = 30 * 60) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, dict[str, Any]] = {}

    def get_history(self, session_id: str) -> list[Any]:
        self._cleanup_expired_sessions()
        session = self._sessions.setdefault(
            session_id,
            {"history": [], "last_active": time.time()},
        )
        session["last_active"] = time.time()
        return session["history"]

    def append_message(self, session_id: str, message: Any) -> None:
        history = self.get_history(session_id)
        history.append(message)
        self._sessions[session_id]["last_active"] = time.time()

    def clear_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _cleanup_expired_sessions(self) -> None:
        now = time.time()
        expired_session_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session["last_active"] > self.ttl_seconds
        ]
        for session_id in expired_session_ids:
            self.clear_session(session_id)
