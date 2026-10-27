"""WeatherAPI.com client. Free plan: 3 forecast days, 100K calls/month."""

import os
from datetime import datetime, timezone

import requests

BASE_URL = "https://api.weatherapi.com/v1"
TIMEOUT = 10
FORECAST_DAYS = 3


class WeatherAPIError(Exception):
    """Any failure talking to WeatherAPI (HTTP error, network error, missing key, no data)."""


def _to_utc(when):
    if isinstance(when, str):
        when = datetime.fromisoformat(when.replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when


def get_forecast(lat, lon, when) -> dict:
    """Forecast for the hour closest to `when` (aware datetime or ISO string).

    Returns {temp_c, precip_mm, wind_kph, condition_text}.
    """
    key = os.environ.get("WEATHERAPI_KEY")
    if not key:
        raise WeatherAPIError(0, "WEATHERAPI_KEY is not set")
    target = _to_utc(when).timestamp()
    try:
        resp = requests.get(
            f"{BASE_URL}/forecast.json",
            params={
                "key": key,
                "q": f"{float(lat)},{float(lon)}",
                "days": FORECAST_DAYS,
                "aqi": "no",
                "alerts": "no",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise WeatherAPIError(0, f"request failed: {type(exc).__name__}") from exc
    if resp.status_code != 200:
        raise WeatherAPIError(resp.status_code, resp.text[:200])
    try:
        body = resp.json()
    except ValueError as exc:
        raise WeatherAPIError(resp.status_code, "response was not JSON") from exc
    return _normalize(body, target)


def _normalize(body, target_epoch):
    hours = [
        h
        for day in (body.get("forecast") or {}).get("forecastday") or []
        for h in day.get("hour") or []
    ]
    if not hours:
        raise WeatherAPIError(200, "no hourly forecast in response")
    best = min(hours, key=lambda h: abs(h["time_epoch"] - target_epoch))
    # Refuse to answer with an hour that is far from kickoff (outside the forecast window).
    if abs(best["time_epoch"] - target_epoch) > 3 * 3600:
        raise WeatherAPIError(200, "kickoff is outside the forecast window")
    return {
        "temp_c": best.get("temp_c"),
        "precip_mm": best.get("precip_mm") or 0.0,
        "wind_kph": best.get("wind_kph") or 0.0,
        "condition_text": (best.get("condition") or {}).get("text", ""),
    }
