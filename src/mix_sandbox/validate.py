"""2025 validation: run the dispatch on the measured hourly inputs of 2025 and compare with what happened.

Inputs taken as measured (MW, hourly): demand, available wind and PV (generation + PSE redispatch), "other"
generation and the must-run envelope. Everything else is the model: storage, exchange, the split between lignite,
hard coal and gas, curtailment, prices and emissions. Compared with PSE data of 2025: gen-jw per fuel (units >=
100 MW), cross-border balance (swm_p + swm_np), storage charging (jgm) and pumped-storage generation, non-market
redispatch of wind and PV (poze-redoze) and the RCE price.

Usage:
    python -m mix_sandbox validate               # writes results/validation_2025.json and .md
    python -m mix_sandbox validate --calibrate   # grid search of the exchange parameters (prints only)
"""

from __future__ import annotations

import copy
import itertools
import json
import logging

import numpy as np
import pandas as pd

from . import model, profiles
from .config import load_scenarios, model_assumptions
from .paths import INTERIM_DIR, RESULTS_DIR

log = logging.getLogger(__name__)

# fleet of 2025 in the model: large units from gen-jw, storage, exchange limits and the calibrated must-run level
# from the "today" preset
FLEET_KEYS = ("lignite", "hard_coal", "gas", "storage_gw", "storage_gwh", "import_gw", "export_gw", "nuclear",
              "wind_off", "mustrun_gw")


def measured_inputs(ref: pd.DataFrame) -> tuple[dict, dict]:
    """Profiles in MW/1000 with unit capacities, so the model sees exactly the measured MW."""
    prof = {
        "demand": ref["demand"].to_numpy(),
        "pv": ref["pv_mw"].to_numpy() / 1000.0,
        "wind_on": ref["wind_mw"].to_numpy() / 1000.0,
        "wind_off": np.zeros(len(ref)),
        "other": ref["other_mw"].to_numpy() / 1000.0,
        "mustrun": ref["mustrun"].to_numpy(),
    }
    today = load_scenarios()["today"]["values"]
    scen = {k: today[k] for k in FLEET_KEYS}
    scen.update(pv=1.0, wind_on=1.0, other=1.0, demand_twh=float(ref["demand"].sum()) / 1e6,
                storage_rule=today["storage_rule"])
    return prof, scen


def _r2(obs: np.ndarray, pred: np.ndarray) -> float:
    return float(1 - ((obs - pred) ** 2).sum() / ((obs - obs.mean()) ** 2).sum())


def compare(ref: pd.DataFrame, rce: pd.Series, r: model.Result) -> dict:
    h = r.hourly
    actual_exchange = ref["net_import"].to_numpy()
    model_exchange = h["import"] - h["export"]
    pumped = ref.get("unit_pumped_hydro", pd.Series(0.0, index=ref.index)).clip(lower=0.0).to_numpy()
    rows = {}

    def row(name, actual, modelled, unit="TWh"):
        rows[name] = {"actual": round(float(actual), 3), "model": round(float(modelled), 3), "unit": unit}

    for fuel in model.THERMAL:
        row(f"{fuel}_twh", ref[f"unit_{fuel}"].sum() / 1e6, h[fuel].sum() / 1e6)
    large_a = sum(ref[f"unit_{f}"] for f in model.THERMAL).to_numpy()
    large_m = h["lignite"] + h["hard_coal"] + h["gas"]
    row("large_thermal_twh", large_a.sum() / 1e6, large_m.sum() / 1e6)
    row("import_twh", np.clip(actual_exchange, 0, None).sum() / 1e6, h["import"].sum() / 1e6)
    row("export_twh", np.clip(-actual_exchange, 0, None).sum() / 1e6, h["export"].sum() / 1e6)
    row("net_import_twh", actual_exchange.sum() / 1e6, model_exchange.sum() / 1e6)
    row("storage_charge_twh", ref["storage_charge"].sum() / 1e6, h["charge"].sum() / 1e6)
    # only the pumped-storage units >= 100 MW (Żarnowiec, Porąbka-Żar) are in gen-jw; all pumping is in jgm
    row("storage_discharge_twh", pumped.sum() / 1e6, h["discharge"].sum() / 1e6)
    red = (ref["pv_redispatch"] + ref["wind_redispatch"]).to_numpy()
    row("curtailment_twh", red.sum() / 1e6, h["curtail"].sum() / 1e6)
    row("curtailment_hours", int((red > 1.0).sum()), int((h["curtail"] > 1.0).sum()), "h")
    price = rce.to_numpy()
    row("price_mean", price.mean(), h["price"].mean(), "PLN/MWh")
    row("price_median", np.median(price), np.median(h["price"]), "PLN/MWh")
    row("hours_price_le_0", int((price <= 0).sum()), int((h["price"] <= 0).sum()), "h")
    row("ens_twh", 0.0, h["ens"].sum() / 1e6)
    hourly = {
        "large_thermal_r2": round(_r2(large_a, large_m), 3),
        "large_thermal_corr": round(float(np.corrcoef(large_a, large_m)[0, 1]), 3),
        "lignite_corr": round(float(np.corrcoef(ref["unit_lignite"], h["lignite"])[0, 1]), 3),
        "hard_coal_corr": round(float(np.corrcoef(ref["unit_hard_coal"], h["hard_coal"])[0, 1]), 3),
        "gas_corr": round(float(np.corrcoef(ref["unit_gas"], h["gas"])[0, 1]), 3),
        "exchange_corr": round(float(np.corrcoef(actual_exchange, model_exchange)[0, 1]), 3),
        "price_corr": round(float(np.corrcoef(price, h["price"])[0, 1]), 3),
        "price_mae": round(float(np.abs(price - h["price"]).mean()), 1),
        "price_spearman": round(float(pd.Series(price).corr(pd.Series(h["price"]), method="spearman")), 3),
    }
    co2 = {"model_mt": round(r.totals["co2_mt"], 2), "model_g_kwh": round(r.totals["co2_g_kwh"], 1)}
    return {"rows": rows, "hourly": hourly, "co2": co2}


