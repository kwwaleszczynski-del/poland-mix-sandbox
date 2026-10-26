"""Read and write the page data in docs/data: gzip-compressed JSON with integer-coded hourly series.

Capacity factors and shapes are stored as integers in units of 1/10000, demand in MW. The Python model reads the
same decoded numbers as the page, so both run on identical inputs.

Usage:
    write_json_gz(path, payload)
    profiles = load_profiles(weather_year=2017)    # dict of numpy arrays for model.simulate
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np

from .paths import SITE_DATA

SCALE = 10000


def encode(values, scale: float = SCALE) -> list[int]:
    return [int(round(float(v) * scale)) for v in values]


def decode(values, scale: float = SCALE) -> np.ndarray:
    return np.asarray(values, dtype=float) / scale


def write_json_gz(path: Path, payload: dict) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    # fixed mtime so that rebuilding unchanged data gives identical files
    with open(path, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(raw)
    return path.stat().st_size


def read_json_gz(path: Path) -> dict:
    with gzip.open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def load_meta(root: Path = SITE_DATA) -> dict:
    return json.loads((root / "meta.json").read_text(encoding="utf-8"))


def load_profiles(weather_year: int | str | None = None, root: Path = SITE_DATA) -> dict[str, np.ndarray]:
    """Profiles of the reference year (PSE 2025: ``None`` or ``"pse"``); with a year (2010..2025) wind and PV
    come from the ERA5 model of that year."""
    ref = read_json_gz(root / "reference.json.gz")
    out = {"demand": np.asarray(ref["demand"], dtype=float)}
    for key in ("pv", "wind_on", "wind_off", "other", "mustrun"):
        out[key] = decode(ref[key])
    if weather_year not in (None, "pse"):
        w = read_json_gz(root / "weather" / f"{int(weather_year)}.json.gz")
        for key in ("pv", "wind_on", "wind_off"):
            out[key] = decode(w[key])
    return out
