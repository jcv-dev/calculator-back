import httpx
from services.cache import cache_get, cache_set

OSRM_URL = "http://router.project-osrm.org/route/v1/driving"


async def get_total_distance(coordinates: list[tuple[float, float]]) -> float:
    if len(coordinates) < 2:
        return 0.0

    loc_str = ";".join(f"{lng},{lat}" for lat, lng in coordinates)

    cached = cache_get("osrm", loc_str)
    if cached is not None:
        return cached

    url = f"{OSRM_URL}/{loc_str}"

    params = {
        "overview": "false",
        "steps": "false",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError(f"OSRM routing failed: {data.get('message', 'unknown error')}")

    distance_meters = data["routes"][0]["distance"]
    result = round(distance_meters / 1000.0, 2)
    cache_set("osrm", result, loc_str)
    return result
