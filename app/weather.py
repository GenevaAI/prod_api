from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from enum import Enum
from typing import Optional
import requests
from datetime import datetime, timedelta
import time


# Create a router instead of a full FastAPI app
router = APIRouter(
    tags=["Weather"]            # nice grouping in the docs
)

# Simple in-memory cache: { (lat, lon, unit): (timestamp, data) }
_weather_cache = {}
CACHE_MINUTES = 10          # cache results for 10 minutes

# ------------------------------------------------------------------
# WMO Weather interpretation codes (used by Open-Meteo)
# ------------------------------------------------------------------
WMO_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class TemperatureUnit(str, Enum):
    celsius = "celsius"
    fahrenheit = "fahrenheit"

def get_client_ip(request: Request) -> str:
    """
    Get the real client IP address.
    Handles common proxy headers used by Render, Cloudflare, etc.
    """
    # Cloudflare
    if cf_ip := request.headers.get("cf-connecting-ip"):
        return cf_ip

    # Standard proxy header – take the first (original) IP
    if xff := request.headers.get("x-forwarded-for"):
        # Render and most proxies put the real client IP first
        return xff.split(",")[0].strip()

    # Some proxies use this
    if real_ip := request.headers.get("x-real-ip"):
        return real_ip

    # Direct connection
    if request.client:
        return request.client.host

    return "127.0.0.1"

def get_location_from_ip(ip: str) -> dict:
    """
    Robust geolocation that works on both local development and Render.
    Tries several strategies and finally falls back to a default location
    so the page never completely fails.
    """
    def _call_ipinfo(url: str) -> dict:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        if data.get("bogon"):
            raise ValueError("Private/bogon IP")

        loc = data.get("loc", "").split(",")
        if len(loc) != 2:
            raise ValueError("No coordinates returned")

        return {
            "ip": data.get("ip", ip),
            "city": data.get("city") or "Unknown",
            "region": data.get("region") or "",
            "country": data.get("country") or "",
            "latitude": float(loc[0]),
            "longitude": float(loc[1]),
        }

    # ---------- Strategy 1: try the real client IP ----------
    try:
        if ip and not (ip in ("127.0.0.1", "::1", "localhost") or ip.startswith(("10.", "172.", "192.168."))):
            return _call_ipinfo(f"https://ipinfo.io/{ip}/json")
    except Exception:
        pass  # fall through to next strategy

    # ---------- Strategy 2: ask ipinfo for the public IP of this server ----------
    try:
        return _call_ipinfo("https://ipinfo.io/json")
    except Exception:
        pass  # fall through to final fallback

    # ---------- Final fallback (so the page never breaks) ----------
    return {
        "ip": ip or "unknown",
        "city": "New York",
        "region": "New York",
        "country": "US",
        "latitude": 40.7128,
        "longitude": -74.0060,
    }

def get_weather(lat: float, lon: float, unit: TemperatureUnit) -> dict:
    """
    Fetch current weather.
    1. Try Open-Meteo (with cache)
    2. If it fails (especially 429), fall back to wttr.in
    """
    cache_key = (round(lat, 2), round(lon, 2), unit.value)

    # Return cached result if still fresh
    if cache_key in _weather_cache:
        cached_time, cached_data = _weather_cache[cache_key]
        if datetime.utcnow() - cached_time < timedelta(minutes=CACHE_MINUTES):
            return cached_data

    # -------------------------------------------------
    # 1. Try Open-Meteo
    # -------------------------------------------------
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,weather_code,wind_speed_10m,wind_direction_10m"
            ),
            "temperature_unit": unit.value,
            "wind_speed_unit": "kmh",
            "timezone": "auto",
        }
        headers = {
            "User-Agent": "WeatherApp/1.0 (https://prod-api-yrml.onrender.com)"
        }

        resp = requests.get(url, params=params, headers=headers, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})

        code = current.get("weather_code")
        current["weather_description"] = WMO_WEATHER_CODES.get(
            code, f"Unknown weather code ({code})"
        )

        # Cache and return
        _weather_cache[cache_key] = (datetime.utcnow(), current)
        return current

    except Exception as e:
        # Open-Meteo failed → try fallback
        print(f"Open-Meteo failed: {e}. Trying wttr.in fallback...")

    # -------------------------------------------------
    # 2. Fallback: wttr.in (free, no key required)
    # -------------------------------------------------
    try:
        # wttr.in uses °C by default. We'll convert if needed.
        url = f"https://wttr.in/{lat},{lon}?format=j1"
        headers = {
            "User-Agent": "WeatherApp/1.0 (https://prod-api-yrml.onrender.com)"
        }

        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        data = resp.json()

        current_condition = data["current_condition"][0]

        temp_c = float(current_condition["temp_C"])
        feels_c = float(current_condition["FeelsLikeC"])
        humidity = int(current_condition["humidity"])
        precip = float(current_condition["precipMM"])
        wind_kmh = float(current_condition["windspeedKmph"])
        desc = current_condition["weatherDesc"][0]["value"]

        # Convert to Fahrenheit if requested
        if unit == TemperatureUnit.fahrenheit:
            temp = temp_c * 9/5 + 32
            feels = feels_c * 9/5 + 32
        else:
            temp = temp_c
            feels = feels_c

        result = {
            "temperature_2m": round(temp, 1),
            "apparent_temperature": round(feels, 1),
            "relative_humidity_2m": humidity,
            "precipitation": precip,
            "weather_code": None,
            "weather_description": desc,
            "wind_speed_10m": wind_kmh,
            "wind_direction_10m": None,
        }

        # Cache the fallback result too
        _weather_cache[cache_key] = (datetime.utcnow(), result)
        return result

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Both weather services failed. Last error: {str(e)}"
        )

