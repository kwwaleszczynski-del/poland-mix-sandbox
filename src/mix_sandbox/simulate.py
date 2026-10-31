"""Run one scenario on the page data and print the yearly balance (the same numbers the page shows).

Usage:
    python -m mix_sandbox simulate --scenario kpeik2030
    python -m mix_sandbox simulate --scenario today --weather-year 2017 --set pv=40 storage_gwh=60
    python -m mix_sandbox simulate --presets     # every preset on every weather year -> results/presets*.csv
"""

from __future__ import annotations

import logging

import pandas as pd

from . import model, site_data
from .config import SCENARIO_KEYS, load_scenarios, model_assumptions
from .paths import RESULTS_DIR

log = logging.getLogger(__name__)


def scenario_values(name: str, overrides: dict[str, str]) -> dict:
    values = dict(load_scenarios()[name]["values"])
    for key, raw in overrides.items():
        if key not in SCENARIO_KEYS:
            raise KeyError(f"unknown parameter {key!r}; known: {', '.join(SCENARIO_KEYS)}")
        values[key] = raw if key == "storage_rule" else float(raw)
    return values


def run(name: str, weather_year: str | None, overrides: dict[str, str]) -> model.Result:
    values = scenario_values(name, overrides)
    year = None if weather_year in (None, "pse") else int(weather_year)
    result = model.simulate(site_data.load_profiles(year), values, model_assumptions())
    t = result.totals
    print(f"scenario {name}, weather {'PSE 2025' if year is None else f'ERA5 {year}'}")
    for key in ("pv", "wind_on", "wind_off", "other", "nuclear", "lignite", "hard_coal", "gas", "import",
                "discharge", "charge", "export", "curtail", "ens"):
        print(f"  {key:<10} {t[f'{key}_twh']:8.2f} TWh")
    print(f"  demand     {t['demand_twh']:8.2f} TWh, wind + PV share {t['vre_share']:.1%}")
    print(f"  CO2        {t['co2_mt']:8.2f} Mt ({t['co2_g_kwh']:.0f} g/kWh)")
    print(f"  price      {t['price_mean']:8.0f} PLN/MWh mean, {t['hours_price_le_0']} h at or below 0")
    print(f"  surplus    {t['surplus_hours']} h, curtailment {t['curtail_hours']} h, ENS {t['ens_hours']} h "
          f"(max {t['ens_max_gw']:.2f} GW)")
    return result


def presets(weather_years=range(2010, 2026)) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every preset on the PSE 2025 reference year and on each ERA5 weather year; writes results/presets*.csv."""
    rows = []
    for weather in ["pse", *weather_years]:
        profiles = site_data.load_profiles(weather)
        for name in load_scenarios():
            t = model.simulate(profiles, scenario_values(name, {}), model_assumptions()).totals
            rows.append({
                "scenario": name, "weather": "PSE 2025" if weather == "pse" else f"ERA5 {weather}",
                "vre_share_pct": round(100 * t["vre_share"], 1), "co2_mt": round(t["co2_mt"], 1),
                "co2_g_kwh": round(t["co2_g_kwh"]), "curtail_twh": round(t["curtail_twh"], 2),
                "ens_twh": round(t["ens_twh"], 4), "ens_hours": t["ens_hours"], "ens_max_gw": round(t["ens_max_gw"], 2),
                "price_mean_pln_mwh": round(t["price_mean"]),
            })
    df = pd.DataFrame(rows)
    ref, era5 = df[df["weather"] == "PSE 2025"], df[df["weather"] != "PSE 2025"]
    RESULTS_DIR.mkdir(exist_ok=True)
    ref.to_csv(RESULTS_DIR / "presets.csv", index=False)
    era5.to_csv(RESULTS_DIR / "presets_weather_years.csv", index=False)
    log.info("wrote %s and %s", RESULTS_DIR / "presets.csv", RESULTS_DIR / "presets_weather_years.csv")
    return ref, era5
