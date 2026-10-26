"""Hourly profiles of the reference year 2025 (PSE) and of the ERA5 weather years.

Reference year (Polish local year 2025, 8760 hours, labelled by start in UTC):
    demand      PSE "demand" (his-wlk-cal), MW
    pv, wind_on available output = measured generation + non-market redispatch ordered by PSE (poze-redoze),
                divided by the installed capacity interpolated day by day between the dated values of
                config/assumptions.toml -> capacity factor
    wind_off    ERA5 model (no offshore wind in Poland in 2025)
    other       generation outside wind, PV and the units >= 100 MW of gen-jw (small CHP, industrial plants,
                hydro, biomass, small storage), shape with mean 1
    mustrun     lower envelope of the generation of large coal and gas units per month (2nd percentile),
                shape with mean 1

Weather years 2010..2025: wind and PV from ERA5 through power curves and a simple PV model, with point weights
fitted (non-negative least squares) to the 2025 PSE capacity factors and rescaled so that the modelled 2025 has the
measured mean; the demand, "other" and must-run shapes of 2025 are kept.

Usage:
    ref = reference_year()          # DataFrame of the series above plus the measured components used in validation
    years, fit = weather_years()    # {year: DataFrame(pv, wind_on, wind_off)}, fit statistics
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import weather
from .config import load_assumptions
from .paths import CONFIG_DIR, ERA5_DIR, INTERIM_DIR

log = logging.getLogger(__name__)

REFERENCE_YEAR = 2025
WEATHER_YEARS = range(2010, 2026)
LARGE_THERMAL = ("lignite", "hard_coal", "gas")


def installed(series: str, index: pd.DatetimeIndex) -> pd.Series:
    """Installed capacity (MW) at each hour, linear in time between the dated values of the assumptions."""
    points = load_assumptions()["capacity_history"][series]
    dates = pd.to_datetime([p["date"] for p in points]).tz_localize("Europe/Warsaw").tz_convert("UTC")
    values = np.array([p["mw"] for p in points], dtype=float)
    # compare in seconds: pandas may hold the two indexes in different resolutions (ns, us)
    x = index.as_unit("s").asi8.astype(float)
    return pd.Series(np.interp(x, dates.as_unit("s").asi8.astype(float), values), index=index)


def _interim(name: str) -> pd.DataFrame:
    return pd.read_parquet(INTERIM_DIR / f"{name}.parquet")


def reference_year() -> pd.DataFrame:
    hours = weather.year_hours(REFERENCE_YEAR)
    system = _interim("system_hourly").reindex(hours)
    if system.isna().any().any():
        raise ValueError("missing PSE hours in the reference year")
    red = _interim("redispatch_hourly").reindex(hours).fillna(0.0)
    units = _interim("units_by_fuel").reindex(hours)
    if units.isna().any().any():
        missing = int(units.isna().any(axis=1).sum())
        log.warning("gen-jw: %d hours missing in %d, filled by interpolation", missing, REFERENCE_YEAR)
        units = units.interpolate(limit_direction="both")
    df = pd.DataFrame(index=hours)
    df["demand"] = system["demand"]
    # poze-redoze reports the curtailment as negative values
    df["pv_mw"] = system["pv"] - red["pv_redispatch"]
    df["wind_mw"] = system["wi"] - red["wi_redispatch"]
    df["pv_redispatch"] = -red["pv_redispatch"]
    df["wind_redispatch"] = -red["wi_redispatch"]
    df["pv_cap"] = installed("pv", hours)
    df["wind_cap"] = installed("wind_on", hours)
    df["pv"] = (df["pv_mw"] / df["pv_cap"]).clip(lower=0.0)
    df["wind_on"] = (df["wind_mw"] / df["wind_cap"]).clip(lower=0.0)
    df["net_import"] = system["swm_p"] + system["swm_np"]
    df["storage_charge"] = -system["jgm"]
    nonvre = system["jg"] + system["jnwrb"] - system["pv"] - system["wi"]
    for fuel in units.columns:
        df[f"unit_{fuel}"] = units[fuel]
    # wind and PV units of gen-jw are already in wi and pv; pumping of large units is negative in gen-jw and
    # also counted in jgm, so only generation of non-VRE units is taken out; large biomass stays in "other"
    dispatchable = [c for c in units.columns if c not in ("pv", "wind", "biomass")]
    unit_gen = units[dispatchable].clip(lower=0.0).sum(axis=1)
    df["other_mw"] = nonvre - unit_gen
    df["other"] = df["other_mw"] / df["other_mw"].mean()
    large = sum(df[f"unit_{f}"] for f in LARGE_THERMAL if f"unit_{f}" in df)
    df["large_thermal"] = large
    local_month = hours.tz_convert("Europe/Warsaw").month
    floor = large.groupby(local_month).quantile(0.02)
    df["mustrun_mw"] = floor.reindex(local_month).to_numpy()
    df["mustrun"] = df["mustrun_mw"] / df["mustrun_mw"].mean()
    return df


@dataclass
class FitStats:
    kind: str
    r2_in_sample: float
    r2_h2_2024: float
    r2_2026: float
    corr_2026: float
    scale: float
    weights: dict


def _era5(kind: str) -> dict[str, pd.DataFrame]:
    cfg = tomllib.load(open(CONFIG_DIR / "era5_points.toml", "rb"))
    return {p["name"]: (p, pd.read_parquet(ERA5_DIR / f"{kind}_{p['name']}.parquet")) for p in cfg[kind]}


def _features(kind: str) -> pd.DataFrame:
    cols = {}
    for name, (p, frame) in _era5(kind).items():
        if kind == "pv":
            f = weather.pv_features(frame, p["lat"], p["lon"])
            cols[f"{name}_tilted"] = f["tilted"]
            cols[f"{name}_horizontal"] = f["horizontal"]
        else:
            cols[name] = weather.wind_cf(frame["wind_speed_100m"], "onshore")
    return pd.DataFrame(cols)


def _r2(obs: pd.Series, pred: pd.Series) -> float:
    return float(1 - ((obs - pred) ** 2).sum() / ((obs - obs.mean()) ** 2).sum())


def fit_onshore_or_pv(kind: str, target: str) -> tuple[pd.Series, FitStats]:
    """Fit point weights to the measured available output (MW) of 2025 and return the modelled capacity factor
    for all ERA5 hours, scaled so that its 2025 mean equals the measured 2025 capacity factor."""
    from scipy.optimize import nnls

    feats = _features(kind)
    system = _interim("system_hourly")
    red = _interim("redispatch_hourly").reindex(system.index).fillna(0.0)
    col, red_col, cap_name = {"wind_on": ("wi", "wi_redispatch", "wind_on"),
                              "pv": ("pv", "pv_redispatch", "pv")}[target]
    measured = system[col] - red[red_col]
    cap = installed(cap_name, measured.index)
    hours = weather.year_hours(REFERENCE_YEAR)
    w, _ = nnls(feats.loc[hours].to_numpy(), measured.loc[hours].to_numpy())
    model_mw = feats @ w
    cf_obs = measured / cap
    scale = float(cf_obs.loc[hours].mean() / (model_mw.loc[hours] / cap.loc[hours]).mean())
    # capacity factor of the modelled fleet: MW per installed MW of 2025, rescaled to the measured mean
    cf_model = model_mw / cap.loc[hours].mean() * scale
    h24 = measured.loc["2024-06-14":"2024-12-31"].index
    h26 = measured.loc["2026-01-01":"2026-09-30"].index
    stats = FitStats(
        kind=target,
        r2_in_sample=_r2(measured.loc[hours], model_mw.loc[hours]),
        r2_h2_2024=_r2(cf_obs.loc[h24], (model_mw / cap).loc[h24] * scale),
        r2_2026=_r2(cf_obs.loc[h26], (model_mw / cap).loc[h26] * scale),
        corr_2026=float(np.corrcoef(cf_obs.loc[h26], model_mw.loc[h26])[0, 1]),
        scale=scale,
        weights={k: round(float(v), 1) for k, v in zip(feats.columns, w, strict=True) if v > 0},
    )
    log.info("%s fit: R2 2025 %.3f, H2 2024 %.3f, 2026 %.3f, scale %.3f", target, stats.r2_in_sample,
             stats.r2_h2_2024, stats.r2_2026, scale)
    return cf_model.clip(lower=0.0, upper=1.0), stats


def offshore_cf() -> pd.Series:
    losses = load_assumptions()["offshore"]["losses"]
    series = [weather.wind_cf(frame["wind_speed_100m"], "offshore") for _, frame in _era5("wind_offshore").values()]
    return pd.concat(series, axis=1).mean(axis=1) * (1.0 - losses)


def weather_years() -> tuple[dict[int, pd.DataFrame], list[FitStats]]:
    wind, wind_stats = fit_onshore_or_pv("wind_onshore", "wind_on")
    pv, pv_stats = fit_onshore_or_pv("pv", "pv")
    off = offshore_cf()
    years = {}
    for year in WEATHER_YEARS:
        hours = weather.year_hours(year)
        frame = pd.DataFrame({"pv": pv.reindex(hours), "wind_on": wind.reindex(hours),
                              "wind_off": off.reindex(hours)}, index=hours)
        # ERA5 starts at 2010-01-01 00:00 UTC, one hour after the Polish year began; the last hour of
        # a wind series has no successor: fill such edge hours from the neighbours
        years[year] = frame.ffill().bfill()
    return years, [wind_stats, pv_stats]
