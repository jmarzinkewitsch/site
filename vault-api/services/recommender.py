"""Small content-based recommendation engine for M6.

The first version is deliberately deterministic and explainable: it learns a
lightweight taste profile from Jellyfin genres and user signals, then scores
library candidates and TMDB discovery results against that profile. No LLM or
background job is required; M7 can add prose explanations on top.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from models import DiscoverItem, LibraryItem, RecommendationItem

# TMDB's stable genre ids for movie/tv discovery. Jellyfin stores genre names,
# so we translate the user's top Jellyfin genres into TMDB filters.
_TMDB_GENRES: dict[str, dict[str, int]] = {
    "Movie": {
        "Action": 28, "Adventure": 12, "Animation": 16, "Comedy": 35,
        "Crime": 80, "Documentary": 99, "Drama": 18, "Family": 10751,
        "Fantasy": 14, "History": 36, "Horror": 27, "Music": 10402,
        "Mystery": 9648, "Romance": 10749, "Science Fiction": 878,
        "Sci-Fi": 878, "Thriller": 53, "War": 10752, "Western": 37,
    },
    "Series": {
        "Action": 10759, "Adventure": 10759, "Animation": 16, "Comedy": 35,
        "Crime": 80, "Documentary": 99, "Drama": 18, "Family": 10751,
        "Kids": 10762, "Mystery": 9648, "News": 10763, "Reality": 10764,
        "Science Fiction": 10765, "Sci-Fi": 10765, "Fantasy": 10765,
        "Soap": 10766, "Talk": 10767, "War": 10768, "Western": 37,
    },
}


@dataclass(frozen=True)
class TasteProfile:
    genres: Counter[str]
    top_genres: tuple[str, ...]

    @property
    def empty(self) -> bool:
        return not self.genres


def _signal_weight(item: LibraryItem) -> float:
    weight = 0.0
    if item.user_rating is not None:
        # User rating is the strongest signal; only positive/neutral ratings
        # should pull recommendations toward a genre.
        weight += max(item.user_rating - 5.0, 0.0) * 2.0
    if item.played:
        weight += 2.0
    if item.resume_position_seconds > 0:
        weight += 1.0
    if item.community_rating is not None and item.community_rating >= 7.5:
        weight += 0.5
    return weight


def build_profile(items: list[LibraryItem]) -> TasteProfile:
    genres: Counter[str] = Counter()
    for item in items:
        weight = _signal_weight(item)
        if weight <= 0:
            continue
        for genre in item.genres:
            genres[genre] += weight
    top = tuple(genre for genre, _ in genres.most_common(5))
    return TasteProfile(genres=genres, top_genres=top)


def _candidate_score(item: LibraryItem, profile: TasteProfile) -> float:
    score = 0.0
    matched = set(item.genres) & set(profile.genres)
    for genre in matched:
        score += profile.genres[genre]
    if item.community_rating is not None:
        score += item.community_rating / 2.0
    if item.critic_rating is not None:
        score += item.critic_rating / 25.0
    if item.year is not None and item.year >= 2015:
        score += 0.25
    return score


def recommend_library(catalog: list[LibraryItem], limit: int) -> list[RecommendationItem]:
    profile = build_profile(catalog)
    candidates = [i for i in catalog if not i.played and i.resume_position_seconds <= 0]
    if profile.empty:
        ranked = sorted(candidates, key=lambda i: (i.community_rating or 0, i.year or 0), reverse=True)
    else:
        ranked = sorted(candidates, key=lambda i: _candidate_score(i, profile), reverse=True)
    return [
        RecommendationItem(
            item=item,
            score=round(_candidate_score(item, profile), 2) if not profile.empty else None,
            reason=_reason(item.genres, profile.top_genres),
        )
        for item in ranked[:limit]
    ]


def tmdb_genre_filter(profile: TasteProfile, media_type: str) -> str | None:
    ids = []
    mapping = _TMDB_GENRES["Series" if media_type.lower() == "series" else "Movie"]
    for genre in profile.top_genres:
        if genre in mapping and mapping[genre] not in ids:
            ids.append(mapping[genre])
    return ",".join(str(i) for i in ids[:3]) or None


def recommend_discover(
    items: list[DiscoverItem], owned_tmdb_ids: set[int], profile: TasteProfile, limit: int
) -> list[RecommendationItem]:
    fresh = [item for item in items if item.tmdb_id not in owned_tmdb_ids]
    ranked = sorted(fresh, key=lambda i: (i.vote_average or 0, i.year or 0), reverse=True)
    return [
        RecommendationItem(
            discover=item,
            score=round(item.vote_average, 2) if item.vote_average is not None else None,
            reason=_reason([], profile.top_genres) if not profile.empty else "Beliebt bei TMDB und noch nicht in deiner Bibliothek.",
        )
        for item in ranked[:limit]
    ]


def _reason(candidate_genres, top_genres: tuple[str, ...]) -> str:
    matched = [g for g in candidate_genres if g in top_genres]
    if matched:
        return f"Passt zu deinem Geschmack für {', '.join(matched[:2])}."
    if top_genres:
        return f"Ausgewählt aus deinen Top-Genres: {', '.join(top_genres[:2])}."
    return "Hoch bewertet und noch nicht gesehen."
