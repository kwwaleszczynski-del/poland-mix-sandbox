"""Assumptions and scenarios from config/*.toml, and the flat assumption set the dispatch model reads.

Usage:
    a = model_assumptions()               # dict for model.simulate / docs/model.js
    scenarios = load_scenarios()          # {"today": {...}, "kpeik2030": {...}, ...}
"""

from __future__ import annotations

import tomllib
from functools import cache

from .paths import CONFIG_DIR

SCENARIO_KEYS = ("pv", "wind_on", "wind_off", "nuclear", "lignite", "hard_coal", "gas", "other", "storage_gw",
                 "storage_gwh", "import_gw", "export_gw", "mustrun_gw", "demand_twh", "storage_rule")


@cache
def load_assumptions() -> dict:
    with open(CONFIG_DIR / "assumptions.toml", "rb") as f:
        return tomllib.load(f)


@cache
def load_scenarios() -> dict:
    with open(CONFIG_DIR / "scenarios.toml", "rb") as f:
        raw = tomllib.load(f)
    out = {}
    for key, s in raw["scenario"].items():
        missing = [k for k in SCENARIO_KEYS if k not in s["values"]]
        if missing:
            raise ValueError(f"scenario {key}: missing {missing}")
        out[key] = s
    return out


def model_assumptions() -> dict:
    """Numbers used by the dispatch, derived from config/assumptions.toml (prices converted to PLN)."""
    a = load_assumptions()
    eur = a["prices"]["eur_pln"]
    co2 = a["prices"]["co2_eur_t"] * eur
    tech = {}
    for name in ("lignite", "hard_coal", "gas"):
        t = a["tech"][name]
        if "fuel_eur_mwh_th" in t:
            fuel_pln_gj = t["fuel_eur_mwh_th"] * eur / 3.6
        else:
            fuel_pln_gj = t["fuel_pln_gj"]
        tech[name] = {
            "availability": t["availability"],
            "eff_best": t["eff_best"],
            "eff_worst": t["eff_worst"],
            "fuel_pln_gj": round(fuel_pln_gj, 4),
            "ef_t_gj": t["ef_kg_gj"] / 1000.0,
            "vom_pln_mwh": t["vom_pln_mwh"],
        }
    m = a["model"]
    return {
        "co2_price_pln_t": round(co2, 4),
        "blocks_per_tech": m["blocks_per_tech"],
        "lookahead_h": m["lookahead_h"],
        "tech": tech,
        "nuclear": dict(a["nuclear"]),
        "other": {"co2_t_mwh": a["other"]["co2_t_mwh"]},
        "storage": dict(a["storage"]),
        "import": {"price_pln_mwh": a["import"]["price_pln_mwh"], "availability": a["import"]["availability"]},
        "export": {"availability": a["export"]["availability"]},
        "prices": {k: a["prices"][k] for k in ("curtailment_pln_mwh", "surplus_pln_mwh", "scarcity_pln_mwh")},
    }
