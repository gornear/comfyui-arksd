import time
from nodes import routes


def test_cache_roundtrip():
    cache = routes.TTLCache(ttl=300)
    cache.put("k", [1, 2])
    assert cache.get("k") == [1, 2]


def test_cache_expires():
    cache = routes.TTLCache(ttl=0.01)
    cache.put("k", [1])
    time.sleep(0.05)
    assert cache.get("k") is None


def test_cache_force_refresh():
    cache = routes.TTLCache(ttl=300)
    cache.put("k", [1])
    cache.invalidate("k")
    assert cache.get("k") is None
