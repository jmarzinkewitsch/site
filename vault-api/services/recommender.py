"""Content-based recommendations with optional M7 Claude wording/ranking."""
from __future__ import annotations

from collections import Counter
import logging
import re

from models import DiscoverItem, LibraryItem, RatingSnapshot, RecommendationItem, RecommendationResponse, RecommendationShelf
from services.anthropic import AnthropicError, AnthropicService

logger = logging.getLogger(__name__)

FEAR_GENRES = {
    "horror": 9,
    "thriller": 6,
    "mystery": 4,
    "crime": 3,
    "sci-fi": 2,
    "science fiction": 2,
    "fantasy": 2,
    "action": 1,
}
CALM_GENRES = {"comedy", "romance", "family", "music", "documentary", "kids"}
TMDB_FEAR_GENRES = {
    27: 9,      # Horror
    53: 6,      # Thriller
    9648: 4,    # Mystery
    80: 3,      # Crime
    10765: 3,   # Sci-Fi & Fantasy (TV)
    14: 2,      # Fantasy
    878: 2,     # Science Fiction
    28: 1,      # Action
}
TMDB_CALM_GENRES = {35, 10749, 10751, 10402, 99, 10762}
FEAR_KEYWORDS = {
    "haunted": 8, "ghost": 7, "demon": 9, "possession": 9, "exorcism": 9,
    "zombie": 8, "vampire": 7, "werewolf": 7, "monster": 7, "creature": 6,
    "serial killer": 8, "slasher": 8, "murder": 5, "killer": 5, "cult": 6,
    "supernatural": 7, "curse": 6, "nightmare": 7, "terror": 7, "terrifying": 7,
    "bloody": 8, "gore": 9, "brutal": 7, "torture": 9, "apocalyptic": 5,
    "spuk": 8, "geist": 7, "dämon": 9, "besessen": 9, "zombie": 8,
    "vampir": 7, "monster": 7, "serienkiller": 8, "mord": 5, "sekten": 6,
    "übernatürlich": 7, "fluch": 6, "albtraum": 7, "blutig": 8, "brutal": 7,
}

def _quality(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(float(value), 10.0)) / 10.0


def _pct(value: float) -> int:
    return int(round(max(0.0, min(value, 1.0)) * 100))


def _score(value: float) -> float:
    return round(max(0.0, min(value, 1.0)), 3)


def _genre_affinity(genres: list[str], profile: Counter[str]) -> float:
    if not genres or not profile:
        return 0.0
    strongest = max(profile.values()) or 1
    hits = sum(profile[genre.lower()] / strongest for genre in genres)
    return min(hits / len(genres), 1.0)


def _fear01(value: float | None) -> float:
    """Normalise the Tanno fear factor to 0–1. The normal scale is 0–10; the
    rare for-fun values above 10 (especially brutal titles) just peg at max."""
    if value is None:
        return 0.0
    return max(0.0, min(float(value), 10.0)) / 10.0


def _rating_floor(official_rating: str | None) -> int:
    if not official_rating:
        return 0
    match = re.search(r"(?:FSK|TV-|RATED\s*)?(\d{1,2})", official_rating.upper())
    if not match:
        return 0
    age = int(match.group(1))
    if age >= 18:
        return 6
    if age >= 16:
        return 4
    if age >= 12:
        return 2
    return 0


def _keyword_fear(*texts: str | None) -> int:
    haystack = " ".join(text or "" for text in texts).lower()
    if not haystack:
        return 0
    score = 0
    for keyword, value in FEAR_KEYWORDS.items():
        if keyword in haystack:
            score = max(score, value)
    return score


def _estimated_library_fear(item: LibraryItem, snapshot: RatingSnapshot | None) -> int:
    manual = _fear(snapshot)
    if manual is not None:
        return manual
    genre_score = max((FEAR_GENRES.get(genre.lower(), 0) for genre in item.genres), default=0)
    keyword_score = _keyword_fear(item.title, item.overview)
    score = max(genre_score, keyword_score, _rating_floor(item.official_rating))
    if score and {genre.lower() for genre in item.genres} & CALM_GENRES:
        score = max(0, score - 1)
    return int(max(0, min(score, 10)))