def run_2025(a: dict | None = None) -> tuple[pd.DataFrame, pd.Series, model.Result]:
    ref = profiles.reference_year()
    rce = pd.read_parquet(INTERIM_DIR / "rce_hourly.parquet")["rce_pln"].reindex(ref.index)
    prof, scen = measured_inputs(ref)
    return ref, rce, model.simulate(prof, scen, a or model_assumptions())


def calibrate() -> None:
    """Grid search of import price / availability and export availability against the 2025 exchange volumes,
    curtailment and the RCE price; prints the best combinations."""
    ref = profiles.reference_year()
    rce = pd.read_parquet(INTERIM_DIR / "rce_hourly.parquet")["rce_pln"].reindex(ref.index)
    prof, scen = measured_inputs(ref)
    base = model_assumptions()
    red = float((ref["pv_redispatch"] + ref["wind_redispatch"]).sum()) / 1e6
    imp_a = float(ref["net_import"].clip(lower=0).sum()) / 1e6
    exp_a = float((-ref["net_import"]).clip(lower=0).sum()) / 1e6
    out = []
    for price, ia, ea in itertools.product((380, 400, 410, 420, 430, 440, 450, 470), (0.3, 0.4, 0.5, 0.6, 0.7),
                                           (0.2, 0.3, 0.4, 0.5, 0.6, 0.8)):
        a = copy.deepcopy(base)
        a["import"].update(price_pln_mwh=float(price), availability=ia)
        a["export"]["availability"] = ea
        t = model.simulate(prof, scen, a).totals
        err = (abs(t["import_twh"] - imp_a) + abs(t["export_twh"] - exp_a) + abs(t["curtail_twh"] - red))
        out.append((round(err, 3), price, ia, ea, round(t["import_twh"], 2), round(t["export_twh"], 2),
                    round(t["curtail_twh"], 2)))
    out.sort()
    print(f"targets: import {imp_a:.2f} TWh, export {exp_a:.2f} TWh, curtailment {red:.2f} TWh")
    print("err, import price, import availability, export availability, import, export, curtailment")
    for line in out[:10]:
        print(line)


def write_report(result: dict) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "validation_2025.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    lines = ["# Validation 2025 (generated by `python -m mix_sandbox validate`)", "",
             "| quantity | actual (PSE) | model | unit |", "|---|---:|---:|---|"]
    for name, v in result["rows"].items():
        lines.append(f"| {name} | {v['actual']:,} | {v['model']:,} | {v['unit']} |")
    lines += ["", "| hourly statistic | value |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in result["hourly"].items()]
    lines += ["", f"Model CO2: {result['co2']['model_mt']} Mt ({result['co2']['model_g_kwh']} g/kWh of demand).", ""]
    (RESULTS_DIR / "validation_2025.md").write_text("\n".join(lines), encoding="utf-8")


def run(calibrate_only: bool = False) -> None:
    if calibrate_only:
        calibrate()
        return
    ref, rce, r = run_2025()
    result = compare(ref, rce, r)
    write_report(result)
    for name, v in result["rows"].items():
        log.info("%-24s actual %10.3f  model %10.3f %s", name, v["actual"], v["model"], v["unit"])
    log.info("hourly: %s", result["hourly"])
