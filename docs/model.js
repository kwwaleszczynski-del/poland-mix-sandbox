// Hourly merit-order dispatch of the Polish power system: the browser twin of src/mix_sandbox/model.py.
// Same steps in the same order, so both give the same numbers on the same data (checked in the tests).
//
//   1. demand is met by wind and PV, then by the inflexible sources: "other" (small CHP, biomass, hydro),
//      the must-run of large thermal units and nuclear at minimum load;
//   2. a surplus charges storage, is exported up to the limit, the rest is curtailed;
//   3. a deficit raises nuclear, discharges storage ("greedy" or "peak" rule), then dispatches thermal blocks
//      and imports by marginal cost; what is left is energy not served (ENS).
//
// Usage:
//   import { simulate } from "./model.js";
//   const r = simulate(profiles, scenario, assumptions);   // r.totals.co2_mt, r.hourly.gas (Float64Array, MW)

export const THERMAL = ["lignite", "hard_coal", "gas"];
export const ENERGY = ["pv", "wind_on", "wind_off", "other", "nuclear", "lignite", "hard_coal", "gas", "import",
  "discharge", "charge", "export", "curtail", "cut_inflexible", "ens"];
export const SERIES = [...ENERGY, "price", "soc", "residual", "surplus", "co2"];

export function meritOrder(scenario, a) {
  const co2Price = a.co2_price_pln_t;
  const n = a.blocks_per_tech;
  const blocks = [];
  for (const tech of THERMAL) {
    const t = a.tech[tech];
    const cap = scenario[tech] * 1000.0 * t.availability / n;
    for (let k = 0; k < n; k++) {
      const eff = t.eff_best + (t.eff_worst - t.eff_best) * (k + 0.5) / n;
      const co2 = t.ef_t_gj * 3.6 / eff;
      const srmc = t.fuel_pln_gj * 3.6 / eff + co2Price * co2 + t.vom_pln_mwh;
      blocks.push({ tech, capacity: cap, srmc, co2 });
    }
  }
  const imp = a.import;
  blocks.push({ tech: "import", capacity: scenario.import_gw * 1000.0 * imp.availability, srmc: imp.price_pln_mwh, co2: 0.0 });
  blocks.forEach((b, i) => { b.index = i; });
  return blocks.sort((p, q) => (p.srmc - q.srmc) || (p.index - q.index));
}

// Level L >= 0 with sum(min(power, max(0, v - L))) == energy over the window; 0 if even L = 0 needs less.
export function peakThreshold(values, power, energy) {
  let total = 0.0;
  for (const v of values) total += Math.min(power, v);
  if (total <= energy) return 0.0;
  const points = [];
  for (const v of values) {
    points.push([v, 1]);
    if (v - power > 0) points.push([v - power, -1]);
  }
  points.sort((p, q) => (q[0] - p[0]) || (q[1] - p[1]));
  let f = 0.0;
  let slope = 0;
  let prev = points[0][0];
  for (const [level, step] of points) {
    const nxt = f + slope * (prev - level);
    if (nxt >= energy && slope > 0) return prev - (energy - f) / slope;
    f = nxt;
    prev = level;
    slope += step;
  }
  return slope > 0 ? Math.max(0.0, prev - (energy - f) / slope) : 0.0;
}

