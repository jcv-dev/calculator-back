import hashlib
import json
from cachetools import TTLCache

CACHE_CONFIG = {
    "geocode": {"ttl": 604800, "maxsize": 2000},
    "osrm": {"ttl": 2592000, "maxsize": 2000},
    "places_search": {"ttl": 3600, "maxsize": 500},
    "places_details": {"ttl": 2592000, "maxsize": 2000},
    "weather": {"ttl": 900, "maxsize": 10},
}

_caches: dict[str, TTLCache] = {}


def _get_cache(namespace: str) -> TTLCache:
    if namespace not in _caches:
        cfg = CACHE_CONFIG.get(namespace, {"ttl": 3600, "maxsize": 1000})
        _caches[namespace] = TTLCache(maxsize=cfg["maxsize"], ttl=cfg["ttl"])
    return _caches[namespace]


def _make_key(*args, **kwargs) -> str:
    raw = json.dumps((args, tuple(sorted(kwargs.items()))), sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_get(namespace: str, *args, **kwargs):
    cache = _get_cache(namespace)
    key = _make_key(namespace, *args, **kwargs)
    return cache.get(key)


def cache_set(namespace: str, value, *args, **kwargs):
    cache = _get_cache(namespace)
    key = _make_key(namespace, *args, **kwargs)
    cache[key] = value


def cache_clear(namespace: str | None = None):
    if namespace:
        cache = _caches.get(namespace)
        if cache:
            cache.clear()
    else:
        _caches.clear()
