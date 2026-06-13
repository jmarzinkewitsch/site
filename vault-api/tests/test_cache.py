import pytest

from cache import TTL, Cache


async def test_no_redis_degrades_to_noop():
    cache = Cache(url=None)
    assert await cache.connect() is False
    assert await cache.ping() is False
    # All operations are safe no-ops when there is no backend.
    assert await cache.get_json("k") is None
    await cache.set_json("k", {"a": 1}, ttl=60)
    assert await cache.get_json("k") is None
    await cache.invalidate("k")
    await cache.invalidate_prefix("lib:")
    await cache.close()


async def test_unreachable_redis_does_not_raise():
    # A bogus port: connect fails cleanly, client stays None.
    cache = Cache(url="redis://127.0.0.1:1/0")
    assert await cache.connect() is False
    await cache.set_json("k", 1, 10)  # must not raise


def test_ttl_constants_match_doc():
    assert TTL.LIBRARY == 15 * 60
    assert TTL.ITEM == 60 * 60
    assert TTL.TMDB == 7 * 24 * 3600
    assert TTL.ARR_QUEUE == 30
