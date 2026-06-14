"""Content-based recommendations with optional M7 Claude wording/ranking."""
from __future__ import annotations

from collections import Counter

from models import DiscoverItem, LibraryItem, RatingSnapshot, RecommendationItem, RecommendationResponse, RecommendationShelf
from services.anthropic import AnthropicError, AnthropicService


def _quality(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(float(value), 10.0)) / 10.0


def _pct(value: float) -> int:
    return int(round(max(0.0, min(value, 1.0)) * 100))


def _snapshot_key(snapshot: RatingSnapshot) -> tuple[str | None, int | str]:
    if snapshot.tmdb_id is not None:
        return (snapshot.type, snapshot.tmdb_id)
    return (snapshot.type, snapshot.item_id)


def _item_key(item: LibraryItem) -> tuple[str | None, int | str]:
    if item.tmdb_id is not None:
        return (item.type, item.tmdb_id)
    return (item.type, item.id)


def _snapshot_index(snapshots: list[RatingSnapshot]) -> dict[tuple[str | None, int | str], RatingSnapshot]:
    indexed: dict[tuple[str | None, int | str], RatingSnapshot] = {}
    for snapshot in snapshots:
        indexed[_snapshot_key(snapshot)] = snapshot
        indexed[(snapshot.type, snapshot.item_id)] = snapshot
    return indexed


def _library_score(item: LibraryItem, profile: Counter[str]) -> float:
    genre_hits = sum(profile[g.lower()] for g in item.genres)
    liked = (item.user_rating or 0) / 10
    watched = 0.15 if item.played or (item.played_percentage or 0) >= 80 else 0
    return round(genre_hits * 0.18 + _quality(item.community_rating) * 0.3 + liked * 0.45 + watched, 3)


def _discover_score(item: DiscoverItem, profile: Counter[str]) -> float:
    return round(0.5 + _quality(item.vote_average) * 0.5 + min(sum(profile.values()), 10) * 0.01, 3)


def _profile(items: list[LibraryItem], snapshots: list[RatingSnapshot], person: str) -> tuple[Counter[str], list[str], list[str]]:
    genres: Counter[str] = Counter()
    liked_titles: list[str] = []
    snapshot_by_item = _snapshot_index(snapshots)
    for item in items:
        snapshot = snapshot_by_item.get(_item_key(item))
        rating = getattr(snapshot, f"{person}_rating", None) if snapshot else item.user_rating
        weight = 1 + max(0, int((rating or 0) - 5))
        if item.played or (item.played_percentage or 0) >= 80:
            weight += 1
        if rating and rating >= 7:
            liked_titles.append(item.title)
        for genre in item.genres:
            genres[genre.lower()] += weight
    favorite_genres = [genre for genre, _ in genres.most_common(3)]
    return genres, favorite_genres, liked_titles


def _person_score(snapshot: RatingSnapshot | None, field: str, fallback: float | None) -> int:
    rating = getattr(snapshot, field, None) if snapshot else fallback
    return _pct(_quality(rating))


def _fear(snapshot: RatingSnapshot | None) -> int | None:
    if snapshot is None or snapshot.tanno_fear_factor is None:
        return None
    return int(round(snapshot.tanno_fear_factor))


def _combined_score(base: float, snapshot: RatingSnapshot | None, profile: str) -> float:
    janno = _quality(snapshot.janno_rating if snapshot else None)
    tanno = _quality(snapshot.tanno_rating if snapshot else None)
    fear = _quality(snapshot.tanno_fear_factor if snapshot else None)
    if profile == "janno":
        return base * 0.55 + janno * 0.45
    if profile == "tanno":
        return base * 0.50 + tanno * 0.60 - fear * 0.25
    return base * 0.45 + (janno + tanno) * 0.35 - fear * 0.20


def _tags(item_type: str, favorite_genres: list[str], fear: int | None) -> list[str]:
    tags = ["Film" if item_type == "Movie" else "Serie"]
    tags += [genre.title() for genre in favorite_genres[:2]]
    if fear is not None:
        tags.append("Grusel niedrig" if fear <= 3 else "Grusel mittel" if fear <= 6 else "Grusel hoch")
    return tags[:4]


def _reason_for_library(item: LibraryItem, favorite_genres: list[str], snapshot: RatingSnapshot | None, profile: str) -> str:
    if profile == "both" and snapshot and snapshot.janno_rating is not None and snapshot.tanno_rating is not None:
        return f"Für euch beide: Janno {snapshot.janno_rating:g}/10, Tanno {snapshot.tanno_rating:g}/10."
    if favorite_genres and set(g.lower() for g in item.genres) & set(favorite_genres):
        return f"Passt zu {', '.join(g.title() for g in favorite_genres[:2])}."
    if item.community_rating:
        return f"Starker Bibliothekstitel mit {item.community_rating:g}/10 Community-Score."
    return "Aus deiner Bibliothek, passend zu eurem Profil."


