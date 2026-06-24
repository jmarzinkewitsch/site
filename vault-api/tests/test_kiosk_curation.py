import deps
from models import LibraryItem
from services.kiosk_curation import curate_kiosk_shelf


def _episode(item_id: str, title: str, series_id: str, series_name: str) -> LibraryItem:
    return LibraryItem(
        id=item_id,
        type="Episode",
        title=title,
        series_id=series_id,
        series_name=series_name,
    )


def _movie(item_id: str, title: str) -> LibraryItem:
    return LibraryItem(id=item_id, type="Movie", title=title)


def _series(item_id: str, title: str) -> LibraryItem:
    return LibraryItem(id=item_id, type="Series", title=title)


def test_curate_kiosk_shelf_keeps_at_most_one_episode_per_series():
    shelf = curate_kiosk_shelf(
        continue_watching=[
            _episode("s1-e1", "Severance 1", "s1", "Severance"),
            _episode("s1-e2", "Severance 2", "s1", "Severance"),
        ],
        next_up=[
            _episode("s1-e3", "Severance 3", "s1", "Severance"),
            _episode("s2-e1", "Silo 1", "s2", "Silo"),
        ],
        latest_movies=[],
        latest_series=[],
        spotlight=[],
        limit=8,
    )

    assert [item.id for item in shelf] == ["s1-e1", "s2-e1"]


def test_curate_kiosk_shelf_promotes_movies_before_episode_wall():
    shelf = curate_kiosk_shelf(
        continue_watching=[
            _episode("s1-e1", "Severance 1", "s1", "Severance"),
            _episode("s2-e1", "Silo 1", "s2", "Silo"),
            _episode("s3-e1", "Andor 1", "s3", "Andor"),
            _episode("s4-e1", "Foundation 1", "s4", "Foundation"),
        ],
        next_up=[
            _episode("s5-e1", "Shrinking 1", "s5", "Shrinking"),
            _episode("s6-e1", "Slow Horses 1", "s6", "Slow Horses"),
        ],
        latest_movies=[
            _movie("m1", "Blade Runner"),
            _movie("m2", "Arrival"),
        ],
        latest_series=[_series("series-1", "The Last of Us")],
        spotlight=[_movie("m3", "Dune")],
        limit=8,
    )

    assert [item.id for item in shelf[:5]] == ["s1-e1", "m1", "s2-e1", "s3-e1", "m2"]
    assert [item.type for item in shelf].count("Movie") >= 2


class _CuratedOverviewJellyfin:
    async def continue_watching(self, limit=8):
        return [
            _episode("s1-e1", "Severance 1", "s1", "Severance"),
            _episode("s1-e2", "Severance 2", "s1", "Severance"),
            _episode("s2-e1", "Silo 1", "s2", "Silo"),
        ]

    async def next_up(self, limit=8):
        return [
            _episode("s1-e3", "Severance 3", "s1", "Severance"),
            _episode("s3-e1", "Andor 1", "s3", "Andor"),
        ]

    async def latest(self, include_type, limit):
        if include_type == "Movie":
            return [_movie("m1", "Blade Runner"), _movie("m2", "Arrival")]
        return [_series("series-1", "The Last of Us")]

    async def shelf(self, *, include_type="Movie", sort="random", unplayed=False, limit=12):
        return [_movie("m3", "Dune")]


def test_kiosk_media_overview_uses_curated_shelf(client, store):
    store.update(kiosk_token="kiosk-media-token", jellyfin={"base_url": "http://jf", "api_key": "x", "user_id": "u"})
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: _CuratedOverviewJellyfin()
    try:
        response = client.get("/kiosk/media/overview", headers={"Authorization": "Bearer kiosk-media-token"})
    finally:
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)

    assert response.status_code == 200
    body = response.json()

    curated_titles = [item["title"] for item in body["continue_watching"]]
    curated_types = [item["type"] for item in body["continue_watching"]]

    assert curated_titles[:5] == ["Severance 1", "Blade Runner", "Silo 1", "Andor 1", "Arrival"]
    assert "Severance 2" not in curated_titles
    assert "Severance 3" not in curated_titles
    assert curated_types.count("Movie") >= 2