export function simulate(profiles, scenario, a) {
  const demand0 = profiles.demand;
  const H = demand0.length;
  let sum0 = 0.0;
  for (let t = 0; t < H; t++) sum0 += demand0[t];
  const scale = scenario.demand_twh * 1e6 / sum0;

  const blocks = meritOrder(scenario, a);
  const nb = blocks.length;
  let thermalCap = 0.0;
  for (const b of blocks) if (b.tech !== "import") thermalCap += b.capacity;
  const share = new Float64Array(nb);
  blocks.forEach((b, j) => { share[j] = b.tech !== "import" && thermalCap > 0 ? b.capacity / thermalCap : 0.0; });

  const nuc = a.nuclear;
  const nucMax = scenario.nuclear * 1000.0 * nuc.availability;
  const nucMin = nucMax * nuc.min_load;
  let pSto = scenario.storage_gw * 1000.0;
  let eSto = scenario.storage_gwh * 1000.0;
  if (pSto <= 0 || eSto <= 0) { pSto = 0.0; eSto = 0.0; }
  const eta = Math.sqrt(a.storage.rte);
  let soc = eSto * a.storage.initial_soc;
  const soc0 = soc;
  const expCap = scenario.export_gw * 1000.0 * a.export.availability;
  const prices = a.prices;
  const peakRule = (scenario.storage_rule || "peak") === "peak";
  const horizon = a.lookahead_h | 0;

  const out = {};
  for (const k of SERIES) out[k] = new Float64Array(H);
  const demand = new Float64Array(H), pv = new Float64Array(H), won = new Float64Array(H), woff = new Float64Array(H);
  const other = new Float64Array(H), vre = new Float64Array(H), mustrun = new Float64Array(H);
  const net = new Float64Array(H), pre = new Float64Array(H);
  for (let t = 0; t < H; t++) {
    demand[t] = demand0[t] * scale;
    pv[t] = scenario.pv * 1000.0 * profiles.pv[t];
    won[t] = scenario.wind_on * 1000.0 * profiles.wind_on[t];
    woff[t] = scenario.wind_off * 1000.0 * profiles.wind_off[t];
    other[t] = scenario.other * 1000.0 * profiles.other[t];
    mustrun[t] = Math.min(scenario.mustrun_gw * 1000.0 * profiles.mustrun[t], thermalCap);
    vre[t] = pv[t] + won[t] + woff[t];
    net[t] = demand[t] - vre[t] - other[t] - mustrun[t] - nucMin;
    pre[t] = Math.max(0.0, net[t] - (nucMax - nucMin));
    out.residual[t] = demand[t] - vre[t];
    out.surplus[t] = Math.max(0.0, -net[t]);
  }

  const flex = new Float64Array(nb);
  const window = [];
  for (let t = 0; t < H; t++) {
    let mr = mustrun[t];
    let nucT = nucMin;
    let otherT = other[t];
    let ch = 0.0, ex = 0.0, curt = 0.0, cut = 0.0, dis = 0.0, ens = 0.0, price;
    flex.fill(0.0);
    if (net[t] <= 0) {
      let surplus = -net[t];
      if (pSto > 0) {
        ch = Math.min(surplus, pSto, (eSto - soc) / eta);
        soc += ch * eta;
        surplus -= ch;
      }
      ex = Math.min(surplus, expCap);
      surplus -= ex;
      curt = Math.min(surplus, vre[t]);
      cut = surplus - curt;
      let c = Math.min(cut, otherT);
      otherT -= c;
      let rest = cut - c;
      c = Math.min(rest, nucT);
      nucT -= c;
      rest -= c;
      mr -= Math.min(rest, mr);
      price = curt > 1e-6 ? prices.curtailment_pln_mwh : prices.surplus_pln_mwh;
    } else {
      let rest = net[t];
      const nx = Math.min(rest, nucMax - nucMin);
      rest -= nx;
      nucT += nx;
      if (pSto > 0 && soc > 0 && rest > 0) {
        const cap = Math.min(rest, pSto, soc * eta);
        if (peakRule) {
          window.length = 0;
          window.push(pre[t]);
          const end = Math.min(H, t + horizon);
          for (let k = t + 1; k < end; k++) {
            if (net[k] <= 0) break;
            window.push(pre[k]);
          }
          const level = peakThreshold(window, pSto, soc * eta);
          dis = Math.min(cap, Math.max(0.0, pre[t] - level));
        } else {
          dis = cap;
        }
        soc -= dis / eta;
        rest -= dis;
      }
      let last = -1, displaced = -1;
      for (let j = 0; j < nb; j++) {
        const head = blocks[j].capacity - mr * share[j];
        if (head <= 1e-9) continue;
        if (rest <= 1e-9) { displaced = j; break; }
        const g = Math.min(rest, head);
        flex[j] = g;
        rest -= g;
        last = j;
      }
      ens = rest > 1e-6 ? rest : 0.0;
      if (ens > 0) price = prices.scarcity_pln_mwh;
      else if (last >= 0) price = blocks[last].srmc;
      else if (dis > 0) price = displaced >= 0 ? blocks[displaced].srmc : prices.scarcity_pln_mwh;
      else if (nx > 0) price = nuc.srmc_pln_mwh;
      else price = prices.surplus_pln_mwh;
    }
    let e = 0.0;
    for (let j = 0; j < nb; j++) {
      const g = flex[j] + mr * share[j];
      if (g > 0) {
        out[blocks[j].tech][t] += g;
        e += g * blocks[j].co2;
      }
    }
    const keep = vre[t] > 0 ? 1.0 - curt / vre[t] : 0.0;
    out.pv[t] = pv[t] * keep;
    out.wind_on[t] = won[t] * keep;
    out.wind_off[t] = woff[t] * keep;
    out.other[t] = otherT;
    out.nuclear[t] = nucT;
    out.discharge[t] = dis;
    out.charge[t] = ch;
    out.export[t] = ex;
    out.curtail[t] = curt;
    out.cut_inflexible[t] = cut;
    out.ens[t] = ens;
    out.price[t] = price;
    out.soc[t] = soc;
    out.co2[t] = e + otherT * a.other.co2_t_mwh;
  }
  return { hourly: out, demand, totals: totals(out, demand, soc0, soc), blocks };
}

function sum(x) {
  let s = 0.0;
  for (let i = 0; i < x.length; i++) s += x[i];
  return s;
}

function count(x, pred) {
  let c = 0;
  for (let i = 0; i < x.length; i++) if (pred(x[i])) c++;
  return c;
}

export function totals(h, demand, soc0, socEnd) {
  const r = {};
  for (const k of ENERGY) r[`${k}_twh`] = sum(h[k]) / 1e6;
  const load = sum(demand);
  const vre = r.pv_twh + r.wind_on_twh + r.wind_off_twh;
  let pw = 0.0, emax = 0.0, rmin = Infinity, rmax = -Infinity;
  for (let t = 0; t < demand.length; t++) {
    pw += h.price[t] * demand[t];
    if (h.ens[t] > emax) emax = h.ens[t];
    if (h.residual[t] < rmin) rmin = h.residual[t];
    if (h.residual[t] > rmax) rmax = h.residual[t];
  }
  Object.assign(r, {
    demand_twh: load / 1e6,
    vre_share: vre / (load / 1e6),
    co2_mt: sum(h.co2) / 1e6,
    co2_g_kwh: sum(h.co2) / load * 1e3,
    price_mean: sum(h.price) / demand.length,
    price_load_weighted: pw / load,
    hours_price_le_0: count(h.price, (v) => v <= 0),
    surplus_hours: count(h.surplus, (v) => v > 1e-6),
    curtail_hours: count(h.curtail, (v) => v > 1e-6),
    ens_hours: count(h.ens, (v) => v > 1e-6),
    ens_max_gw: emax / 1e3,
    residual_min_gw: rmin / 1e3,
    residual_max_gw: rmax / 1e3,
    storage_delta_twh: (socEnd - soc0) / 1e6,
  });
  return r;
}