def _estimated_discover_fear(item: DiscoverItem) -> int:
    genre_score = max((TMDB_FEAR_GENRES.get(genre_id, 0) for genre_id in item.genre_ids), default=0)
    keyword_score = _keyword_fear(item.title, item.overview)
    score = max(genre_score, keyword_score)
    if score and set(item.genre_ids) & TMDB_CALM_GENRES:
        score = max(0, score - 1)
    return int(max(0, min(score, 10)))


def _snapshot_key(snapshot: RatingSnapshot) -> tuple[str | None, int | str]:
    if snapshot.tmdb_id is not None:
        return (snapshot.type, snapshot.tmdb_id)
    return (snapshot.type, snapshot.item_id)


def _item_key(item: LibraryItem) -> tuple[str | None, int | str]:
    if item.tmdb_id is not None:
        return (item.type, item.tmdb_id)
    return (item.type, item.id)


def _snapshot_index(snapshots: list[RatingSnapshot]) -> dict[tuple[str | None, int | str], RatingSnapshot]:
    # `snapshots` arrives newest-first (RatingStore.list orders by updated_at
    # desc), so setdefault keeps the latest rating when the same TMDB title has
    # several snapshots (e.g. after a Jellyfin item was deleted and re-added).
    indexed: dict[tuple[str | None, int | str], RatingSnapshot] = {}
    for snapshot in snapshots:
        indexed.setdefault(_snapshot_key(snapshot), snapshot)
        indexed.setdefault((snapshot.type, snapshot.item_id), snapshot)
    return indexed


def _library_score(item: LibraryItem, profile: Counter[str]) -> float:
    genre_match = _genre_affinity(item.genres, profile)
    liked = (item.user_rating or 0) / 10
    watched = 1.0 if item.played or (item.played_percentage or 0) >= 80 else 0.0
    return round(genre_match * 0.45 + _quality(item.community_rating) * 0.25 + liked * 0.2 + watched * 0.1, 3)


def _discover_score(item: DiscoverItem, profile: Counter[str]) -> float:
    profile_strength = min(sum(profile.values()) / 80, 1.0) if profile else 0.0
    return round(0.35 + _quality(item.vote_average) * 0.55 + profile_strength * 0.1, 3)


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


def _person_score(snapshot: RatingSnapshot | None, field: str, fallback: float | None) -> int | None:
    rating = getattr(snapshot, field, None) if snapshot else fallback
    if rating is None:
        return None
    return _pct(_quality(rating))


def _fear(snapshot: RatingSnapshot | None) -> int | None:
    if snapshot is None or snapshot.tanno_fear_factor is None:
        return None
    return int(round(snapshot.tanno_fear_factor))


def _combined_score(base: float, snapshot: RatingSnapshot | None, profile: str, fallback_rating: float | None, fear_factor: int) -> float:
    janno_rating = snapshot.janno_rating if snapshot and snapshot.janno_rating is not None else fallback_rating
    tanno_rating = snapshot.tanno_rating if snapshot and snapshot.tanno_rating is not None else fallback_rating
    janno = _quality(janno_rating)
    tanno = _quality(tanno_rating)
    fear = _fear01(fear_factor)
    if profile == "janno":
        return _score(base * 0.55 + janno * 0.45)
    if profile == "tanno":
        return _score(base * 0.50 + tanno * 0.60 - fear * 0.25)
    return _score(base * 0.45 + (janno + tanno) * 0.35 - fear * 0.20)


def _discover_profile_score(base: float, profile: str, fear_factor: int) -> float:
    fear = _fear01(fear_factor)
    if profile == "tanno":
        return _score(base - fear * 0.25)
    if profile == "both":
        return _score(base - fear * 0.12)
    return _score(base)


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


