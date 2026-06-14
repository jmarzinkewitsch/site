"""Content-based recommendations with optional M7 Claude wording/ranking."""
from __future__ import annotations

from collections import Counter

from models import DiscoverItem, LibraryItem, RecommendationItem, RecommendationResponse, RecommendationShelf
from services.anthropic import AnthropicError, AnthropicService


def _quality(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(float(value), 10.0)) / 10.0


def _library_score(item: LibraryItem, profile: Counter[str]) -> float:
    genre_hits = sum(profile[g.lower()] for g in item.genres)
    liked = (item.user_rating or 0) / 10
    watched = 0.15 if item.played or (item.played_percentage or 0) >= 80 else 0
    return round(genre_hits * 0.18 + _quality(item.community_rating) * 0.3 + liked * 0.45 + watched, 3)


def _discover_score(item: DiscoverItem, profile: Counter[str]) -> float:
    # TMDB discover/recommendation candidates arrive pre-filtered by popularity;
    # without detail calls we combine that ordering with TMDB's vote average.
    return round(0.5 + _quality(item.vote_average) * 0.5 + min(sum(profile.values()), 10) * 0.01, 3)


def _reason_for_library(item: LibraryItem, favorite_genres: list[str]) -> str:
    if item.user_rating and item.user_rating >= 8:
        return f"Hoch bewertet von dir ({item.user_rating:g}/10) — ein guter Kandidat zum Wiederentdecken."
    if favorite_genres and set(g.lower() for g in item.genres) & set(favorite_genres):
        return f"Passt zu deinen häufigen Genres: {', '.join(g.title() for g in favorite_genres[:2])}."
    if item.community_rating:
        return f"Starker Bibliothekstitel mit {item.community_rating:g}/10 Community-Score."
    return "Aus deiner Bibliothek, passend zu deinem bisherigen Sehprofil."


def _reason_for_discover(item: DiscoverItem, favorite_genres: list[str]) -> str:
    if item.vote_average:
        return f"Neuer Kandidat mit {item.vote_average:g}/10 TMDB-Score, passend zu deinem Profil."
    if favorite_genres:
        return f"Anfragbarer Titel als Ergänzung zu deinen {favorite_genres[0].title()}-Vorlieben."
    return "Anfragbarer Titel aus aktuellen TMDB-Empfehlungen."


def _profile(items: list[LibraryItem]) -> tuple[Counter[str], list[str], list[str]]:
    genres: Counter[str] = Counter()
    liked_titles: list[str] = []
    for item in items:
        weight = 1
        if item.user_rating is not None:
            weight += max(0, int(item.user_rating - 5))
        if item.played or (item.played_percentage or 0) >= 80:
            weight += 1
        if item.user_rating and item.user_rating >= 7:
            liked_titles.append(item.title)
        for genre in item.genres:
            genres[genre.lower()] += weight
    favorite_genres = [genre for genre, _ in genres.most_common(3)]
    return genres, favorite_genres, liked_titles


def _rec_id(prefix: str, raw_id: object) -> str:
    return f"{prefix}:{raw_id}"


async def build_recommendations(
    library_items: list[LibraryItem],
    discover_items: list[DiscoverItem],
    anthropic: AnthropicService | None = None,
    limit: int = 12,
) -> RecommendationResponse:
    profile, favorite_genres, liked_titles = _profile(library_items)
    owned_tmdb = {(item.type, item.tmdb_id) for item in library_items if item.tmdb_id is not None}

    library_recs = [
        RecommendationItem(
            id=_rec_id("library", item.id),
            title=item.title,
            type=item.type,
            year=item.year,
            overview=item.overview,
            poster_url=item.poster_url,
            backdrop_url=item.backdrop_url,
            score=_library_score(item, profile),
            reason=_reason_for_library(item, favorite_genres),
            status="playable",
            library_id=item.id,
        )
        for item in library_items
    ]
    library_recs.sort(key=lambda item: item.score, reverse=True)

    new_recs = [
        RecommendationItem(
            id=_rec_id("tmdb", item.tmdb_id),
            title=item.title,
            type=item.type,
            year=item.year,
            overview=item.overview,
            poster_url=item.poster_url,
            backdrop_url=item.backdrop_url,
            score=_discover_score(item, profile),
            reason=_reason_for_discover(item, favorite_genres),
            status="requestable",
            tmdb_id=item.tmdb_id,
        )
        for item in discover_items
        if (item.type, item.tmdb_id) not in owned_tmdb
    ]
    new_recs.sort(key=lambda item: item.score, reverse=True)

    llm_used = False
    if anthropic is not None:
        try:
            new_recs = await anthropic.improve(new_recs[:limit], liked_titles)
            library_recs = await anthropic.improve(library_recs[:limit], liked_titles)
            llm_used = True
        except AnthropicError:
            pass

    return RecommendationResponse(
        shelves=[
            RecommendationShelf(id="new-for-you", title="Für dich neu", items=new_recs[:limit]),
            RecommendationShelf(id="from-library", title="Aus deiner Bibliothek", items=library_recs[:limit]),
        ],
        llm_used=llm_used,
    )
