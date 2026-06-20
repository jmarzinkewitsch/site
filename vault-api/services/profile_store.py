"""SQLite persistence for persona mini-profiles (janno/tanno).

Mirrors the pattern from rating_store.py: one table, thread-safe, path from env.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from models import PersonaProfile

DB_PATH = Path(os.environ.get("VAULT_DB_PATH", "vault.db"))

VALID_PERSONS = {"janno", "tanno"}
DEFAULTS: dict[str, PersonaProfile] = {
    "janno": PersonaProfile(person="janno", favorite_genres=[], fear_comfort=7),
    "tanno": PersonaProfile(person="tanno", favorite_genres=[], fear_comfort=4),
}


class ProfileStore:
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
                CREATE TABLE IF NOT EXISTS persona_profiles (
                    person TEXT PRIMARY KEY,
                    favorite_genres TEXT NOT NULL DEFAULT '[]',
                    fear_comfort INTEGER NOT NULL DEFAULT 5,
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
                """
            )

    def upsert(self, profile: PersonaProfile) -> PersonaProfile:
        import json
        genres_json = json.dumps(profile.favorite_genres, ensure_ascii=False)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO persona_profiles (person, favorite_genres, fear_comfort, updated_at)
                VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                ON CONFLICT(person) DO UPDATE SET
                    favorite_genres = excluded.favorite_genres,
                    fear_comfort = excluded.fear_comfort,
                    updated_at = excluded.updated_at
                """,
                (profile.person, genres_json, profile.fear_comfort),
            )
            row = conn.execute(
                "SELECT * FROM persona_profiles WHERE person = ?", (profile.person,)
            ).fetchone()
        return _profile_from_row(row)

    def get(self, person: str) -> PersonaProfile:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM persona_profiles WHERE person = ?", (person,)
            ).fetchone()
        if row is None:
            return DEFAULTS.get(person, PersonaProfile(person=person))
        return _profile_from_row(row)

    def list_all(self) -> list[PersonaProfile]:
        results = []
        with self._lock, self._connect() as conn:
            rows = {
                row["person"]: row
                for row in conn.execute("SELECT * FROM persona_profiles").fetchall()
            }
        for person in ("janno", "tanno"):
            if person in rows:
                results.append(_profile_from_row(rows[person]))
            else:
                results.append(DEFAULTS[person])
        return results


def _profile_from_row(row: sqlite3.Row) -> PersonaProfile:
    import json
    data: dict[str, Any] = dict(row)
    data["favorite_genres"] = json.loads(data.get("favorite_genres") or "[]")
    data.pop("updated_at", None)
    return PersonaProfile.model_validate(data)
