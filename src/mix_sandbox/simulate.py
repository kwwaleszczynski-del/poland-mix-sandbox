"""Run one scenario on the page data and print the yearly balance (the same numbers the page shows).

Usage:
    python -m mix_sandbox simulate --scenario kpeik2030
    python -m mix_sandbox simulate --scenario today --weather-year 2017 --set pv=40 storage_gwh=60
"""

from __future__ import annotations

import logging

from . import model, site_data
from .config import SCENARIO_KEYS, load_scenarios, model_assumptions

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
