"""ERA5 hourly time series from the Open-Meteo archive API, one cached Parquet file per point.

Open-Meteo counts the cost of a request per location as max(1, variables / 10 * max(1, days / 14)) against a
free limit of 600 per minute, 5000 per hour and 10000 per day per IP. Requests are spaced to stay under the
minute limit, and a point is never downloaded twice (delete its file to refresh it).

Usage:
    frame = load_point(point, ["wind_speed_100m"], "2010-01-01", "2026-09-30")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from .paths import ERA5_DIR

log = logging.getLogger(__name__)

URL = "https://archive-api.open-meteo.com/v1/archive"
WEIGHT_PER_MINUTE = 500          # stay below the 600/min free limit


@dataclass(frozen=True)
class Point:
    name: str
    lat: float
    lon: float


def request_weight(n_variables: int, start: str, end: str) -> float:
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    return max(1.0, n_variables / 10 * max(1.0, days / 14))


def _cache_path(kind: str, point: Point) -> Path:
    return ERA5_DIR / f"{kind}_{point.name}.parquet"


def load_point(point: Point, variables: list[str], start: str, end: str, *, kind: str,
               offline: bool = False, session: requests.Session | None = None) -> pd.DataFrame:
    """Hourly ERA5 values at a point, indexed by UTC time (instantaneous for wind, preceding-hour mean for
    radiation, as Open-Meteo labels them)."""
    path = _cache_path(kind, point)
    if path.exists():
        frame = pd.read_parquet(path)
        if set(variables) <= set(frame.columns) and frame.index.min() <= pd.Timestamp(start, tz="UTC") \
                and frame.index.max() >= pd.Timestamp(end, tz="UTC") + pd.Timedelta(hours=23):
            return frame[variables]
    if offline:
        raise FileNotFoundError(f"no cached ERA5 data for {kind}/{point.name} at {path}")
    params = {
        "latitude": point.lat, "longitude": point.lon, "start_date": start, "end_date": end,
        "hourly": ",".join(variables), "models": "era5", "timezone": "GMT", "wind_speed_unit": "ms",
    }
    weight = request_weight(len(variables), start, end)
    log.info("ERA5 %s/%s (%.2f, %.2f) %s..%s, weight %.0f", kind, point.name, point.lat, point.lon, start, end,
             weight)
    http = session or requests.Session()
    for attempt in range(4):
        response = http.get(URL, params=params, timeout=180)
        if response.status_code == 429:
            # a daily limit cannot be waited out here; minute/hour limits can
            if "daily" in response.text.lower():
                raise RuntimeError("Open-Meteo daily limit reached; resume after the reset")
            log.warning("Open-Meteo 429, waiting 65 s (%s)", response.text[:120])
            time.sleep(65)
            continue
        response.raise_for_status()
        break
    else:
        raise RuntimeError(f"Open-Meteo kept refusing {kind}/{point.name}")
    hourly = response.json()["hourly"]
    frame = pd.DataFrame({v: hourly[v] for v in variables},
                         index=pd.to_datetime(hourly["time"], utc=True).rename("time_utc"), dtype="float64")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)
    time.sleep(60 * weight / WEIGHT_PER_MINUTE)
    return frame
