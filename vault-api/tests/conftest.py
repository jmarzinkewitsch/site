"""Test fixtures: an in-memory cache, a fake Jellyfin, and a wired TestClient."""
from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

import deps
from config import ConfigStore
from doubles import InMemoryCache
from main import create_app
from models import LibraryItem, StreamInfo
from services.podcast_store import PodcastStore
from services.rating_store import RatingStore


def pytest_collection_modifyitems(items):
    """Run async tests through AnyIO in environments without pytest-asyncio."""
    for item in items:
        if inspect.iscoroutinefunction(item.obj):
            item.add_marker(pytest.mark.anyio)


class FakeJellyfin:
    """Records calls so tests can assert caching/invalidation behaviour."""

    def __init__(self) -> None:
        self.movies_calls = 0
        self.latest_calls = 0
        self.next_up_calls = 0
        self.seasons_calls = 0
        self.episodes_calls = 0
        self.progress_calls: list[tuple] = []
        self.ratings: list[tuple] = []
        self.watched_calls: list[tuple[str, bool]] = []
        self.item_error: Exception | None = None
        self.movies_error: Exception | None = None
        self.progress_error: Exception | None = None
        self.watched_error: Exception | None = None
        self._item = LibraryItem(id="m1", type="Movie", title="Blade Runner", year=1982, runtime_seconds=4628.96)
        self.season_list = [LibraryItem(id="season1", type="Season", title="Season 1", series_id="s1", index_number=1)]
        self.episode_map = {
            "season1": [LibraryItem(
                id="e1", type="Episode", title="Good News About Hell",
                series_id="s1", season_id="season1", series_name="Severance",
                parent_index_number=1, index_number=1, episode_code="S1 E1",
                runtime_seconds=3420,
            )]
        }

    async def movies(self, start: int = 0, limit: int = 100):
        if self.movies_error:
            raise self.movies_error
        self.movies_calls += 1
        return [self._item]

    async def series(self, start: int = 0, limit: int = 100):
        return [LibraryItem(id="s1", type="Series", title="Severance")]

    async def latest(self, include_type: str, limit: int = 16):
        self.latest_calls += 1
        return [LibraryItem(id="new1", type=include_type, title="Freshly Added")]

    async def seasons(self, series_id: str):
        self.seasons_calls += 1
        return [season.model_copy(update={"series_id": series_id}) for season in self.season_list]

    async def episodes(self, series_id: str, season_id: str):
        self.episodes_calls += 1
        return [episode.model_copy(update={"series_id": series_id, "season_id": season_id}) for episode in self.episode_map.get(season_id, [])]

    async def continue_watching(self, limit: int = 12):
        return [self._item]

    async def next_up(self, limit: int = 24):
        self.next_up_calls += 1
        return [LibraryItem(
            id="e2", type="Episode", title="Half Loop",
            series_id="s1", season_id="season1", series_name="Severance",
            parent_index_number=1, index_number=2, episode_code="S1 E2",
            runtime_seconds=3300, played_percentage=25,
            poster_url="http://jf.local/Items/e2/Images/Primary?tag=p",
            backdrop_url="http://jf.local/Items/e2/Images/Backdrop?tag=b",
        )]

    async def search(self, term: str, limit: int = 24):
        return [self._item]

    async def shelf(
        self,
        *,
        include_type: str = "Movie",
        sort: str = "top_rated",
        genres: list[str] | None = None,
        unplayed: bool = False,
        limit: int = 16,
    ):
        self.shelf_calls = getattr(self, "shelf_calls", 0) + 1
        self.last_shelf_args = {
            "include_type": include_type,
            "sort": sort,
            "genres": genres,
            "unplayed": unplayed,
            "limit": limit,
        }
        return [self._item]

    async def item(self, item_id: str):
        if self.item_error:
            raise self.item_error
        return self._item

    async def report_progress(self, item_id, position_seconds, is_paused, media_source_id=None):
        if self.progress_error:
            raise self.progress_error
        self.progress_calls.append((item_id, position_seconds, is_paused, media_source_id))
        played_percentage = None
        if self._item.runtime_seconds:
            played_percentage = position_seconds / self._item.runtime_seconds * 100
        self._item = self._item.model_copy(update={
            "id": item_id,
            "resume_position_seconds": position_seconds,
            "played_percentage": played_percentage,
        })

    async def set_rating(self, item_id, rating):
        self.ratings.append((item_id, rating))

    async def stream(self, item_id, media_source_id=None, audio_stream_index=None):
        suffix = f"&audioStreamIndex={audio_stream_index}" if audio_stream_index is not None else ""
        return StreamInfo(
            url=f"http://jellyfin.local/Videos/{item_id}/stream?static=true&api_key=k{suffix}",
            audio_tracks=[
                {"index": 1, "language": "deu", "codec": "aac", "channels": 2, "display_title": "Deutsch AAC Stereo"},
                {"index": 2, "language": "eng", "codec": "eac3", "channels": 6, "display_title": "English EAC3 5.1"},
            ],
        )

    async def mark_played(self, item_id):
        if self.watched_error:
            raise self.watched_error
        self.watched_calls.append((item_id, True))

    async def mark_unplayed(self, item_id):
        if self.watched_error:
            raise self.watched_error
        self.watched_calls.append((item_id, False))


BEARER = "test-bearer-token"


@pytest.fixture
def store(tmp_path) -> ConfigStore:
    s = ConfigStore(tmp_path / "config.json")
    s.update(
        bearer_token=BEARER,
        jellyfin={"base_url": "http://jf.local", "api_key": "k", "user_id": "u1"},
    )
    return s


@pytest.fixture
def fake_jellyfin() -> FakeJellyfin:
    return FakeJellyfin()


@pytest.fixture
def cache() -> InMemoryCache:
    return InMemoryCache()


@pytest.fixture
def rating_store(tmp_path) -> RatingStore:
    return RatingStore(tmp_path / "vault-test.db")


@pytest.fixture
def podcast_store(tmp_path) -> PodcastStore:
    return PodcastStore(tmp_path / "vault-test.db")


@pytest.fixture
def client(store, fake_jellyfin, cache, rating_store, podcast_store):
    app = create_app()
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_cache] = lambda: cache
    app.dependency_overrides[deps.get_jellyfin] = lambda: fake_jellyfin
    app.dependency_overrides[deps.get_rating_store] = lambda: rating_store
    app.dependency_overrides[deps.get_podcast_store] = lambda: podcast_store
    with TestClient(app) as c:
        c.fake_jellyfin = fake_jellyfin
        c.cache = cache
        c.rating_store = rating_store
        c.podcast_store = podcast_store
        yield c


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {BEARER}"}
