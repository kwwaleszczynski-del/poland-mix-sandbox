import math

import numpy as np
import pytest
from conftest import SINKS, SUPPLY, synthetic_profiles

from mix_sandbox import model

SCENARIOS = {
    "base": {},
    "high_res": {"pv": 60.0, "wind_on": 30.0, "wind_off": 15.0, "storage_gw": 10.0, "storage_gwh": 40.0},
    "nuclear_surplus": {"nuclear": 30.0, "pv": 40.0, "export_gw": 0.0, "storage_gw": 0.0, "storage_gwh": 0.0},
    "short": {"lignite": 0.0, "hard_coal": 0.0, "gas": 3.0, "import_gw": 1.0},
    "greedy": {"pv": 50.0, "storage_gw": 8.0, "storage_gwh": 30.0, "storage_rule": "greedy"},
}


def run(profiles, today, assumptions, **over):
    # the synthetic profiles span weeks, not a year: keep their own demand instead of the annual 158 TWh
    scen = {**today, "demand_twh": float(profiles["demand"].sum()) / 1e6, **over}
    return model.simulate(profiles, scen, assumptions), scen


@pytest.mark.parametrize("name", SCENARIOS)
def test_energy_balance_every_hour(profiles, today, assumptions, name):
    r, scen = run(profiles, today, assumptions, **SCENARIOS[name])
    h = r.hourly
    demand = profiles["demand"] * scen["demand_twh"] * 1e6 / profiles["demand"].sum()
    supply = sum(h[k] for k in SUPPLY)
    sinks = sum(h[k] for k in SINKS)
    assert np.allclose(supply, demand + sinks, atol=1e-5)
    # nothing negative, curtailment never above the wind and PV available
    for key in (*SUPPLY, *SINKS, "curtail", "cut_inflexible"):
        assert h[key].min() >= -1e-9, key
    vre = 1000.0 * (scen["pv"] * profiles["pv"] + scen["wind_on"] * profiles["wind_on"]
                    + scen["wind_off"] * profiles["wind_off"])
    assert np.all(h["curtail"] <= vre + 1e-6)
    assert np.allclose(h["pv"] + h["wind_on"] + h["wind_off"] + h["curtail"], vre, atol=1e-6)


@pytest.mark.parametrize("name", SCENARIOS)
def test_storage_stays_within_limits(profiles, today, assumptions, name):
    r, scen = run(profiles, today, assumptions, **SCENARIOS[name])
    h = r.hourly
    p = scen["storage_gw"] * 1000.0
    e = scen["storage_gwh"] * 1000.0
    eta = math.sqrt(assumptions["storage"]["rte"])
    assert h["soc"].min() >= -1e-6
    assert h["soc"].max() <= e + 1e-6
    assert h["charge"].max() <= p + 1e-6
    assert h["discharge"].max() <= p + 1e-6
    assert not np.any((h["charge"] > 1e-6) & (h["discharge"] > 1e-6))
    soc = np.concatenate([[e * assumptions["storage"]["initial_soc"]], h["soc"]])
    assert np.allclose(np.diff(soc), h["charge"] * eta - h["discharge"] / eta, atol=1e-6)


def test_storage_losses_match_round_trip(profiles, today, assumptions):
    r, _ = run(profiles, today, assumptions, **SCENARIOS["high_res"])
    t = r.totals
    stored = t["storage_delta_twh"]
    rte = assumptions["storage"]["rte"]
    assert t["discharge_twh"] == pytest.approx(rte * t["charge_twh"] - math.sqrt(rte) * stored, rel=1e-9)


def test_thermal_never_below_mustrun(profiles, today, assumptions):
    r, scen = run(profiles, today, assumptions)
    thermal = r.hourly["lignite"] + r.hourly["hard_coal"] + r.hourly["gas"]
    assert thermal.min() >= scen["mustrun_gw"] * 1000.0 * profiles["mustrun"].min() - 1e-6


def test_ens_appears_only_when_capacity_is_short(profiles, today, assumptions):
    r, _ = run(profiles, today, assumptions)
    assert r.totals["ens_twh"] == 0.0
    r, _ = run(profiles, today, assumptions, **SCENARIOS["short"])
    assert r.totals["ens_twh"] > 0
    assert np.all(r.hourly["price"][r.hourly["ens"] > 0] == assumptions["prices"]["scarcity_pln_mwh"])


def test_inflexible_surplus_is_cut_after_wind_and_pv(profiles, today, assumptions):
    r, _ = run(profiles, today, assumptions, **SCENARIOS["nuclear_surplus"])
    h = r.hourly
    cut = h["cut_inflexible"] > 1e-6
    assert cut.any()
    # inflexible sources are cut only once wind and PV are fully curtailed
    assert np.allclose((h["pv"] + h["wind_on"] + h["wind_off"])[cut], 0.0, atol=1e-6)


def test_merit_order_is_sorted_and_complete(today, assumptions):
    blocks = model.merit_order(today, assumptions)
    costs = [b.srmc for b in blocks]
    assert costs == sorted(costs)
    n = assumptions["blocks_per_tech"]
    for tech in model.THERMAL:
        mine = [b for b in blocks if b.tech == tech]
        assert len(mine) == n
        assert sum(b.capacity for b in mine) == pytest.approx(today[tech] * 1000 * assumptions["tech"][tech]["availability"])


def test_price_follows_marginal_block(profiles, today, assumptions):
    r, _ = run(profiles, today, assumptions)
    costs = {round(b.srmc, 9) for b in r.blocks}
    prices = assumptions["prices"]
    allowed = costs | {prices["surplus_pln_mwh"], prices["curtailment_pln_mwh"], prices["scarcity_pln_mwh"],
                       assumptions["nuclear"]["srmc_pln_mwh"]}
    assert {round(p, 9) for p in r.hourly["price"]} <= allowed


@pytest.mark.parametrize(("values", "power", "energy"), [
    ([5.0, 3.0, 1.0], 10.0, 4.0),
    ([5.0, 3.0, 1.0], 1.5, 2.0),
    ([2.0, 2.0, 2.0, 8.0], 3.0, 5.0),
    ([4.0], 2.0, 1.0),
])
def test_peak_threshold_spends_exactly_the_energy(values, power, energy):
    level = model.peak_threshold(values, power, energy)
    used = sum(min(power, max(0.0, v - level)) for v in values)
    assert used == pytest.approx(energy)
    assert level >= 0


def test_peak_threshold_zero_when_energy_is_enough():
    assert model.peak_threshold([1.0, 2.0], 5.0, 10.0) == 0.0


def test_peak_rule_cuts_more_of_the_top_than_greedy(today, assumptions):
    prof = synthetic_profiles(hours=24 * 14, seed=3)
    over = {"pv": 45.0, "storage_gw": 6.0, "storage_gwh": 20.0, "lignite": 2.0, "hard_coal": 3.0, "gas": 4.0}
    peak, _ = run(prof, today, assumptions, **over, storage_rule="peak")
    greedy, _ = run(prof, today, assumptions, **over, storage_rule="greedy")
    top = lambda r: np.sort(r.hourly["gas"] + r.hourly["import"] + r.hourly["ens"])[-24:].sum()  # noqa: E731
    assert top(peak) <= top(greedy) + 1e-6


def test_seq_sum_is_left_to_right():
    values = [1e16, 1.0, -1e16, 1.0]
    assert model.seq_sum(values) == ((1e16 + 1.0) - 1e16) + 1.0
