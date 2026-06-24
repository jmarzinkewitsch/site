"""SQLite persistence for Vault-owned podcast progress."""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from models import PodcastProgress

DB_PATH = Path(os.environ.get("VAULT_DB_PATH", "vault.db"))


class PodcastStore:
    def __init__(self, path: Path = DB_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS podcast_progress (
                    episode_id TEXT PRIMARY KEY,
                    position_seconds REAL NOT NULL DEFAULT 0,
                    completed INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
                """
            )

    def upsert(self, *, episode_id: str, position_seconds: float, completed: bool) -> PodcastProgress:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO podcast_progress (
                    episode_id, position_seconds, completed, updated_at
                ) VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                ON CONFLICT(episode_id) DO UPDATE SET
                    position_seconds = excluded.position_seconds,
                    completed = excluded.completed,
                    updated_at = excluded.updated_at
                """,
                (episode_id, position_seconds, int(completed)),
            )
            row = conn.execute("SELECT * FROM podcast_progress WHERE episode_id = ?", (episode_id,)).fetchone()
        return _progress_from_row(row)

    def get(self, episode_id: str) -> PodcastProgress | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM podcast_progress WHERE episode_id = ?", (episode_id,)).fetchone()
        return _progress_from_row(row) if row is not None else None

    def get_many(self, episode_ids: list[str]) -> dict[str, PodcastProgress]:
        ids = list(dict.fromkeys(episode_ids))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM podcast_progress WHERE episode_id IN ({placeholders})",
                ids,
            ).fetchall()
        return {row["episode_id"]: _progress_from_row(row) for row in rows}


def _progress_from_row(row: sqlite3.Row) -> PodcastProgress:
    data: dict[str, Any] = dict(row)
    data["completed"] = bool(data.get("completed"))
    return PodcastProgress.model_validate(data)
