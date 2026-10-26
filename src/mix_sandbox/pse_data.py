"""PSE reports through ``pse-opendata``, averaged to hourly values indexed by interval start (UTC).

Reports used:
    his-wlk-cal   demand, generation of scheduling units (jg) and of units outside the balancing market (jnwrb),
                  storage charging (jgm), wind (wi), PV (pv), cross-border balance (swm_p, swm_np), MW
    poze-redoze   non-market redispatch (curtailment) of wind and PV ordered by PSE, MW
    gen-jw        generation per unit >= 100 MW, summed per fuel with config/plants.csv
    rce-pln       market price RCE, PLN/MWh (only to compare the price approximation)

Usage:
    system = system_hourly("2024-06-14", "2026-09-30")
"""

from __future__ import annotations

import logging

import pandas as pd
import pse_opendata as pse

from .paths import CONFIG_DIR, PSE_CACHE

log = logging.getLogger(__name__)

SYSTEM_FIELDS = ["demand", "jg", "jnwrb", "jgm", "wi", "pv", "swm_p", "swm_np"]
REDISPATCH_FIELDS = ["pv_red_balance", "pv_red_network", "wi_red_balance", "wi_red_network"]


def client(offline: bool = False) -> pse.Client:
    return pse.Client(cache_dir=PSE_CACHE, offline=offline, page_size=100000)


def hourly(frame: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    """Mean of the quarter-hours of each clock hour; hours with fewer than 4 quarter-hours are dropped."""
    start = frame["start_utc"].dt.floor("h")
    grouped = frame[fields].groupby(start)
    out = grouped.mean()
    out = out[grouped.size() == 4]
    out.index.name = "start_utc"
    return out


def system_hourly(start: str, end: str, offline: bool = False) -> pd.DataFrame:
    raw = client(offline).get("his-wlk-cal", start, end, fields=SYSTEM_FIELDS)
    log.info("his-wlk-cal %s..%s: %d rows", start, end, len(raw))
    return hourly(raw, SYSTEM_FIELDS)


def redispatch_hourly(start: str, end: str, offline: bool = False) -> pd.DataFrame:
    # most intervals carry no redispatch: keep the empty rows and read them as zero
    raw = client(offline).get("poze-redoze", start, end, fields=REDISPATCH_FIELDS, dropna=False)
    raw[REDISPATCH_FIELDS] = raw[REDISPATCH_FIELDS].fillna(0.0)
    log.info("poze-redoze %s..%s: %d rows", start, end, len(raw))
    out = hourly(raw, REDISPATCH_FIELDS)
    return pd.DataFrame({
        "pv_redispatch": out["pv_red_balance"] + out["pv_red_network"],
        "wi_redispatch": out["wi_red_balance"] + out["wi_red_network"],
    })


def rce_hourly(start: str, end: str, offline: bool = False) -> pd.Series:
    raw = client(offline).get("rce-pln", start, end)
    return hourly(raw, ["rce_pln"])["rce_pln"]


def plant_fuels() -> pd.DataFrame:
    return pd.read_csv(CONFIG_DIR / "plants.csv", comment="#")


def units_by_fuel(start: str, end: str, offline: bool = False) -> pd.DataFrame:
    """Hourly generation of units >= 100 MW summed per fuel of config/plants.csv; pumping is negative."""
    raw = client(offline).get("gen-jw", start, end)
    log.info("gen-jw %s..%s: %d rows, %d plants", start, end, len(raw), raw["power_plant"].nunique())
    fuels = plant_fuels().set_index("power_plant")["fuel"]
    unknown = sorted(set(raw["power_plant"]) - set(fuels.index))
    if unknown:
        raise ValueError(f"plants missing from config/plants.csv: {unknown}")
    raw["fuel"] = raw["power_plant"].map(fuels)
    hour = raw["start_utc"].dt.floor("h")
    # sum of units over the 4 quarter-hours / 4 = hourly mean of the fuel total
    out = raw.groupby([hour, "fuel"])["value"].sum().unstack("fuel", fill_value=0.0) / 4.0
    quarters = raw.groupby(hour)["start_utc"].nunique()
    out = out[quarters == 4]
    out.index.name = "start_utc"
    return out
