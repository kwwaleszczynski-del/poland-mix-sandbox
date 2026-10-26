"""Hourly merit-order dispatch, the Python twin of docs/model.js (same steps, same order, same numbers).

Each hour:
  1. demand is met first by wind and PV, then by the inflexible part of the system: "other" sources (small CHP,
     biomass, hydro: an exogenous profile), the must-run of large thermal units (heat and system stability) and
     nuclear at its minimum load;
  2. a surplus charges storage, then is exported up to the export limit, the rest is curtailed: wind and PV
     first, then (rarely) the inflexible sources;
  3. a deficit raises nuclear to its available capacity, then storage discharges (rule "greedy": as much as it
     can; rule "peak": shaves the highest net load until the next surplus, at most 24 h ahead), then thermal
     blocks and imports are dispatched by short-run marginal cost; what is left is energy not served (ENS).

The price approximation is the marginal cost of the last block used, a fixed negative price when wind and PV are
curtailed, zero in other surplus hours and a scarcity price when demand is not served.

Usage:
    result = simulate(profiles, scenario, assumptions)
    result.totals["co2_mt"]
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

THERMAL = ("lignite", "hard_coal", "gas")
ENERGY = ("pv", "wind_on", "wind_off", "other", "nuclear", "lignite", "hard_coal", "gas", "import",
          "discharge", "charge", "export", "curtail", "cut_inflexible", "ens")
SERIES = (*ENERGY, "price", "soc", "residual", "surplus", "co2")


@dataclass
class Block:
    tech: str          # lignite | hard_coal | gas | import
    capacity: float    # MW available
    srmc: float        # PLN/MWh
    co2: float         # t/MWh of electricity
    index: int = 0


@dataclass
class Result:
    hourly: dict[str, np.ndarray]
    totals: dict[str, float]
    blocks: list[Block] = field(default_factory=list)


def seq_sum(values) -> float:
    """Plain left-to-right float sum, as in JavaScript (numpy and Python 3.12+ ``sum`` round differently)."""
    total = 0.0
    for v in values:
        total += float(v)
    return total


def merit_order(scenario: dict, a: dict) -> list[Block]:
    """Thermal fleet as equal sub-blocks per technology with efficiency from best to worst, plus imports,
    sorted by marginal cost (ties keep the order of creation)."""
    co2_price = a["co2_price_pln_t"]
    n = a["blocks_per_tech"]
    blocks: list[Block] = []
    for tech in THERMAL:
        t = a["tech"][tech]
        cap = scenario[tech] * 1000.0 * t["availability"] / n
        for k in range(n):
            eff = t["eff_best"] + (t["eff_worst"] - t["eff_best"]) * (k + 0.5) / n
            co2 = t["ef_t_gj"] * 3.6 / eff
            srmc = t["fuel_pln_gj"] * 3.6 / eff + co2_price * co2 + t["vom_pln_mwh"]
            blocks.append(Block(tech, cap, srmc, co2))
    imp = a["import"]
    blocks.append(Block("import", scenario["import_gw"] * 1000.0 * imp["availability"], imp["price_pln_mwh"], 0.0))
    for i, b in enumerate(blocks):
        b.index = i
    return sorted(blocks, key=lambda b: (b.srmc, b.index))


def peak_threshold(values: list[float], power: float, energy: float) -> float:
    """Level L >= 0 with sum(min(power, max(0, v - L))) == energy over the window, 0 if even L = 0 needs less."""
    total = 0.0
    for v in values:
        total += min(power, v)
    if total <= energy:
        return 0.0
    points = []
    for v in values:
        points.append((v, 1))
        if v - power > 0:
            points.append((v - power, -1))
    points.sort(key=lambda p: (-p[0], -p[1]))
    f = 0.0
    slope = 0
    prev = points[0][0]
    for level, step in points:
        nxt = f + slope * (prev - level)
        if nxt >= energy and slope > 0:
            return prev - (energy - f) / slope
        f = nxt
        prev = level
        slope += step
    return max(0.0, prev - (energy - f) / slope) if slope > 0 else 0.0


def simulate(profiles: dict[str, np.ndarray], scenario: dict, a: dict) -> Result:
    """Run one year. ``profiles``: demand (MW), pv, wind_on, wind_off (capacity factors), other and mustrun
    (shapes with mean 1). ``scenario``: capacities in GW (storage_gwh in GWh), demand_twh, storage_rule."""
    demand0 = np.asarray(profiles["demand"], dtype=float)
    n_hours = len(demand0)
    demand = demand0 * (scenario["demand_twh"] * 1e6 / seq_sum(demand0))
    pv = scenario["pv"] * 1000.0 * np.asarray(profiles["pv"], dtype=float)
    won = scenario["wind_on"] * 1000.0 * np.asarray(profiles["wind_on"], dtype=float)
    woff = scenario["wind_off"] * 1000.0 * np.asarray(profiles["wind_off"], dtype=float)
    other = scenario["other"] * 1000.0 * np.asarray(profiles["other"], dtype=float)

    blocks = merit_order(scenario, a)
    thermal = [b for b in blocks if b.tech != "import"]
    thermal_cap = seq_sum([b.capacity for b in thermal])
    share = {b.index: (b.capacity / thermal_cap if thermal_cap > 0 else 0.0) for b in thermal}
    mustrun = np.minimum(scenario["mustrun_gw"] * 1000.0 * np.asarray(profiles["mustrun"], dtype=float), thermal_cap)
    nuc = a["nuclear"]
    nuc_max = scenario["nuclear"] * 1000.0 * nuc["availability"]
    nuc_min = nuc_max * nuc["min_load"]
    p_sto = scenario["storage_gw"] * 1000.0
    e_sto = scenario["storage_gwh"] * 1000.0
    if p_sto <= 0 or e_sto <= 0:
        p_sto, e_sto = 0.0, 0.0
    eta = math.sqrt(a["storage"]["rte"])
    soc = e_sto * a["storage"]["initial_soc"]
    soc0 = soc
    exp_cap = scenario["export_gw"] * 1000.0 * a["export"]["availability"]
    prices = a["prices"]
    peak_rule = scenario.get("storage_rule", "peak") == "peak"
    horizon = int(a["lookahead_h"])

    vre = pv + won + woff
    net = demand - vre - other - mustrun - nuc_min
    # net load left for storage and the merit order (exogenous, read by the look-ahead of the "peak" rule)
    pre = np.maximum(0.0, net - (nuc_max - nuc_min))

    out = {k: np.zeros(n_hours) for k in SERIES}
    out["residual"] = demand - vre
    out["surplus"] = np.maximum(0.0, -net)
    co2 = out["co2"]
    for t in range(n_hours):
        mr_t = mustrun[t]
        nuc_t = nuc_min
        other_t = other[t]
        ch = ex = curt = cut = dis = ens = 0.0
        flex = {}                      # block index -> generation above must-run
        if net[t] <= 0:
            surplus = -net[t]
            if p_sto > 0:
                ch = min(surplus, p_sto, (e_sto - soc) / eta)
                soc += ch * eta
                surplus -= ch
            ex = min(surplus, exp_cap)
            surplus -= ex
            curt = min(surplus, vre[t])
            cut = surplus - curt
            # a surplus beyond wind and PV: cut "other", then nuclear below its minimum, then must-run
            c = min(cut, other_t)
            other_t -= c
            rest = cut - c
            c = min(rest, nuc_t)
            nuc_t -= c
            rest -= c
            mr_t -= min(rest, mr_t)
            price = prices["curtailment_pln_mwh"] if curt > 1e-6 else prices["surplus_pln_mwh"]
        else:
            rest = net[t]
            nx = min(rest, nuc_max - nuc_min)
            rest -= nx
            nuc_t += nx
            if p_sto > 0 and soc > 0 and rest > 0:
                cap = min(rest, p_sto, soc * eta)
                if peak_rule:
                    window = [pre[t]]
                    for k in range(t + 1, min(n_hours, t + horizon)):
                        if net[k] <= 0:
                            break
                        window.append(pre[k])
                    level = peak_threshold(window, p_sto, soc * eta)
                    dis = min(cap, max(0.0, pre[t] - level))
                else:
                    dis = cap
                soc -= dis / eta
                rest -= dis
            last = None
            displaced = None
            for b in blocks:
                head = b.capacity - mr_t * share.get(b.index, 0.0)
                if head <= 1e-9:
                    continue
                if rest <= 1e-9:
                    displaced = b
                    break
                g = min(rest, head)
                flex[b.index] = g
                rest -= g
                last = b
            ens = rest if rest > 1e-6 else 0.0
            if ens > 0:
                price = prices["scarcity_pln_mwh"]
            elif last is not None:
                price = last.srmc
            elif dis > 0:
                price = displaced.srmc if displaced is not None else prices["scarcity_pln_mwh"]
            elif nx > 0:
                price = nuc["srmc_pln_mwh"]
            else:
                price = prices["surplus_pln_mwh"]
        e_t = 0.0
        for b in blocks:
            g = flex.get(b.index, 0.0) + mr_t * share.get(b.index, 0.0)
            if g > 0:
                out[b.tech][t] += g
                e_t += g * b.co2
        keep = 1.0 - curt / vre[t] if vre[t] > 0 else 0.0
        out["pv"][t] = pv[t] * keep
        out["wind_on"][t] = won[t] * keep
        out["wind_off"][t] = woff[t] * keep
        out["other"][t] = other_t
        out["nuclear"][t] = nuc_t
        out["discharge"][t] = dis
        out["charge"][t] = ch
        out["export"][t] = ex
        out["curtail"][t] = curt
        out["cut_inflexible"][t] = cut
        out["ens"][t] = ens
        out["price"][t] = price
        out["soc"][t] = soc
        co2[t] = e_t + other_t * a["other"]["co2_t_mwh"]
    return Result(out, totals(out, demand, soc0, soc), blocks)


def totals(h: dict[str, np.ndarray], demand: np.ndarray, soc0: float, soc_end: float) -> dict[str, float]:
    twh = {f"{k}_twh": float(h[k].sum()) / 1e6 for k in ENERGY}
    load = float(demand.sum())
    vre = twh["pv_twh"] + twh["wind_on_twh"] + twh["wind_off_twh"]
    return {
        **twh,
        "demand_twh": load / 1e6,
        "vre_share": vre / (load / 1e6),
        "co2_mt": float(h["co2"].sum()) / 1e6,
        "co2_g_kwh": float(h["co2"].sum()) / load * 1e3,
        "price_mean": float(h["price"].mean()),
        "price_load_weighted": float((h["price"] * demand).sum() / load),
        "hours_price_le_0": int((h["price"] <= 0).sum()),
        "surplus_hours": int((h["surplus"] > 1e-6).sum()),
        "curtail_hours": int((h["curtail"] > 1e-6).sum()),
        "ens_hours": int((h["ens"] > 1e-6).sum()),
        "ens_max_gw": float(h["ens"].max()) / 1e3,
        "residual_min_gw": float(h["residual"].min()) / 1e3,
        "residual_max_gw": float(h["residual"].max()) / 1e3,
        "storage_delta_twh": (soc_end - soc0) / 1e6,
    }