def _reason_for_discover(item: DiscoverItem, favorite_genres: list[str], profile: str) -> str:
    who = "euch beide" if profile == "both" else ("Janno" if profile == "janno" else "Tanno")
    if item.vote_average:
        return f"Anfragbarer Kandidat für {who} mit {item.vote_average:g}/10 TMDB-Score."
    if favorite_genres:
        return f"Anfragbarer Titel passend zu {favorite_genres[0].title()}."
    return f"Anfragbarer Titel für {who}."


def _rec_id(prefix: str, raw_id: object, profile: str) -> str:
    return f"{prefix}:{raw_id}"


def _library_rec(item: LibraryItem, score: float, profile: str, favorite_genres: list[str], snapshot: RatingSnapshot | None) -> RecommendationItem:
    return RecommendationItem(
        id=_rec_id("library", item.id, profile), title=item.title, type=item.type, year=item.year,
        overview=item.overview, poster_url=item.poster_url, backdrop_url=item.backdrop_url,
        score=round(score, 3), reason=_reason_for_library(item, favorite_genres, snapshot, profile),
        status="playable", library_id=item.id, community_rating=item.community_rating, critic_rating=item.critic_rating,
        match_score=_pct(score), janno_score=_person_score(snapshot, "janno_rating", item.user_rating),
        tanno_score=_person_score(snapshot, "tanno_rating", item.user_rating), fear_factor=_fear(snapshot),
        profile=profile, category_tags=_tags(item.type, favorite_genres, _fear(snapshot)),
    )


def _discover_rec(item: DiscoverItem, score: float, profile: str, favorite_genres: list[str]) -> RecommendationItem:
    return RecommendationItem(
        id=_rec_id("tmdb", item.tmdb_id, profile), title=item.title, type=item.type, year=item.year,
        overview=item.overview, poster_url=item.poster_url, backdrop_url=item.backdrop_url,
        score=round(score, 3), reason=_reason_for_discover(item, favorite_genres, profile), status="requestable",
        tmdb_id=item.tmdb_id, community_rating=item.vote_average, match_score=_pct(score),
        janno_score=_pct(_quality(item.vote_average)), tanno_score=_pct(_quality(item.vote_average)),
        fear_factor=None, profile=profile, category_tags=_tags(item.type, favorite_genres, None),
    )


async def build_recommendations(
    library_items: list[LibraryItem],
    discover_items: list[DiscoverItem],
    anthropic: AnthropicService | None = None,
    limit: int = 12,
    snapshots: list[RatingSnapshot] | None = None,
) -> RecommendationResponse:
    snapshots = snapshots or []
    snapshot_by_item = _snapshot_index(snapshots)
    owned_tmdb = {(item.type, item.tmdb_id) for item in library_items if item.tmdb_id is not None}
    shelves: list[RecommendationShelf] = []
    llm_used = False

    for profile, title in [("both", "Für euch beide"), ("janno", "Jannos Profil"), ("tanno", "Tannos Profil")]:
        j_profile, j_favorites, liked_j = _profile(library_items, snapshots, "janno")
        t_profile, t_favorites, liked_t = _profile(library_items, snapshots, "tanno")
        active_profile = j_profile + t_profile if profile == "both" else (j_profile if profile == "janno" else t_profile)
        favorites = [genre for genre, _ in active_profile.most_common(3)] or (j_favorites + t_favorites)[:3]

        library_recs = []
        for item in library_items:
            snapshot = snapshot_by_item.get(_item_key(item))
            base = _library_score(item, active_profile)
            library_recs.append(_library_rec(item, _combined_score(base, snapshot, profile), profile, favorites, snapshot))
        library_recs.sort(key=lambda item: item.score, reverse=True)

        new_recs = [
            _discover_rec(item, _discover_score(item, active_profile), profile, favorites)
            for item in discover_items
            if (item.type, item.tmdb_id) not in owned_tmdb
        ]
        new_recs.sort(key=lambda item: item.score, reverse=True)

        items = (new_recs + library_recs)[:limit]
        if anthropic is not None:
            try:
                items = await anthropic.improve(items, liked_j + liked_t)
                llm_used = True
            except AnthropicError:
                pass
        shelves.append(RecommendationShelf(id=profile, title=title, profile=profile, items=items))

    return RecommendationResponse(shelves=shelves, llm_used=llm_used)
