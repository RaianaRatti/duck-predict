'''
Overall: Fetches weather data from Open-Meteo (free, no API key) for the CAISO representative point (see config.py). Two entry points:
  - fetch_weather_history(): 1-2 years of actual past weather -> persisted to DuckDB
  - fetch_weather_forecast(): next 48h forecast -> returned as a DataFrame, not persisted
    (the forecast API endpoint calls this live, so caching/persisting isn't needed here)

Unlike caiso.py, Open-Meteo's archive endpoint accepts a full multi-year date range in a single HTTP call (verified: 1 year = 8784 rows, one request). No day-by-day looping needed here.
'''

from __future__ import annotations

import sys
from datetime import date, timedelta

import pandas as pd
import requests

from ..config import WEATHER_LAT, WEATHER_LON
from .db import write_df

HOURLY_FIELDS = "temperature_2m,shortwave_radiation,wind_speed_10m,cloud_cover"

_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


# NOTE: Both endpoints (archive + forecast) return the same "hourly" JSON shape,
# so both fetch functions share this parser instead of duplicating the logic.
def _parse_hourly_response(payload: dict) -> pd.DataFrame:
    hourly = payload["hourly"]

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(hourly["time"], utc=True),
            "irradiance_w_m2": hourly["shortwave_radiation"],
            "wind_speed_ms": 
            [ # NOTE: Open-Meteo returns km/h; convert to m/s (standard met. unit)
                None if v is None else v / 3.6 for v in hourly["wind_speed_10m"]
            ],
            "temp_c": hourly["temperature_2m"],
            "cloud_cover_pct": hourly["cloud_cover"],
        }
    )
    return df


# ---------------------------------------------------------------------------
# Step 1.3 — weather history (actual)
# ---------------------------------------------------------------------------
''' Fetches actual (observed) hourly weather for [start, end] in one request and stores it in DuckDB table 'weather'. Columns: timestamp, irradiance_w_m2, wind_speed_ms, temp_c, cloud_cover_pct '''
def fetch_weather_history(start, end, persist: bool = True) -> pd.DataFrame:
    params = {
        "latitude": WEATHER_LAT,
        "longitude": WEATHER_LON,
        "start_date": str(pd.Timestamp(start).date()),
        "end_date": str(pd.Timestamp(end).date()),
        "hourly": HOURLY_FIELDS,
        "timezone": "UTC",
    }

    resp = requests.get(_ARCHIVE_URL, params=params, timeout=30)
    resp.raise_for_status()  # a failed request here should stop the backfill, not be silently skipped

    out = _parse_hourly_response(resp.json()).sort_values("timestamp").reset_index(drop=True)

    if persist:
        n = write_df(out, "weather")
        print(f"[weather] wrote {len(out)} rows ({n} now in table 'weather')")
    return out


# ---------------------------------------------------------------------------
# Step 1.3 — weather forecast (next 48h)
# ---------------------------------------------------------------------------
''' Fetches the next 48h weather forecast. Returns a DataFrame only (no DB write) — this is called live by the forecast API endpoint (step 3.2), not part of the historical backfill. Same columns as fetch_weather_history(). '''
def fetch_weather_forecast() -> pd.DataFrame:
    params = {
        "latitude": WEATHER_LAT,
        "longitude": WEATHER_LON,
        "hourly": HOURLY_FIELDS,
        "forecast_days": 2,  # NOTE: Open-Meteo returns whole days; 2 days covers the 48h window
        "timezone": "UTC",
    }

    resp = requests.get(_FORECAST_URL, params=params, timeout=30)
    resp.raise_for_status()

    return _parse_hourly_response(resp.json()).sort_values("timestamp").reset_index(drop=True)


'''
Main function

Note: Doing python -m backend.data.weather will make this function run automatically, but not if we import weather into another file
'''
if __name__ == "__main__":
    # NOTE: Check whether number was typed (i.e. python -m backend.data.weather 365), else default = 365
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 365

    # NOTE: end = today - 1 day = yesterday (matches caiso.py's convention; keeps history + forecast non-overlapping)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)

    print(f"Fetching weather history {start} -> {end} ({days} days)")
    fetch_weather_history(start, end)