import asyncio
import math
import time
import httpx
import os
from dotenv import load_dotenv
from services.cache import cache_get, cache_set

load_dotenv()

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
NOMINATIM_ENABLED = os.getenv("NOMINATIM_ENABLED", "true").lower() in ("1", "true", "yes")

TULUA_CENTRO = (4.0847, -76.1954)
MAX_LOCAL_KM = 60

_nominatim_lock = asyncio.Lock()
_nominatim_last_call: float = 0


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _is_near_tulua(lat: float, lng: float) -> bool:
    return _haversine_km(lat, lng, *TULUA_CENTRO) <= MAX_LOCAL_KM


async def _geocode_google(query: str) -> tuple[float, float] | None:
    if not GOOGLE_MAPS_KEY:
        return None
    params = {
        "address": query,
        "region": "co",
        "bounds": "3.8,-76.6|4.4,-75.8",
        "language": "es",
        "key": GOOGLE_MAPS_KEY,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(GEOCODE_URL, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        loc = data["results"][0]["geometry"]["location"]
        return (loc["lat"], loc["lng"])


async def _geocode_nominatim(query: str) -> tuple[float, float] | None:
    if not NOMINATIM_ENABLED:
        return None

    global _nominatim_last_call
    async with _nominatim_lock:
        elapsed = time.time() - _nominatim_last_call
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        _nominatim_last_call = time.time()

        params = {"q": query, "format": "json", "limit": 1, "countrycodes": "co"}
        headers = {"User-Agent": "DomiiTulua/1.0"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(NOMINATIM_URL, params=params, headers=headers, timeout=10.0)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data:
                return None
            return (float(data[0]["lat"]), float(data[0]["lon"]))


async def geocode_address(address: str) -> tuple[float, float]:
    query = address.strip()

    cached = cache_get("geocode", query)
    if cached is not None:
        return tuple(cached)

    contextual = f"{query}, Tuluá, Colombia"

    engines = [
        ("google", lambda: _geocode_google(query)),
        ("google_contextual", lambda: _geocode_google(contextual)),
    ]
    if NOMINATIM_ENABLED:
        engines.append(("nominatim_contextual", lambda: _geocode_nominatim(contextual)))

    for name, fn in engines:
        result = await fn()
        if result is not None and _is_near_tulua(*result):
            cache_set("geocode", result, address)
            return result

    raise ValueError(f"Address not found near Tuluá: {address}")
