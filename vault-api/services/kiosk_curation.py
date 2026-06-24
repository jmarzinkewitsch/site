from __future__ import annotations

from collections import deque

from models import LibraryItem


def curate_kiosk_overview(
    *,
    continue_watching: list[LibraryItem],
    next_up: list[LibraryItem],
    latest_movies: list[LibraryItem],
    latest_series: list[LibraryItem],
    spotlight: list[LibraryItem],
    shelf_limit: int = 8,
) -> dict[str, list[LibraryItem]]:
    """Build the first kiosk shelf from all media sources without changing the API."""
    original = {
        "continue_watching": continue_watching,
        "next_up": next_up,
        "latest_movies": latest_movies,
        "latest_series": latest_series,
        "spotlight": spotlight,
    }
    if not _needs_kiosk_curation(
        continue_watching=continue_watching,
        next_up=next_up,
        latest_movies=latest_movies,
        latest_series=latest_series,
        spotlight=spotlight,
        limit=shelf_limit,
    ):
        return original

    shelf = curate_kiosk_shelf(
        continue_watching=continue_watching,
        next_up=next_up,
        latest_movies=latest_movies,
        latest_series=latest_series,
        spotlight=spotlight,
        limit=shelf_limit,
    )
    used_ids = {item.id for item in shelf}
    return {
        "continue_watching": shelf,
        "next_up": [item for item in next_up if item.id not in used_ids],
        "latest_movies": [item for item in latest_movies if item.id not in used_ids],
        "latest_series": [item for item in latest_series if item.id not in used_ids],
        "spotlight": [item for item in spotlight if item.id not in used_ids],
    }


def curate_kiosk_shelf(
    *,
    continue_watching: list[LibraryItem],
    next_up: list[LibraryItem],
    latest_movies: list[LibraryItem],
    latest_series: list[LibraryItem],
    spotlight: list[LibraryItem],
    limit: int = 8,
) -> list[LibraryItem]:
    candidates = _dedupe_candidates(
        [
            *continue_watching,
            *next_up,
            *latest_movies,
            *latest_series,
            *spotlight,
        ]
    )
    # Always interleave movies — even when everything fits within `limit`, films
    # must be promoted out from behind the episode wall (the loop simply stops
    # early when candidates run out).
    movie_candidates = [item for item in candidates if item.type == "Movie"]
    any_queue = deque(candidates)
    movie_queue = deque(movie_candidates)
    used_ids: set[str] = set()
    result: list[LibraryItem] = []

    for index in range(limit):
        candidate = None
        if index in _movie_promotion_slots(limit):
            candidate = _pop_next(movie_queue, used_ids)
        if candidate is None:
            candidate = _pop_next(any_queue, used_ids)
        if candidate is None:
            break
        used_ids.add(candidate.id)
        result.append(candidate)
    return result


def _movie_promotion_slots(limit: int) -> set[int]:
    return set(range(1, limit, 3))


def _pop_next(queue: deque[LibraryItem], used_ids: set[str]) -> LibraryItem | None:
    while queue:
        item = queue.popleft()
        if item.id not in used_ids:
            return item
    return None


def _dedupe_candidates(items: list[LibraryItem]) -> list[LibraryItem]:
    seen_ids: set[str] = set()
    seen_episode_series: set[str] = set()
    deduped: list[LibraryItem] = []

    for item in items:
        if item.id in seen_ids:
            continue
        if item.type == "Episode":
            series_key = item.series_id or f"episode:{item.id}"
            if series_key in seen_episode_series:
                continue
            seen_episode_series.add(series_key)
        seen_ids.add(item.id)
        deduped.append(item)
    return deduped


def _needs_kiosk_curation(
    *,
    continue_watching: list[LibraryItem],
    next_up: list[LibraryItem],
    latest_movies: list[LibraryItem],
    latest_series: list[LibraryItem],
    spotlight: list[LibraryItem],
    limit: int,
) -> bool:
    shelf = [
        *continue_watching,
        *next_up,
        *latest_movies,
        *latest_series,
        *spotlight,
    ][:limit]
    if _has_duplicate_episode_series(shelf):
        return True

    all_items = [
        *continue_watching,
        *next_up,
        *latest_movies,
        *latest_series,
        *spotlight,
    ]
    available_movies = sum(1 for item in _dedupe_candidates(all_items) if item.type == "Movie")
    visible_movies = sum(1 for item in shelf if item.type == "Movie")
    target_movies = min(2, available_movies)
    return target_movies > visible_movies


def _has_duplicate_episode_series(items: list[LibraryItem]) -> bool:
    seen_series: set[str] = set()
    for item in items:
        if item.type != "Episode":
            continue
        series_key = item.series_id or f"episode:{item.id}"
        if series_key in seen_series:
            return True
        seen_series.add(series_key)
    return False
