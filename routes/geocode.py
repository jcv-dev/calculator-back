import logging
import httpx
from fastapi import APIRouter, Query, HTTPException
import os
from dotenv import load_dotenv

from services.cache import cache_get, cache_set

load_dotenv()

logger = logging.getLogger("geocode")

router = APIRouter(prefix="/api/geocode")

GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

TULUA_LAT = 4.0847
TULUA_LNG = -76.1954
BIAS_RADIUS = 50000


@router.get("/search")
async def search_address(
    q: str = Query(..., min_length=2),
):
    if not q.strip():
        return []

    cached = cache_get("places_search", q.strip())
    if cached is not None:
        return cached

    if not GOOGLE_MAPS_KEY:
        logger.warning("GOOGLE_MAPS_API_KEY is not set — geocode search will return empty")
        raise HTTPException(
            status_code=503,
            detail="Google Maps API key not configured on server",
        )

    params = {
        "input": q.strip(),
        "components": "country:co",
        "location": f"{TULUA_LAT},{TULUA_LNG}",
        "radius": BIAS_RADIUS,
        "language": "es",
        "key": GOOGLE_MAPS_KEY,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(AUTOCOMPLETE_URL, params=params, timeout=8.0)
        resp.raise_for_status()
        data = resp.json()

    status = data.get("status", "")
    if status != "OK":
        logger.warning("Google Places Autocomplete returned status=%s for q=%r", status, q.strip())
        if status == "REQUEST_DENIED":
            raise HTTPException(
                status_code=503,
                detail="Google Maps API key is invalid or Places API not enabled",
            )
        if status == "OVER_QUERY_LIMIT":
            raise HTTPException(
                status_code=429,
                detail="Google Maps API quota exceeded",
            )
        return []

    result = [
        {"display_name": item.get("description", ""), "place_id": item.get("place_id", "")}
        for item in data.get("predictions", [])[:5]
    ]
    cache_set("places_search", result, q.strip())
    return result


@router.get("/details")
async def place_details(
    place_id: str = Query(...),
):
    if not GOOGLE_MAPS_KEY:
        raise HTTPException(503, "Google Maps API key not configured")

    cached = cache_get("places_details", place_id)
    if cached is not None:
        return cached

    params = {
        "place_id": place_id,
        "fields": "formatted_address,geometry",
        "language": "es",
        "key": GOOGLE_MAPS_KEY,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(DETAILS_URL, params=params, timeout=8.0)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "OK":
        raise HTTPException(404, "Place not found")

    result_data = data.get("result", {})
    result = {
        "display_name": result_data.get("formatted_address", ""),
        "lat": result_data["geometry"]["location"]["lat"],
        "lng": result_data["geometry"]["location"]["lng"],
    }
    cache_set("places_details", result, place_id)
    return result


@router.get("/reverse")
async def reverse_geocode(
    lat: float = Query(...),
    lng: float = Query(...),
):
    if not GOOGLE_MAPS_KEY:
        raise HTTPException(503, "Google Maps API key not configured")

    GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "latlng": f"{lat},{lng}",
        "language": "es",
        "key": GOOGLE_MAPS_KEY,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(GEOCODE_URL, params=params, timeout=10.0)
        data = resp.json()

    if data.get("status") != "OK" or not data.get("results"):
        return {"display_name": f"{lat:.4f}, {lng:.4f}", "lat": lat, "lng": lng}

    result_data = data["results"][0]
    loc = result_data["geometry"]["location"]
    return {
        "display_name": result_data.get("formatted_address", f"{lat:.4f}, {lng:.4f}"),
        "lat": loc["lat"],
        "lng": loc["lng"],
    }
