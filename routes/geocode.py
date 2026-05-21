import logging
import httpx
from fastapi import APIRouter, Query, HTTPException
import os
from dotenv import load_dotenv

from services.cache import cache_get, cache_set

load_dotenv()

logger = logging.getLogger("geocode")

router = APIRouter(prefix="/api/geocode")

_http_client = httpx.AsyncClient(timeout=10.0)


@router.on_event("shutdown")
async def shutdown():
    await _http_client.aclose()


GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

PLACES_API_BASE = "https://places.googleapis.com/v1"

TULUA_LAT = 4.0847
TULUA_LNG = -76.1954
BIAS_RADIUS = 50000


def _headers() -> dict:
    return {
        "X-Goog-Api-Key": GOOGLE_MAPS_KEY,
        "Content-Type": "application/json",
    }


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

    body = {
        "input": q.strip(),
        "locationBias": {
            "circle": {
                "center": {"latitude": TULUA_LAT, "longitude": TULUA_LNG},
                "radius": BIAS_RADIUS,
            }
        },
        "regionCode": "co",
        "languageCode": "es",
    }

    resp = await _http_client.post(
        f"{PLACES_API_BASE}/places:autocomplete",
        headers=_headers(),
        json=body,
    )

    if resp.status_code == 403:
        raise HTTPException(
            status_code=503,
            detail="Google Maps API key is invalid or Places API not enabled",
        )
    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="Google Maps API quota exceeded",
        )

    resp.raise_for_status()
    data = resp.json()

    suggestions = data.get("suggestions", [])
    result = []
    for s in suggestions:
        pred = s.get("placePrediction")
        if pred:
            result.append({
                "display_name": pred.get("text", {}).get("text", ""),
                "place_id": pred.get("placeId", ""),
            })

    result = result[:5]
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

    resp = await _http_client.get(
        f"{PLACES_API_BASE}/places/{place_id}",
        headers={
            "X-Goog-Api-Key": GOOGLE_MAPS_KEY,
            "X-Goog-FieldMask": "formattedAddress,location",
        },
    )

    if resp.status_code == 404:
        raise HTTPException(404, "Place not found")
    if resp.status_code == 403:
        raise HTTPException(503, "Google Maps API key is invalid or Places API not enabled")
    if resp.status_code == 429:
        raise HTTPException(429, "Google Maps API quota exceeded")

    resp.raise_for_status()
    place = resp.json()

    loc = place.get("location", {})
    result = {
        "display_name": place.get("formattedAddress", ""),
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
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

    resp = await _http_client.get(GEOCODE_URL, params=params)
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
