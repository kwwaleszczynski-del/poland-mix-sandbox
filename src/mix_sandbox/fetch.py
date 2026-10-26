"""Download step: PSE reports and ERA5 series into data/ (cached), hourly PSE tables into data/interim/.

Usage:
    python -m mix_sandbox fetch                 # everything
    python -m mix_sandbox fetch --only era5
    python -m mix_sandbox fetch --offline       # rebuild data/interim from the caches only
"""

from __future__ import annotations

import logging
import tomllib

import requests

from . import era5, pse_data
from .paths import CONFIG_DIR, INTERIM_DIR

log = logging.getLogger(__name__)

SYSTEM_SPAN = ("2024-06-14", "2026-09-30")       # whole span of the reports API used for checks
REDISPATCH_SPAN = ("2024-09-24", "2026-09-30")   # poze-redoze starts on 2024-09-24
YEAR = ("2025-01-01", "2025-12-31")              # reference year
WIND_VARS = ["wind_speed_100m"]
PV_VARS = ["shortwave_radiation", "diffuse_radiation", "temperature_2m"]


def era5_points() -> dict:
    with open(CONFIG_DIR / "era5_points.toml", "rb") as f:
        return tomllib.load(f)


def fetch_era5(offline: bool = False) -> None:
    cfg = era5_points()
    start, end = cfg["period"]["start"], cfg["period"]["end"]
    session = requests.Session()
    for kind, variables in (("wind_onshore", WIND_VARS), ("wind_offshore", WIND_VARS), ("pv", PV_VARS)):
        for p in cfg[kind]:
            point = era5.Point(p["name"], p["lat"], p["lon"])
            era5.load_point(point, variables, start, end, kind=kind, offline=offline, session=session)


def fetch_pse(offline: bool = False) -> None:
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    pse_data.system_hourly(*SYSTEM_SPAN, offline=offline).to_parquet(INTERIM_DIR / "system_hourly.parquet")
    pse_data.redispatch_hourly(*REDISPATCH_SPAN, offline=offline).to_parquet(INTERIM_DIR / "redispatch_hourly.parquet")
    pse_data.rce_hourly(*YEAR, offline=offline).to_frame().to_parquet(INTERIM_DIR / "rce_hourly.parquet")
    pse_data.units_by_fuel(*YEAR, offline=offline).to_parquet(INTERIM_DIR / "units_by_fuel.parquet")


def run(only: str | None = None, offline: bool = False) -> None:
    if only in (None, "pse"):
        fetch_pse(offline)
    if only in (None, "era5"):
        fetch_era5(offline)
    log.info("fetch done")
