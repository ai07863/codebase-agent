from cache.redis_cache import Cache


def test_cache_set_and_get():
    cache = Cache(host="localhost", port=6379, db=1)
    cache.set("test_key", "hello world", ttl=60)
    value = cache.get("test_key")
    assert value == "hello world"
    cache.close()
    cache.clear_db()