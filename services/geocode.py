import httpx
import os
from dotenv import load_dotenv
from services.cache import cache_get, cache_set

load_dotenv()

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


async def geocode_address(address: str) -> tuple[float, float]:
    query = address.strip()

    cached = cache_get("geocode", query)
    if cached is not None:
        return tuple(cached)

    # Append Tuluá context if the query is short/ambiguous (no commas, short string)
    if "," not in query and len(query.split()) <= 2:
        query = f"{query}, Tuluá, Colombia"

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
            raise ValueError(f"Address not found: {address}")
        loc = data["results"][0]["geometry"]["location"]
        result = (loc["lat"], loc["lng"])
        cache_set("geocode", result, address)
        return result