@router.get("/weather")
async def weather_at_client_location(
    request: Request,
    unit: TemperatureUnit = Query(
        default=TemperatureUnit.celsius,
        description="Temperature unit: celsius or fahrenheit",
    ),
):
    try:
        client_ip = get_client_ip(request)
        location = get_location_from_ip(client_ip)

        lat = location.get("latitude")
        lon = location.get("longitude")

        if lat is None or lon is None:
            raise HTTPException(
                status_code=400,
                detail="Could not determine coordinates from the client IP",
            )

        weather = get_weather(lat, lon, unit)

        return {
            "client_ip": client_ip,
            "location": {
                "city": location.get("city"),
                "region": location.get("region"),
                "country": location.get("country"),
                "latitude": lat,
                "longitude": lon,
            },
            "unit": unit.value,
            "weather": weather,
        }
    except HTTPException:
        raise
    except Exception as e:
        # This will show the real error in the response
        raise HTTPException(status_code=502, detail=f"Unexpected error: {type(e).__name__}: {str(e)}")

@router.get("/weather-page", response_class=HTMLResponse)
async def weather_page():
    """
    Friendly HTML page that shows the weather.
    Access it at: /weather/page
    """
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Current Weather</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #74b9ff, #0984e3);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
            color: #2d3436;
        }
        .card {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.15);
            padding: 40px;
            max-width: 420px;
            width: 100%;
            text-align: center;
        }
        .location {
            font-size: 1.4rem;
            font-weight: 600;
            margin-bottom: 5px;
        }
        .country {
            color: #636e72;
            margin-bottom: 25px;
        }
        .temp {
            font-size: 4.5rem;
            font-weight: 300;
            line-height: 1;
            margin: 10px 0;
        }
        .desc {
            font-size: 1.3rem;
            text-transform: capitalize;
            margin-bottom: 30px;
            color: #2d3436;
        }
        .details {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            text-align: left;
        }
        .detail {
            background: #f5f6fa;
            padding: 12px 15px;
            border-radius: 12px;
        }
        .detail span {
            display: block;
            font-size: 0.85rem;
            color: #636e72;
        }
        .detail strong {
            font-size: 1.1rem;
        }
        .loading, .error {
            font-size: 1.2rem;
            padding: 40px 20px;
        }
        .error { color: #d63031; }
        .unit-toggle {
            margin-top: 25px;
            display: flex;
            gap: 10px;
            justify-content: center;
        }
        button {
            padding: 8px 18px;
            border: none;
            border-radius: 30px;
            background: #0984e3;
            color: white;
            font-size: 0.95rem;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover { background: #74b9ff; }
        button.active { background: #2d3436; }
    </style>
</head>
<body>
    <div class="card">
        <div id="content">
            <div class="loading">Loading weather...</div>
        </div>

        <div class="unit-toggle">
            <button id="btn-c" class="active" onclick="loadWeather('celsius')">°C</button>
            <button id="btn-f" onclick="loadWeather('fahrenheit')">°F</button>
        </div>
    </div>

    <script>
        async function loadWeather(unit = 'celsius') {
            // Update active button
            document.getElementById('btn-c').classList.toggle('active', unit === 'celsius');
            document.getElementById('btn-f').classList.toggle('active', unit === 'fahrenheit');

            const content = document.getElementById('content');
            content.innerHTML = '<div class="loading">Loading weather...</div>';

            try {
                const res = await fetch(`/weather?unit=${unit}`);
                if (!res.ok) throw new Error('Failed to load weather');

                const data = await res.json();

                const loc = data.location;
                const w = data.weather;

                content.innerHTML = `
                    <div class="location">${loc.city || 'Unknown city'}</div>
                    <div class="country">${loc.region || ''} ${loc.country || ''}</div>

                    <div class="temp">${Math.round(w.temperature_2m)}°</div>
                    <div class="desc">${w.weather_description || '—'}</div>

                    <div class="details">
                        <div class="detail">
                            <span>Feels like</span>
                            <strong>${Math.round(w.apparent_temperature)}°</strong>
                        </div>
                        <div class="detail">
                            <span>Humidity</span>
                            <strong>${w.relative_humidity_2m}%</strong>
                        </div>
                        <div class="detail">
                            <span>Wind</span>
                            <strong>${w.wind_speed_10m} km/h</strong>
                        </div>
                        <div class="detail">
                            <span>Precipitation</span>
                            <strong>${w.precipitation} mm</strong>
                        </div>
                    </div>
                `;
            } catch (err) {
                content.innerHTML = `<div class="error">Could not load weather data.<br>${err.message}</div>`;
            }
        }

        // Load on page open
        loadWeather('celsius');
    </script>
</body>
</html>
"""