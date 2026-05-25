import hashlib
import json
import logging
from cachetools import TTLCache

logger = logging.getLogger("cache")

CACHE_CONFIG = {
    "geocode": {"ttl": 604800, "maxsize": 500},
    "osrm": {"ttl": 2592000, "maxsize": 500},
    "places_search": {"ttl": 172800, "maxsize": 500},
    "places_details": {"ttl": 2592000, "maxsize": 500},
    "weather": {"ttl": 600, "maxsize": 10},
}

_caches: dict[str, TTLCache] = {}


def _get_cache(namespace: str) -> TTLCache:
    if namespace not in _caches:
        cfg = CACHE_CONFIG.get(namespace, {"ttl": 3600, "maxsize": 1000})
        _caches[namespace] = TTLCache(maxsize=cfg["maxsize"], ttl=cfg["ttl"])
        logger.info("cache=%s action=init maxsize=%d ttl=%d", namespace, cfg["maxsize"], cfg["ttl"])
    return _caches[namespace]


def _make_key(*args, **kwargs) -> str:
    raw = json.dumps((args, tuple(sorted(kwargs.items()))), sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def cache_get(namespace: str, *args, **kwargs):
    cache = _get_cache(namespace)
    key = _make_key(namespace, *args, **kwargs)
    value = cache.get(key)
    if value is not None:
        logger.debug("cache=%s key=%s action=hit size=%d/%d", namespace, key, cache.currsize, cache.maxsize)
    else:
        logger.debug("cache=%s key=%s action=miss size=%d/%d", namespace, key, cache.currsize, cache.maxsize)
    return value


def cache_set(namespace: str, value, *args, **kwargs):
    cache = _get_cache(namespace)
    key = _make_key(namespace, *args, **kwargs)
    cache[key] = value
    logger.debug("cache=%s key=%s action=set size=%d/%d", namespace, key, cache.currsize, cache.maxsize)


def cache_stats() -> dict:
    """Return current cache occupancy for all namespaces (useful for /api/health)."""
    return {
        ns: {"size": c.currsize, "maxsize": c.maxsize, "ttl": CACHE_CONFIG.get(ns, {}).get("ttl", 0)}
        for ns, c in _caches.items()
    }


def cache_clear(namespace: str | None = None):
    if namespace:
        cache = _caches.get(namespace)
        if cache:
            cache.clear()
            logger.info("cache=%s action=cleared", namespace)
    else:
        for c in _caches.values():
            c.clear()
        logger.info("cache=* action=cleared")