def _library_rec(item: LibraryItem, score: float, profile: str, favorite_genres: list[str], snapshot: RatingSnapshot | None, fear_factor: int) -> RecommendationItem:
    return RecommendationItem(
        id=_rec_id("library", item.id, profile), title=item.title, type=item.type, year=item.year,
        overview=item.overview, poster_url=item.poster_url, backdrop_url=item.backdrop_url,
        score=round(score, 3), reason=_reason_for_library(item, favorite_genres, snapshot, profile),
        status="playable", library_id=item.id, community_rating=item.community_rating, critic_rating=item.critic_rating,
        match_score=_pct(score), janno_score=_person_score(snapshot, "janno_rating", item.user_rating),
        tanno_score=_person_score(snapshot, "tanno_rating", item.user_rating), fear_factor=fear_factor,
        profile=profile, category_tags=_tags(item.type, favorite_genres, fear_factor),
    )


def _discover_rec(item: DiscoverItem, score: float, profile: str, favorite_genres: list[str]) -> RecommendationItem:
    fear_factor = _estimated_discover_fear(item)
    return RecommendationItem(
        id=_rec_id("tmdb", item.tmdb_id, profile), title=item.title, type=item.type, year=item.year,
        overview=item.overview, poster_url=item.poster_url, backdrop_url=item.backdrop_url,
        score=round(score, 3), reason=_reason_for_discover(item, favorite_genres, profile), status="requestable",
        tmdb_id=item.tmdb_id, community_rating=item.vote_average, match_score=_pct(score),
        janno_score=None, tanno_score=None,
        fear_factor=fear_factor, profile=profile, category_tags=_tags(item.type, favorite_genres, fear_factor),
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

    # Profiles are independent of the shelf being built, so derive them once.
    j_profile, j_favorites, liked_j = _profile(library_items, snapshots, "janno")
    t_profile, t_favorites, liked_t = _profile(library_items, snapshots, "tanno")

    for profile, title in [("both", "Für euch beide"), ("janno", "Jannos Profil"), ("tanno", "Tannos Profil")]:
        active_profile = j_profile + t_profile if profile == "both" else (j_profile if profile == "janno" else t_profile)
        favorites = [genre for genre, _ in active_profile.most_common(3)] or (j_favorites + t_favorites)[:3]

        library_recs = []
        for item in library_items:
            snapshot = snapshot_by_item.get(_item_key(item))
            base = _library_score(item, active_profile)
            fear_factor = _estimated_library_fear(item, snapshot)
            library_recs.append(_library_rec(item, _combined_score(base, snapshot, profile, item.user_rating, fear_factor), profile, favorites, snapshot, fear_factor))
        library_recs.sort(key=lambda item: item.score, reverse=True)

        new_recs = [
            _discover_rec(item, _discover_profile_score(_discover_score(item, active_profile), profile, _estimated_discover_fear(item)), profile, favorites)
            for item in discover_items
            if (item.type, item.tmdb_id) not in owned_tmdb
        ]
        new_recs.sort(key=lambda item: item.score, reverse=True)

        # Reserve a few slots for playable library titles so a full discover
        # page can't crowd them out; fill the remainder by score.
        lib_quota = min(len(library_recs), max(1, limit // 3))
        reserved = library_recs[:lib_quota]
        remainder = sorted(new_recs + library_recs[lib_quota:], key=lambda item: item.score, reverse=True)
        items = sorted(reserved + remainder[: limit - len(reserved)], key=lambda item: item.score, reverse=True)
        if anthropic is not None:
            try:
                items = await anthropic.improve(items, liked_j + liked_t)
                llm_used = True
            except AnthropicError as exc:
                logger.warning("Anthropic recommendation polish failed: %s", exc.message)
                pass
        shelves.append(RecommendationShelf(id=profile, title=title, profile=profile, items=items))

    return RecommendationResponse(shelves=shelves, llm_used=llm_used)
