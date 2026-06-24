from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def database_path() -> Path:
    configured_path = os.getenv("SUPPORT_AGENT_DB_PATH")
    if configured_path:
        return Path(configured_path)

    return project_root() / "sessions.db"
