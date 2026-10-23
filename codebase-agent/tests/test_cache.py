import pytest
from cache.redis_cache import Cache


def _make_cache():
    cache = Cache(host="localhost", port=6379, db=1)
    try:
        cache.client.ping()
    except Exception:
        pytest.skip("Redis not available")
    return cache


def test_cache_set_and_get():
    cache = _make_cache()
    try:
        cache.set("test_key", "hello world", ttl=60)
        assert cache.get("test_key") == "hello world"
    finally:
        cache.clear_db()
        cache.close()