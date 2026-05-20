import os
import httpx
from dotenv import load_dotenv
from services.cache import cache_get, cache_set

load_dotenv()

WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

TULUA_LAT = 4.0847
TULUA_LON = -76.1954


async def check_rain(api_key: str | None = None) -> bool:
    key = api_key or os.getenv("OPENWEATHER_API_KEY", "")
    if not key:
        return False

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
            return False

        w = weather_list[0]
        main_condition = w.get("main", "")
        condition_id = w.get("id", 0)
        result = main_condition == "Rain" or str(condition_id).startswith("5")
        cache_set("weather", result)
        return result
    except Exception:
        pass

    return False
