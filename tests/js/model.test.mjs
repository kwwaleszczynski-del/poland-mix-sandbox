// Unit tests of docs/model.js on synthetic profiles (node --test tests/js).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { simulate, peakThreshold, meritOrder } from "../../docs/model.js";

const meta = JSON.parse(readFileSync(new URL("../../docs/data/meta.json", import.meta.url), "utf-8"));
const A = meta.model;
const TODAY = meta.scenarios.today.values;

function profiles(hours = 24 * 21) {
  // deterministic made-up profiles: PV bell, slow wind wave, daily demand cycle
  const p = { demand: [], pv: [], wind_on: [], wind_off: [], other: [], mustrun: [] };
  for (let t = 0; t < hours; t++) {
    const h = t % 24;
    p.demand.push(18000 + 3000 * Math.sin(((h - 9) / 24) * 2 * Math.PI) + 500 * Math.sin(t / 13));
    p.pv.push(Math.max(0, Math.sin(((h - 6) / 12) * Math.PI)) * 0.55);
    const w = Math.min(1, Math.max(0, 0.3 + 0.3 * Math.sin(t / 37)));
    p.wind_on.push(w);
    p.wind_off.push(Math.min(1, w * 1.4));
    p.other.push(1);
    p.mustrun.push(1);
  }
  for (const k of Object.keys(p)) p[k] = Float64Array.from(p[k]);
  return p;
}

const sum = (x) => x.reduce((s, v) => s + v, 0);
const SUPPLY = ["pv", "wind_on", "wind_off", "other", "nuclear", "lignite", "hard_coal", "gas", "import", "discharge", "ens"];

const CASES = {
  base: {},
  highRes: { pv: 60, wind_on: 30, wind_off: 15, storage_gw: 10, storage_gwh: 40 },
  short: { lignite: 0, hard_coal: 0, gas: 3, import_gw: 1 },
  greedy: { pv: 50, storage_gw: 8, storage_gwh: 30, storage_rule: "greedy" },
};

for (const [name, over] of Object.entries(CASES)) {
  test(`energy balance and storage limits: ${name}`, () => {
    const p = profiles();
    const s = { ...TODAY, demand_twh: sum(p.demand) / 1e6, ...over };
    const r = simulate(p, s, A);
    const h = r.hourly;
    const eta = Math.sqrt(A.storage.rte);
    let soc = s.storage_gwh * 1000 * A.storage.initial_soc;
    for (let t = 0; t < p.demand.length; t++) {
      const supply = SUPPLY.reduce((acc, k) => acc + h[k][t], 0);
      assert.ok(Math.abs(supply - (r.demand[t] + h.charge[t] + h.export[t])) < 1e-5, `balance at ${t}`);
      assert.ok(h.soc[t] >= -1e-6 && h.soc[t] <= s.storage_gwh * 1000 + 1e-6, `soc at ${t}`);
      assert.ok(h.charge[t] <= s.storage_gw * 1000 + 1e-6 && h.discharge[t] <= s.storage_gw * 1000 + 1e-6);
      assert.ok(!(h.charge[t] > 1e-6 && h.discharge[t] > 1e-6), `charge and discharge at ${t}`);
      soc += h.charge[t] * eta - h.discharge[t] / eta;
      assert.ok(Math.abs(soc - h.soc[t]) < 1e-6);
    }
  });
}

test("energy not served only when capacity is short", () => {
  const p = profiles();
  const d = sum(p.demand) / 1e6;
  assert.equal(simulate(p, { ...TODAY, demand_twh: d }, A).totals.ens_twh, 0);
  assert.ok(simulate(p, { ...TODAY, demand_twh: d, ...CASES.short }, A).totals.ens_twh > 0);
});

test("peak threshold spends exactly the stored energy", () => {
  for (const [values, power, energy] of [[[5, 3, 1], 10, 4], [[5, 3, 1], 1.5, 2], [[2, 2, 2, 8], 3, 5], [[4], 2, 1]]) {
    const level = peakThreshold(values, power, energy);
    const used = values.reduce((s, v) => s + Math.min(power, Math.max(0, v - level)), 0);
    assert.ok(Math.abs(used - energy) < 1e-9);
  }
  assert.equal(peakThreshold([1, 2], 5, 10), 0);
});

test("merit order is sorted by marginal cost", () => {
  const blocks = meritOrder(TODAY, A);
  for (let i = 1; i < blocks.length; i++) assert.ok(blocks[i].srmc >= blocks[i - 1].srmc);
});
