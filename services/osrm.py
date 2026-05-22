import asyncio
import os
import httpx
from services.cache import cache_get, cache_set

OSRM_ENDPOINTS = [
    os.getenv("OSRM_URL", "http://router.project-osrm.org/route/v1/driving"),
]

OSRM_TIMEOUT = float(os.getenv("OSRM_TIMEOUT", "10.0"))
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
GMAPS_DISTMATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


async def _google_distance(coordinates: list[tuple[float, float]]) -> float | None:
    if not GOOGLE_MAPS_KEY or len(coordinates) < 2:
        return None

    total_meters = 0
    async with httpx.AsyncClient() as client:
        for i in range(len(coordinates) - 1):
            lat1, lng1 = coordinates[i]
            lat2, lng2 = coordinates[i + 1]
            params = {
                "origins": f"{lat1},{lng1}",
                "destinations": f"{lat2},{lng2}",
                "mode": "driving",
                "key": GOOGLE_MAPS_KEY,
            }
            try:
                resp = await client.get(GMAPS_DISTMATRIX_URL, params=params, timeout=10.0)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") != "OK":
                    return None
                element = data["rows"][0]["elements"][0]
                if element["status"] != "OK":
                    return None
                total_meters += element["distance"]["value"]
            except Exception:
                return None

    return round(total_meters / 1000.0, 2)


async def _osrm_distance(coordinates: list[tuple[float, float]]) -> float:
    loc_str = ";".join(f"{lng},{lat}" for lat, lng in coordinates)
    params = {"overview": "false", "steps": "false"}

    last_error = None
    for attempt in range(3):
        for base_url in OSRM_ENDPOINTS:
            url = f"{base_url}/{loc_str}"
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, params=params, timeout=OSRM_TIMEOUT)
                    resp.raise_for_status()
                    data = resp.json()

                if data.get("code") != "Ok" or not data.get("routes"):
                    raise ValueError(f"OSRM routing failed: {data.get('message', 'unknown error')}")

                distance_meters = data["routes"][0]["distance"]
                result = round(distance_meters / 1000.0, 2)
                return result
            except Exception as exc:
                last_error = exc
                continue

        await asyncio.sleep(1.0 * (attempt + 1))

    raise type(last_error)(f"OSRM routing failed after retries: {last_error}") if last_error else RuntimeError("OSRM routing failed")


async def get_total_distance(coordinates: list[tuple[float, float]]) -> float:
    if len(coordinates) < 2:
        return 0.0

    loc_str = ";".join(f"{lng},{lat}" for lat, lng in coordinates)

    cached = cache_get("osrm", loc_str)
    if cached is not None:
        return cached

    try:
        result = await _osrm_distance(coordinates)
        cache_set("osrm", result, loc_str)
        return result
    except Exception:
        pass

    result = await _google_distance(coordinates)
    if result is not None:
        cache_set("osrm", result, loc_str)
        return result

    raise RuntimeError("All routing services failed — OSRM and Google Maps Distance Matrix are unreachable")
