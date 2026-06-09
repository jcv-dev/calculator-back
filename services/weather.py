import os
import httpx
from dotenv import load_dotenv
from services.cache import cache_get, cache_set

load_dotenv()

WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

TULUA_LAT = 4.0847
TULUA_LON = -76.1954

WEATHER_FALLBACK = {
    "is_raining": False,
    "icon": "01d",
    "description": "",
    "condition_id": 0,
    "main": "",
}

FORCE_RAIN = {
    "is_raining": True,
    "icon": "10d",
    "description": "lluvia moderada",
    "condition_id": 501,
    "main": "Rain",
}


async def check_rain(api_key: str | None = None) -> dict:
    if os.getenv("FORCE_RAIN", "").lower() in ("true", "1", "yes"):
        return dict(FORCE_RAIN)

    key = api_key or os.getenv("OPENWEATHER_API_KEY", "")
    if not key:
        return dict(WEATHER_FALLBACK)

    cached = cache_get("weather")
    if cached is not None:
        return cached

    params = {
        "lat": TULUA_LAT,
        "lon": TULUA_LON,
        "appid": key,
        "units": "metric",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(WEATHER_URL, params=params, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()

        weather_list = data.get("weather", [])
        if not weather_list:
            cache_set("weather", WEATHER_FALLBACK)
            return dict(WEATHER_FALLBACK)

        w = weather_list[0]
        main_condition = w.get("main", "")
        condition_id = w.get("id", 0)
        icon = w.get("icon", "01d")
        description = w.get("description", "")

        is_raining = main_condition == "Rain" and str(condition_id) != "500"

        result = {
            "is_raining": is_raining,
            "icon": icon,
            "description": description,
            "condition_id": condition_id,
            "main": main_condition,
        }
        cache_set("weather", result)
        return result
    except Exception:
        pass

    return dict(WEATHER_FALLBACK)
