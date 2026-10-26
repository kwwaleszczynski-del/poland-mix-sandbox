// Runs docs/model.js on the page data for the cases given as JSON on stdin and prints the results as JSON.
// Used by tests/test_parity.py to compare the browser model with the Python reference on identical inputs.
//
// Usage:
//   echo '{"cases":[{"scenario":{...},"weather":"pse","assumptions":{...}}]}' | node tests/js/run_model.mjs

import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const { simulate, SERIES } = await import(new URL("../../docs/model.js", import.meta.url));

const readGz = (path) => JSON.parse(gunzipSync(readFileSync(path)).toString("utf-8"));
const decode = (arr, scale) => Float64Array.from(arr, (v) => v / scale);

const ref = readGz(join(root, "docs", "data", "reference.json.gz"));
const base = {
  demand: Float64Array.from(ref.demand),
  pv: decode(ref.pv, ref.scale), wind_on: decode(ref.wind_on, ref.scale), wind_off: decode(ref.wind_off, ref.scale),
  other: decode(ref.other, ref.scale), mustrun: decode(ref.mustrun, ref.scale),
};

function profiles(weather) {
  if (weather === "pse") return base;
  const w = readGz(join(root, "docs", "data", "weather", `${weather}.json.gz`));
  return { ...base, pv: decode(w.pv, w.scale), wind_on: decode(w.wind_on, w.scale), wind_off: decode(w.wind_off, w.scale) };
}

const request = JSON.parse(readFileSync(0, "utf-8"));
const out = request.cases.map((c) => {
  const t0 = performance.now();
  const r = simulate(profiles(c.weather), c.scenario, c.assumptions);
  const ms = performance.now() - t0;
  const hourly = {};
  for (const k of SERIES) hourly[k] = Array.from(r.hourly[k]);
  return { totals: r.totals, hourly, ms };
});
process.stdout.write(JSON.stringify(out));
