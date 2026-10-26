"""Build step: profiles, assumptions and scenarios into docs/data/ for the page (and for the tests).

Writes:
    docs/data/reference.json.gz        reference year 2025 (PSE): demand, wind, PV, other, must-run (+ ERA5 offshore)
    docs/data/weather/<year>.json.gz   ERA5 model of wind and PV, 2010..2025
    docs/data/meta.json                model assumptions, scenarios, weather-year statistics, sources, validation

Usage:
    python -m mix_sandbox build
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date

from . import profiles, site_data
from .config import load_assumptions, load_scenarios, model_assumptions
from .paths import RESULTS_DIR, SITE_DATA

log = logging.getLogger(__name__)


def reference_stats(ref) -> dict:
    return {
        "demand_twh": round(float(ref["demand"].sum()) / 1e6, 2),
        "other_gw": round(float(ref["other_mw"].mean()) / 1e3, 2),
        "mustrun_gw": round(float(ref["mustrun_mw"].mean()) / 1e3, 2),
        "pv_cap_mean_mw": round(float(ref["pv_cap"].mean())),
        "wind_cap_mean_mw": round(float(ref["wind_cap"].mean())),
        "pv_cf": round(float(ref["pv"].mean()), 4),
        "wind_on_cf": round(float(ref["wind_on"].mean()), 4),
        "pv_redispatch_twh": round(float(ref["pv_redispatch"].sum()) / 1e6, 3),
        "wind_redispatch_twh": round(float(ref["wind_redispatch"].sum()) / 1e6, 3),
    }


def run() -> None:
    ref = profiles.reference_year()
    years, fits = profiles.weather_years()
    start = ref.index[0].strftime("%Y-%m-%dT%H:%M:%SZ")
    sizes = {}
    reference = {
        "year": profiles.REFERENCE_YEAR,
        "start_utc": start,
        "hours": len(ref),
        "scale": site_data.SCALE,
        "demand": [int(round(v)) for v in ref["demand"]],
        "pv": site_data.encode(ref["pv"]),
        "wind_on": site_data.encode(ref["wind_on"]),
        "wind_off": site_data.encode(years[profiles.REFERENCE_YEAR]["wind_off"]),
        "other": site_data.encode(ref["other"]),
        "mustrun": site_data.encode(ref["mustrun"]),
    }
    sizes["reference.json.gz"] = site_data.write_json_gz(SITE_DATA / "reference.json.gz", reference)
    weather_table = {}
    for year, frame in years.items():
        payload = {"year": year, "scale": site_data.SCALE,
                   **{k: site_data.encode(frame[k]) for k in ("pv", "wind_on", "wind_off")}}
        sizes[f"weather/{year}.json.gz"] = site_data.write_json_gz(SITE_DATA / "weather" / f"{year}.json.gz", payload)
        weather_table[str(year)] = {k: round(float(frame[k].mean()), 4) for k in ("pv", "wind_on", "wind_off")}
    a = load_assumptions()
    validation_path = RESULTS_DIR / "validation_2025.json"
    meta = {
        "built": date.today().isoformat(),
        "reference": {"year": profiles.REFERENCE_YEAR, "start_utc": start, **reference_stats(ref)},
        "model": model_assumptions(),
        "assumptions": {k: a[k] for k in ("prices", "tech", "nuclear", "storage", "import", "export", "other", "offshore")},
        "scenarios": load_scenarios(),
        "weather_years": weather_table,
        "fit": [asdict(f) for f in fits],
        "sources": a.get("sources", {}),
        "validation": json.loads(validation_path.read_text(encoding="utf-8")) if validation_path.exists() else None,
    }
    (SITE_DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(sizes.values()) + (SITE_DATA / "meta.json").stat().st_size
    log.info("docs/data: %d files, %.0f kB (reference %.0f kB)", len(sizes) + 1, total / 1024,
             sizes["reference.json.gz"] / 1024)
