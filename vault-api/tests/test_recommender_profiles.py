"""Profile recommender edge cases flagged in review (PR #28)."""
import asyncio

from models import DiscoverItem, LibraryItem, RatingSnapshot
from services.recommender import build_recommendations


def _run(coro):
    return asyncio.run(coro)


def test_library_recs_survive_discover_flood():
    # A full discover page must not crowd playable library titles out of a shelf.
    library = [LibraryItem(id="m1", type="Movie", title="Owned Gem", genres=["Drama"],
                           user_rating=9, community_rating=8.0, tmdb_id=1)]
    discover = [DiscoverItem(tmdb_id=100 + i, type="Movie", title=f"New {i}", vote_average=9.0)
                for i in range(30)]
    result = _run(build_recommendations(library, discover, None, limit=12))
    both = next(s for s in result.shelves if s.id == "both")
    assert any(i.status == "playable" and i.title == "Owned Gem" for i in both.items)


def test_newest_snapshot_wins_for_tmdb_match():
    # Same TMDB title rated twice (e.g. deleted + re-added) → newest rating wins.
    library = [LibraryItem(id="m2", type="Movie", title="Re-added", genres=["Drama"], tmdb_id=42)]
    newest = RatingSnapshot(item_id="new", title="Re-added", type="Movie", tmdb_id=42,
                            janno_rating=9, tanno_rating=9, updated_at="2026-06-14T18:00:00Z")
    oldest = RatingSnapshot(item_id="old", title="Re-added", type="Movie", tmdb_id=42,
                            janno_rating=2, tanno_rating=2, updated_at="2026-01-01T00:00:00Z")
    result = _run(build_recommendations(library, [], None, limit=12, snapshots=[newest, oldest]))
    both = next(s for s in result.shelves if s.id == "both")
    rec = next(i for i in both.items if i.title == "Re-added")
    assert rec.janno_score == 90  # newest 9/10 → 90, not the oldest's 2/10 → 20


def test_match_scores_stay_normalized_with_large_profiles():
    library = [
        LibraryItem(id=f"m{i}", type="Movie", title=f"Action {i}", genres=["Action"],
                    user_rating=8, community_rating=8, played=True, tmdb_id=i)
        for i in range(80)
    ]
    library.append(LibraryItem(id="quiet", type="Movie", title="Quiet Drama", genres=["Drama"],
                               community_rating=6, tmdb_id=999))

    result = _run(build_recommendations(library, [], None, limit=12))
    both = next(s for s in result.shelves if s.id == "both")

    assert all(0 <= item.score <= 1 for item in both.items)
    assert any((item.match_score or 0) < 100 for item in both.items)


def test_fear_factor_is_estimated_for_discover_items_and_penalizes_tanno():
    horror = DiscoverItem(tmdb_id=1, type="Movie", title="Haunted House",
                          overview="A demon turns a family home into a nightmare.",
                          vote_average=8.0, genre_ids=[27])
    comedy = DiscoverItem(tmdb_id=2, type="Movie", title="Sunny Weekend",
                           overview="Friends plan a harmless summer party.",
                           vote_average=8.0, genre_ids=[35])

    result = _run(build_recommendations([], [horror, comedy], None, limit=12))
    tanno = next(s for s in result.shelves if s.id == "tanno")
    horror_rec = next(i for i in tanno.items if i.title == "Haunted House")
    comedy_rec = next(i for i in tanno.items if i.title == "Sunny Weekend")

    assert horror_rec.fear_factor == 9
    assert comedy_rec.fear_factor == 0
    assert horror_rec.score < comedy_rec.score
