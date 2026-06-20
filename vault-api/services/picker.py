"""Candidate gathering + LLM curation for the "Was schauen wir?" picker."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from models import DiscoverItem, LibraryItem, PersonaProfile, PickerRequest, PickItem, PickerResponse
from services.recommender import (
    TMDB_FEAR_GENRES,
    _estimated_discover_fear,
    _estimated_library_fear,
)

logger = logging.getLogger(__name__)

# TMDB genre name → numeric id (a curated subset sufficient for genre-filter discovery)
GENRE_NAME_TO_TMDB_ID: dict[str, int] = {
    "action": 28,
    "abenteuer": 12,
    "adventure": 12,
    "animation": 16,
    "komödie": 35,
    "comedy": 35,
    "krimi": 80,
    "crime": 80,
    "documentary": 99,
    "dokumentation": 99,
    "drama": 18,
    "family": 10751,
    "fantasy": 14,
    "history": 36,
    "historie": 36,
    "horror": 27,
    "musik": 10402,
    "music": 10402,
    "mystery": 9648,
    "romance": 10749,
    "romantik": 10749,
    "sci-fi": 878,
    "science fiction": 878,
    "thriller": 53,
    "war": 10752,
    "western": 37,
}


def _genres_to_tmdb_ids(genres: list[str]) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for g in genres:
        gid = GENRE_NAME_TO_TMDB_ID.get(g.lower())
        if gid and gid not in seen:
            ids.append(gid)
            seen.add(gid)
    return ids


SHORT_MAX_SECONDS = 90 * 60  # < 90 min → "short"
FEATURE_MIN_SECONDS = 90 * 60  # ≥ 90 min → "feature"


def _length_ok(item: LibraryItem, length: str | None) -> bool:
    if length is None:
        return True
    if length == "series":
        return item.type == "Series"
    runtime = item.runtime_seconds
    if length == "short":
        return item.type == "Movie" and (runtime is not None and runtime < SHORT_MAX_SECONDS)
    if length == "feature":
        return item.type == "Movie" and (runtime is None or runtime >= FEATURE_MIN_SECONDS)
    return True


def _item_id(item: LibraryItem) -> str:
    return f"library:{item.id}"


def _discover_id(item: DiscoverItem) -> str:
    return f"tmdb:{item.tmdb_id}"


def _short_overview(text: str | None, limit: int = 200) -> str:
    if not text:
        return ""
    return text[:limit] + ("…" if len(text) > limit else "")


def _library_candidate(item: LibraryItem, fear: int) -> dict[str, Any]:
    return {
        "id": _item_id(item),
        "title": item.title,
        "year": item.year,
        "type": item.type,
        "genres": item.genres,
        "overview": _short_overview(item.overview),
        "rating": item.community_rating,
        "fear": fear,
        "source": "library",
    }


def _discover_candidate(item: DiscoverItem, fear: int) -> dict[str, Any]:
    return {
        "id": _discover_id(item),
        "title": item.title,
        "year": item.year,
        "type": item.type,
        "genres": [],  # DiscoverItem has genre_ids, not names — keep compact
        "genre_ids": item.genre_ids,
        "overview": _short_overview(item.overview),
        "rating": item.vote_average,
        "fear": fear,
        "source": "discover",
    }


def _fear_distance(fear: int, mood_fear: int | None) -> float:
    """Lower = better match to desired intensity."""
    if mood_fear is None:
        return 0.0
    return abs(fear - mood_fear) / 10.0


def _simple_score(rating: float | None, fear: int, mood_fear: int | None) -> float:
    base = (rating or 5.0) / 10.0
    penalty = _fear_distance(fear, mood_fear)
    return max(0.0, base - penalty * 0.3)


def gather_library_candidates(
    library_items: list[LibraryItem],
    request: PickerRequest,
    snapshots_by_id: dict,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Filter and annotate library items for the picker."""
    candidates: list[tuple[float, dict]] = []
    for item in library_items:
        # length filter
        if not _length_ok(item, request.length):
            continue
        # genre filter (if not surprise and genres provided)
        if not request.surprise and request.genres:
            item_genres_lower = {g.lower() for g in item.genres}
            if not any(g.lower() in item_genres_lower for g in request.genres):
                continue
        # exclude_ids
        if _item_id(item) in request.exclude_ids or item.id in request.exclude_ids:
            continue
        snapshot = snapshots_by_id.get(item.id) or snapshots_by_id.get(f"tmdb:{item.tmdb_id}")
        fear = _estimated_library_fear(item, snapshot)
        score = _simple_score(item.community_rating, fear, request.mood_fear)
        candidates.append((score, _library_candidate(item, fear)))

    candidates.sort(key=lambda t: t[0], reverse=True)
    return [c for _, c in candidates[:limit]]


