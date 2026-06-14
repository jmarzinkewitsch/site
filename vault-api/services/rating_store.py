"""SQLite persistence for Vault-owned rating snapshots.

These ratings are deliberately separate from Jellyfin user data: they survive
Jellyfin item deletion and can seed future profile/recommendation work.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from models import RatingSnapshot

DB_PATH = Path(os.environ.get("VAULT_DB_PATH", "vault.db"))


class RatingStore:
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
                CREATE TABLE IF NOT EXISTS rating_snapshots (
                    item_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    type TEXT NOT NULL,
                    year INTEGER,
                    tmdb_id INTEGER,
                    imdb_id TEXT,
                    janno_rating REAL,
                    tanno_rating REAL,
                    tanno_fear_factor REAL,
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
                """
            )

    def upsert(
        self,
        *,
        item_id: str,
        title: str,
        type: str,
        year: int | None = None,
        tmdb_id: int | None = None,
        imdb_id: str | None = None,
        janno_rating: float | None = None,
        tanno_rating: float | None = None,
        tanno_fear_factor: float | None = None,
    ) -> RatingSnapshot:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rating_snapshots (
                    item_id, title, type, year, tmdb_id, imdb_id,
                    janno_rating, tanno_rating, tanno_fear_factor, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                ON CONFLICT(item_id) DO UPDATE SET
                    title = excluded.title,
                    type = excluded.type,
                    year = excluded.year,
                    tmdb_id = excluded.tmdb_id,
                    imdb_id = excluded.imdb_id,
                    janno_rating = excluded.janno_rating,
                    tanno_rating = excluded.tanno_rating,
                    tanno_fear_factor = excluded.tanno_fear_factor,
                    updated_at = excluded.updated_at
                """,
                (
                    item_id, title, type, year, tmdb_id, imdb_id,
                    janno_rating, tanno_rating, tanno_fear_factor,
                ),
            )
            row = conn.execute("SELECT * FROM rating_snapshots WHERE item_id = ?", (item_id,)).fetchone()
        return _snapshot_from_row(row)

    def get(self, item_id: str) -> RatingSnapshot | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM rating_snapshots WHERE item_id = ?", (item_id,)).fetchone()
        return _snapshot_from_row(row) if row is not None else None

    def list(self) -> list[RatingSnapshot]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM rating_snapshots ORDER BY updated_at DESC").fetchall()
        return [_snapshot_from_row(row) for row in rows]


def _snapshot_from_row(row: sqlite3.Row) -> RatingSnapshot:
    data: dict[str, Any] = dict(row)
    return RatingSnapshot.model_validate(data)