def gather_discover_candidates(
    discover_items: list[DiscoverItem],
    owned_tmdb: set[tuple[str, int]],
    request: PickerRequest,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Filter and annotate TMDB discover items for the picker."""
    genre_ids_filter = _genres_to_tmdb_ids(request.genres) if not request.surprise else []
    candidates: list[tuple[float, dict]] = []
    for item in discover_items:
        # drop already-owned
        if (item.type, item.tmdb_id) in owned_tmdb:
            continue
        # exclude_ids
        if _discover_id(item) in request.exclude_ids:
            continue
        # genre filter
        if genre_ids_filter and not any(gid in item.genre_ids for gid in genre_ids_filter):
            continue
        # series only if length == "series"
        if request.length == "series" and item.type != "Series":
            continue
        if request.length in ("short", "feature") and item.type == "Series":
            continue
        fear = _estimated_discover_fear(item)
        score = _simple_score(item.vote_average, fear, request.mood_fear)
        candidates.append((score, _discover_candidate(item, fear)))

    candidates.sort(key=lambda t: t[0], reverse=True)
    return [c for _, c in candidates[:limit]]


def _build_pick_item(candidate: dict, reason: str) -> PickItem | None:
    try:
        source = candidate["source"]
        raw_id = candidate["id"]
        if source == "library":
            lib_id = raw_id.removeprefix("library:")
            return PickItem(
                id=raw_id,
                title=candidate["title"],
                type=candidate.get("type", "Movie"),
                year=candidate.get("year"),
                overview=candidate.get("overview") or None,
                source="library",
                status="playable",
                library_id=lib_id,
                tmdb_id=None,
                reason=reason,
                fear_factor=candidate.get("fear"),
                community_rating=candidate.get("rating"),
            )
        else:
            tmdb_id = int(raw_id.removeprefix("tmdb:"))
            return PickItem(
                id=raw_id,
                title=candidate["title"],
                type=candidate.get("type", "Movie"),
                year=candidate.get("year"),
                overview=candidate.get("overview") or None,
                source="discover",
                status="requestable",
                library_id=None,
                tmdb_id=tmdb_id,
                reason=reason,
                fear_factor=candidate.get("fear"),
                community_rating=candidate.get("rating"),
            )
    except Exception as exc:
        logger.warning("Failed to build PickItem from candidate %r: %s", candidate.get("id"), exc)
        return None


def _fallback_reason(source: str, title: str) -> str:
    if source == "library":
        return f"Top-bewerteter Titel aus der Bibliothek."
    return f"Beliebter Titel, der noch nicht in der Bibliothek ist."


def build_picker_response_from_llm(
    llm_result: dict,
    lib_by_id: dict[str, dict],
    disc_by_id: dict[str, dict],
) -> tuple[PickItem | None, PickItem | None, list[PickItem]]:
    """Map LLM-chosen ids back to full candidate metadata."""
    all_candidates = {**lib_by_id, **disc_by_id}

    def resolve(entry: dict | None, expected_source: str | None = None) -> PickItem | None:
        if not isinstance(entry, dict):
            return None
        cid = str(entry.get("id", ""))
        reason = str(entry.get("reason", "")).strip() or "Empfohlen."
        candidate = all_candidates.get(cid)
        if not candidate:
            return None
        if expected_source and candidate.get("source") != expected_source:
            # LLM mixed up sources — still build from whatever it returned
            pass
        return _build_pick_item(candidate, reason)

    library_pick = resolve(llm_result.get("library_pick"), "library")
    discover_pick = resolve(llm_result.get("discover_pick"), "discover")
    alternatives: list[PickItem] = []
    for alt_entry in (llm_result.get("alternatives") or [])[:6]:
        pick = resolve(alt_entry)
        if pick:
            alternatives.append(pick)

    return library_pick, discover_pick, alternatives


def build_fallback_response(
    lib_candidates: list[dict],
    disc_candidates: list[dict],
) -> tuple[PickItem | None, PickItem | None, list[PickItem]]:
    """Simple score-ordered fallback when LLM is unavailable or fails."""
    library_pick = None
    if lib_candidates:
        c = lib_candidates[0]
        library_pick = _build_pick_item(c, _fallback_reason("library", c["title"]))

    discover_pick = None
    if disc_candidates:
        c = disc_candidates[0]
        discover_pick = _build_pick_item(c, _fallback_reason("discover", c["title"]))

    # Alternatives: next best from each list (up to 6 total)
    alternatives: list[PickItem] = []
    used_ids: set[str] = {
        (library_pick.id if library_pick else ""),
        (discover_pick.id if discover_pick else ""),
    }
    for pool in [lib_candidates[1:4], disc_candidates[1:4]]:
        for c in pool:
            if c["id"] not in used_ids:
                pick = _build_pick_item(c, _fallback_reason(c["source"], c["title"]))
                if pick:
                    alternatives.append(pick)
                    used_ids.add(c["id"])

    return library_pick, discover_pick, alternatives
