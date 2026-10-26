// Page logic: sliders -> scenario -> hourly dispatch (model.js) -> tiles, charts, tables; state in the URL hash.

import { simulate } from "./model.js";
import { Chart, cssVar } from "./charts.js";

const CONTROLS = [
  { group: "Wiatr i słońce", items: [
    { key: "pv", url: "pv", label: "Fotowoltaika", unit: "GW", min: 0, max: 80, step: 0.1, color: "--c-pv" },
    { key: "wind_on", url: "won", label: "Wiatr na lądzie", unit: "GW", min: 0, max: 50, step: 0.1, color: "--c-wind" },
    { key: "wind_off", url: "woff", label: "Wiatr na morzu", unit: "GW", min: 0, max: 30, step: 0.1, color: "--c-wind" },
  ] },
  { group: "Elektrownie sterowalne", items: [
    { key: "nuclear", url: "nuc", label: "Atom", unit: "GW", min: 0, max: 20, step: 0.1, color: "--c-nuclear" },
    { key: "lignite", url: "lig", label: "Węgiel brunatny", unit: "GW", min: 0, max: 10, step: 0.1, color: "--c-coal" },
    { key: "hard_coal", url: "hc", label: "Węgiel kamienny", unit: "GW", min: 0, max: 25, step: 0.1, color: "--c-coal" },
    { key: "gas", url: "gas", label: "Gaz", unit: "GW", min: 0, max: 35, step: 0.1, color: "--c-gas" },
    { key: "other", url: "oth", label: "Inne: małe EC, biomasa, woda (średnio)", unit: "GW", min: 0, max: 6, step: 0.05, color: "--c-other" },
    { key: "mustrun_gw", url: "mr", label: "Minimum pracy dużych bloków (średnio)", unit: "GW", min: 0, max: 15, step: 0.1 },
  ] },
  { group: "Magazyny energii", items: [
    { key: "storage_gw", url: "sgw", label: "Moc magazynów", unit: "GW", min: 0, max: 50, step: 0.1, color: "--c-storage" },
    { key: "storage_gwh", url: "sgwh", label: "Pojemność magazynów", unit: "GWh", min: 0, max: 300, step: 0.5, color: "--c-storage" },
  ] },
  { group: "Połączenia transgraniczne", items: [
    { key: "import_gw", url: "imp", label: "Import, limit", unit: "GW", min: 0, max: 15, step: 0.1, color: "--c-import" },
    { key: "export_gw", url: "exp", label: "Eksport, limit", unit: "GW", min: 0, max: 15, step: 0.1, color: "--c-import" },
  ] },
  { group: "Zapotrzebowanie", items: [
    { key: "demand_twh", url: "dem", label: "Zapotrzebowanie roczne", unit: "TWh", min: 100, max: 320, step: 0.5 },
  ] },
];
const PRICE_CONTROLS = [
  { key: "co2_eur", url: "co2", label: "Cena uprawnień CO₂", unit: "EUR/t", min: 0, max: 300, step: 1 },
  { key: "gas_eur", url: "gp", label: "Cena gazu", unit: "EUR/MWh", min: 5, max: 150, step: 1 },
  { key: "coal_pln", url: "cp", label: "Cena węgla kamiennego", unit: "PLN/GJ", min: 5, max: 50, step: 0.5 },
];
const ALL = [...CONTROLS.flatMap((g) => g.items), ...PRICE_CONTROLS];

// stack order bottom -> top was checked for colour-vision separation of neighbouring layers
const UP = [
  { key: "nuclear", label: "Atom", color: "--c-nuclear" },
  { key: "coal", label: "Węgiel", color: "--c-coal" },
  { key: "other", label: "Inne (małe EC, biomasa, woda)", color: "--c-other" },
  { key: "wind", label: "Wiatr", color: "--c-wind" },
  { key: "gas", label: "Gaz", color: "--c-gas" },
  { key: "discharge", label: "Magazyn: rozładowanie", color: "--c-storage" },
  { key: "pv", label: "Fotowoltaika", color: "--c-pv" },
  { key: "import", label: "Import", color: "--c-import" },
  { key: "curtail", label: "Obcięte wiatr i PV", color: "--c-curtail", hatch: true },
  { key: "ens", label: "Energia niedostarczona", color: "--critical", hatch: true },
];
const DOWN = [
  { key: "charge", label: "Magazyn: ładowanie", color: "--c-storage" },
  { key: "export", label: "Eksport", color: "--c-import" },
];

const BAR_ROWS = [
  ["pv", "Fotowoltaika", "--c-pv"], ["wind_on", "Wiatr na lądzie", "--c-wind"], ["wind_off", "Wiatr na morzu", "--c-wind"],
  ["nuclear", "Atom", "--c-nuclear"], ["lignite", "Węgiel brunatny", "--c-coal"], ["hard_coal", "Węgiel kamienny", "--c-coal"],
  ["gas", "Gaz", "--c-gas"], ["other", "Inne", "--c-other"], ["import", "Import", "--c-import"],
  ["discharge", "Magazyn: rozładowanie", "--c-storage"], null,
  ["export", "Eksport", "--c-import"], ["charge", "Magazyn: ładowanie", "--c-storage"],
  ["curtail", "Obcięte wiatr i PV", "--c-curtail", true], ["ens", "Energia niedostarczona", "--critical", true],
];

const VALIDATION_LABELS = {
  lignite_twh: "Węgiel brunatny, bloki ≥ 100 MW", hard_coal_twh: "Węgiel kamienny, bloki ≥ 100 MW",
  gas_twh: "Gaz, bloki ≥ 100 MW", large_thermal_twh: "Duże bloki cieplne razem", import_twh: "Import (saldo godzinowe > 0)",
  export_twh: "Eksport (saldo godzinowe < 0)", net_import_twh: "Import netto", storage_charge_twh: "Ładowanie magazynów",
  storage_discharge_twh: "Rozładowanie (szczytowo-pompowe ≥ 100 MW)", curtailment_twh: "Obcięcia OZE (redysponowanie PSE)",
  curtailment_hours: "Godziny z obcięciami", price_mean: "Cena średnia (RCE)", price_median: "Cena mediana (RCE)",
  hours_price_le_0: "Godziny z ceną ≤ 0", ens_twh: "Energia niedostarczona",
};

const fmt = (v, d = 1) => Number(v).toLocaleString("pl-PL", { minimumFractionDigits: d, maximumFractionDigits: d });
const $ = (id) => document.getElementById(id);

let META, REF, BASE_PROFILES;
const WEATHER = new Map();
const state = { values: {}, weather: "pse", rule: "peak", preset: null };
let result = null;
let baseline = null;
let week = 3;
let lastHash = "";

async function loadJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  const buf = new Uint8Array(await res.arrayBuffer());
  // the files are gzip; a server may already have decoded them (Content-Encoding), so check the magic bytes
  if (buf[0] === 0x1f && buf[1] === 0x8b) {
    const stream = new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"));
    return JSON.parse(await new Response(stream).text());
  }
  return JSON.parse(new TextDecoder().decode(buf));
}

const decode = (arr, scale) => Float64Array.from(arr, (v) => v / scale);

async function profilesFor(weather) {
  if (weather === "pse") return BASE_PROFILES;
  if (!WEATHER.has(weather)) {
    const w = await loadJson(`data/weather/${weather}.json.gz`);
    WEATHER.set(weather, { ...BASE_PROFILES, pv: decode(w.pv, w.scale), wind_on: decode(w.wind_on, w.scale), wind_off: decode(w.wind_off, w.scale) });
  }
  return WEATHER.get(weather);
}

function assumptions() {
  const a = structuredClone(META.model);
  const p = META.assumptions;
  const eur = p.prices.eur_pln;
  const v = state.values;
  // use the exact numbers of the build unless a price was moved, so the defaults match the Python model
  if (v.co2_eur !== p.prices.co2_eur_t) a.co2_price_pln_t = v.co2_eur * eur;
  if (v.gas_eur !== p.tech.gas.fuel_eur_mwh_th) a.tech.gas.fuel_pln_gj = v.gas_eur * eur / 3.6;
  if (v.coal_pln !== p.tech.hard_coal.fuel_pln_gj) a.tech.hard_coal.fuel_pln_gj = v.coal_pln;
  return a;
}

function priceDefaults() {
  const p = META.assumptions;
  return { co2_eur: p.prices.co2_eur_t, gas_eur: p.tech.gas.fuel_eur_mwh_th, coal_pln: p.tech.hard_coal.fuel_pln_gj };
}

function scenario() {
  const s = {};
  for (const c of CONTROLS.flatMap((g) => g.items)) s[c.key] = state.values[c.key];
  s.storage_rule = state.rule;
  return s;
}

// ---------------------------------------------------------------- controls

function buildControls() {
  const make = (c) => {
    const row = document.createElement("div");
    row.className = "ctrl";
    const id = `in-${c.key}`;
    row.innerHTML = `<label for="${id}">${c.color ? `<span class="key" style="background:var(${c.color})"></span>` : ""}${c.label}</label>` +
      `<output id="out-${c.key}" for="${id}"></output>` +
      `<input type="range" id="${id}" min="${c.min}" max="${c.max}" step="${c.step}">`;
    row.querySelector("input").addEventListener("input", (ev) => {
      state.values[c.key] = Number(ev.target.value);
      state.preset = null;
      update();
    });
    return row;
  };
  const host = $("controls");
  for (const g of CONTROLS) {
    const fs = document.createElement("fieldset");
    fs.innerHTML = `<legend>${g.group}</legend>`;
    for (const c of g.items) fs.append(make(c));
    host.append(fs);
  }
  for (const c of PRICE_CONTROLS) $("controls-prices").append(make(c));

  const presets = $("presets");
  for (const [key, sc] of Object.entries(META.scenarios)) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.preset = key;
    b.textContent = sc.label;
    b.addEventListener("click", () => applyPreset(key));
    presets.append(b);
  }

  const sel = $("weather");
  const years = Object.entries(META.weather_years).sort((x, y) => Number(y[0]) - Number(x[0]));
  const windiest = years.reduce((m, y) => (y[1].wind_on > m[1].wind_on ? y : m));
  const calmest = years.reduce((m, y) => (y[1].wind_on < m[1].wind_on ? y : m));
  sel.innerHTML = `<option value="pse">2025: pomiar PSE</option>` + years.map(([y, s]) => {
    const tag = y === windiest[0] ? ", najbardziej wietrzny" : y === calmest[0] ? ", najmniej wietrzny" : "";
    return `<option value="${y}">${y}: ERA5 (wiatr ${fmt(s.wind_on * 100, 1)}%${tag})</option>`;
  }).join("");
  sel.addEventListener("change", async () => { state.weather = sel.value; await update(); });
  $("rule").addEventListener("change", (ev) => { state.rule = ev.target.value; update(); });

  $("week").addEventListener("input", (ev) => { week = Number(ev.target.value); renderWeek(); });
  $("week-hard").addEventListener("click", () => { week = pickWeek("hard"); $("week").value = week; renderWeek(); });
  $("week-surplus").addEventListener("click", () => { week = pickWeek("surplus"); $("week").value = week; renderWeek(); });
  $("share").addEventListener("click", share);
  $("theme").addEventListener("click", toggleTheme);
}

function syncControls() {
  for (const c of ALL) {
    const v = state.values[c.key];
    $(`in-${c.key}`).value = v;
    $(`out-${c.key}`).textContent = `${fmt(v, c.step < 1 ? (c.step < 0.1 ? 2 : 1) : 0)} ${c.unit}`;
  }
  $("weather").value = state.weather;
  $("rule").value = state.rule;
  for (const b of $("presets").querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.preset === state.preset));
  const sc = state.preset ? META.scenarios[state.preset] : null;
  $("preset-note").textContent = sc ? sc.note : "Własny scenariusz.";
  const w = state.weather;
  $("weather-note").textContent = w === "pse"
    ? "Wiatr na lądzie i PV zmierzone przez PSE w 2025 (z dodanym redysponowaniem), wiatr na morzu z ERA5. 2025 był rokiem słabego wiatru."
    : `Wiatr i PV z modelu ERA5 dla ${w}, skalibrowanego na danych PSE 2025; zapotrzebowanie zawsze z 2025.`;
}

function applyPreset(key) {
  const sc = META.scenarios[key];
  state.preset = key;
  for (const c of CONTROLS.flatMap((g) => g.items)) state.values[c.key] = sc.values[c.key];
  Object.assign(state.values, priceDefaults());
  state.rule = sc.values.storage_rule;
  update();
}

// ---------------------------------------------------------------- URL state

function writeHash() {
  const q = new URLSearchParams();
  if (state.preset) q.set("s", state.preset);
  for (const c of ALL) q.set(c.url, String(state.values[c.key]));
  q.set("wy", state.weather);
  q.set("r", state.rule);
  lastHash = q.toString();
  history.replaceState(null, "", `#${lastHash}`);
}

function readHash() {
  const q = new URLSearchParams(location.hash.slice(1));
  const preset = q.get("s");
  const base = META.scenarios[preset] ? preset : "today";
  const sc = META.scenarios[base];
  for (const c of CONTROLS.flatMap((g) => g.items)) state.values[c.key] = sc.values[c.key];
  Object.assign(state.values, priceDefaults());
  state.rule = sc.values.storage_rule;
  state.preset = base;
  let custom = false;
  for (const c of ALL) {
    if (!q.has(c.url)) continue;
    const v = Number(q.get(c.url));
    if (!Number.isFinite(v)) continue;
    const clamped = Math.min(c.max, Math.max(c.min, v));
    if (clamped !== state.values[c.key]) custom = true;
    state.values[c.key] = clamped;
  }
  const wy = q.get("wy");
  if (wy && (wy === "pse" || META.weather_years[wy])) state.weather = wy;
  const r = q.get("r");
  if (r === "peak" || r === "greedy") { if (r !== state.rule) custom = true; state.rule = r; }
  if (custom || !META.scenarios[preset]) state.preset = custom ? null : base;
}

async function share() {
  writeHash();
  try {
    await navigator.clipboard.writeText(location.href);
    toast("Link skopiowany");
  } catch {
    toast("Skopiuj adres z paska przeglądarki");
  }
}

function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.style.display = "block";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.style.display = "none"; }, 1800);
}

function toggleTheme() {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("theme", root.dataset.theme); } catch { /* storage may be blocked */ }
  redraw();
}

// ---------------------------------------------------------------- render

// slider events come faster than a year can be computed: coalesce them into one run per macrotask
let scheduled = null;
function update() {
  syncControls();
  writeHash();
  if (!scheduled) {
    scheduled = new Promise((resolve, reject) => setTimeout(() => {
      scheduled = null;
      compute().then(resolve, reject);
    }, 0));
  }
  return scheduled;
}

async function compute() {
  const prof = await profilesFor(state.weather);
  result = simulate(prof, scenario(), assumptions());
  renderTiles();
  renderBars();
  renderWeek();
  renderDuration();
}

function redraw() {
  if (!result) return;
  for (const c of [weekChart, priceChart, residualChart, durationChart]) c.draw();
  renderBars();
}

function tile(label, value, detail, extra = "") {
  return `<div class="tile"><div class="label">${label}</div><div class="value">${value}</div>` +
    `<div class="detail">${detail}</div>${extra}</div>`;
}

function delta(v, base, unit, d = 0, lowerIsGood = true) {
  if (baseline === null || state.preset === "today") return "";
  const x = v - base;
  if (Math.abs(x) < 10 ** -d / 2) return `<div class="delta">jak dziś</div>`;
  const sign = x > 0 ? "+" : "−";
  const good = (x < 0) === lowerIsGood;
  return `<div class="delta">${sign}${fmt(Math.abs(x), d)} ${unit} vs dziś <span class="status ${good ? "ok" : "bad"}">${good ? "▼" : "▲"}</span></div>`;
}

function renderTiles() {
  const t = result.totals;
  const b = baseline;
  const ensGwh = t.ens_twh * 1000;
  const ensStatus = t.ens_hours > 0
    ? `<span class="status bad">⚠ ${t.ens_hours} h, maks. ${fmt(t.ens_max_gw, 1)} GW</span>`
    : `<span class="status ok">✓ zapotrzebowanie pokryte</span>`;
  $("tiles").innerHTML = [
    tile("Emisje CO₂", `${fmt(t.co2_mt, 1)} Mt`, `${fmt(t.co2_g_kwh, 0)} g/kWh zapotrzebowania`, delta(t.co2_mt, b?.co2_mt, "Mt", 1)),
    tile("Wiatr i PV w zapotrzebowaniu", `${fmt(t.vre_share * 100, 1)}%`, `${fmt(t.pv_twh + t.wind_on_twh + t.wind_off_twh, 1)} TWh po obcięciach`),
    tile("Obcięcia wiatru i PV", `${fmt(t.curtail_twh, 2)} TWh`, `${t.curtail_hours} h z obcięciami`, delta(t.curtail_twh, b?.curtail_twh, "TWh", 2)),
    tile("Energia niedostarczona", ensGwh >= 1000 ? `${fmt(t.ens_twh, 2)} TWh` : `${fmt(ensGwh, ensGwh < 10 ? 1 : 0)} GWh`, ensStatus),
    tile("Cena przybliżona", `${fmt(t.price_mean, 0)} PLN/MWh`, `${t.hours_price_le_0} h z ceną ≤ 0`, delta(t.price_mean, b?.price_mean, "PLN/MWh", 0)),
    tile("Godziny z nadwyżką", `${t.surplus_hours.toLocaleString("pl-PL")} h`, `eksport ${fmt(t.export_twh, 1)}, ładowanie ${fmt(t.charge_twh, 1)} TWh`),
    tile("Import netto", `${fmt(t.import_twh - t.export_twh, 1)} TWh`, `import ${fmt(t.import_twh, 1)} TWh`),
  ].join("");
  $("mini").innerHTML = `<span>CO₂ <b>${fmt(t.co2_mt, 1)} Mt</b></span><span>wiatr i PV <b>${fmt(t.vre_share * 100, 0)}%</b></span>` +
    `<span>obcięcia <b>${fmt(t.curtail_twh, 1)} TWh</b></span><span>niedobór <b>${fmt(t.ens_twh * 1000, 0)} GWh</b></span>` +
    `<span>cena <b>${fmt(t.price_mean, 0)} PLN/MWh</b></span>`;
}

function renderBars() {
  const t = result.totals;
  const vals = BAR_ROWS.filter(Boolean).map((r) => t[`${r[0]}_twh`]);
  const max = Math.max(...vals, 1e-9);
  const html = [];
  for (const r of BAR_ROWS) {
    if (!r) { html.push(`<div class="sep"></div>`); continue; }
    const [key, label, color, hatched] = r;
    const v = t[`${key}_twh`];
    const bg = hatched ? `repeating-linear-gradient(45deg, var(${color}) 0 2px, transparent 2px 5px)` : `var(${color})`;
    html.push(`<div class="name"><span class="key" style="background:${bg}"></span>${label}</div>` +
      `<div class="track"><div class="bar" style="width:${(v / max * 100).toFixed(2)}%;background:${bg}"></div></div>` +
      `<div class="val">${fmt(v, 1)}</div>`);
  }
  $("bars").innerHTML = html.join("");
  const rows = BAR_ROWS.filter(Boolean).map(([key, label]) => `<tr><td>${label}</td><td class="r">${fmt(t[`${key}_twh`], 2)}</td></tr>`);
  $("balance-table").innerHTML = `<thead><tr><th>Pozycja</th><th class="r">TWh</th></tr></thead><tbody>${rows.join("")}` +
    `<tr><td>Zapotrzebowanie</td><td class="r">${fmt(t.demand_twh, 2)}</td></tr>` +
    `<tr><td>Zmiana zapasu w magazynach</td><td class="r">${fmt(t.storage_delta_twh, 3)}</td></tr></tbody>`;
}

const DAY = ["nd", "pn", "wt", "śr", "cz", "pt", "sb"];
function localTime(h) {
  return new Date(Date.parse(REF.start_utc) + h * 3600e3);
}
function localLabel(h, withHour = true) {
  const d = localTime(h);
  const parts = new Intl.DateTimeFormat("pl-PL", { timeZone: "Europe/Warsaw", weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", hour12: false }).formatToParts(d);
  const get = (t) => parts.find((p) => p.type === t)?.value ?? "";
  return withHour ? `${get("weekday")} ${get("day")}.${get("month")} ${get("hour")}:00` : `${get("weekday")} ${get("day")}.${get("month")}`;
}

function weekSlice(w) {
  const from = (w - 1) * 168;
  return [from, from + 168];
}

function pickWeek(kind) {
  const h = result.hourly;
  let best = 1, bestScore = -Infinity;
  for (let w = 1; w <= 52; w++) {
    const [a, b] = weekSlice(w);
    let s = 0;
    for (let i = a; i < b; i++) {
      s += kind === "hard" ? h.ens[i] * 100 + h.residual[i] : h.curtail[i] + h.export[i] + h.charge[i];
    }
    if (s > bestScore) { bestScore = s; best = w; }
  }
  return best;
}

let weekChart, priceChart, residualChart, durationChart, weekData = null;

function seriesOf(key, a, b) {
  const h = result.hourly;
  const out = new Float64Array(b - a);
  for (let i = a; i < b; i++) {
    out[i - a] = key === "coal" ? h.lignite[i] + h.hard_coal[i]
      : key === "wind" ? h.wind_on[i] + h.wind_off[i] : h[key][i];
  }
  return out;
}

function renderWeek() {
  const [a, b] = weekSlice(week);
  $("week-title").textContent = `${localLabel(a, false)} – ${localLabel(b - 1, false)}, tydzień ${week}`;
  const up = UP.map((l) => ({ ...l, values: seriesOf(l.key, a, b) }));
  const down = DOWN.map((l) => ({ ...l, values: seriesOf(l.key, a, b) }));
  const demand = result.demand.slice(a, b);
  weekData = { a, up, down, demand };
  weekChart.set({ n: b - a, up, down, line: { values: demand } });
  const price = seriesOf("price", a, b);
  priceChart.set({ n: b - a, series: [{ values: price, color: "--ink-2" }] });
  const present = new Set([...up, ...down].filter((l) => l.values.some((v) => v > 0.5)).map((l) => l.key));
  $("week-legend").innerHTML = [...UP, ...DOWN].filter((l) => present.has(l.key)).map((l) =>
    `<span><span class="key${l.hatch ? " hatch" : ""}" style="${l.hatch ? `color:var(${l.color})` : `background:var(${l.color})`}"></span>${l.label}</span>`).join("") +
    `<span><span class="key" style="height:2px;background:var(--ink)"></span>Zapotrzebowanie</span>`;
}

function weekTooltip(i) {
  const d = weekData;
  const rows = [...d.up].reverse().concat(d.down).filter((l) => l.values[i] > 0.5).map((l) =>
    `<div class="row"><span><span class="key" style="background:var(${l.color})"></span>${l.label}${d.down.includes(l) ? " (−)" : ""}</span><span class="num">${fmt(l.values[i] / 1000, 2)} GW</span></div>`);
  return `<div class="title">${localLabel(d.a + i)}</div>` +
    `<div class="row"><span>Zapotrzebowanie</span><span class="num">${fmt(d.demand[i] / 1000, 2)} GW</span></div>${rows.join("")}` +
    `<div class="row"><span>Cena</span><span class="num">${fmt(result.hourly.price[d.a + i], 0)} PLN/MWh</span></div>`;
}

function downsample(sorted, points = 730) {
  const n = sorted.length;
  const out = new Float64Array(points);
  for (let k = 0; k < points; k++) out[k] = sorted[Math.min(n - 1, Math.round(k / (points - 1) * (n - 1)))];
  return out;
}

let durationData = null;
function renderDuration() {
  const res = Float64Array.from(result.hourly.residual).sort().reverse();
  const pr = Float64Array.from(result.hourly.price).sort().reverse();
  durationData = { res: downsample(res), price: downsample(pr), n: res.length };
  residualChart.set({ n: durationData.res.length, series: [{ values: durationData.res, color: "--c-wind" }] });
  durationChart.set({ n: durationData.price.length, series: [{ values: durationData.price, color: "--c-gas" }] });
}

function hourTicks(n) {
  return [0, 2000, 4000, 6000, 8000].map((h) => ({ i: Math.round(h / 8759 * (n - 1)), label: `${h.toLocaleString("pl-PL")} h` }));
}

function dayTicks(n, width) {
  const out = [];
  if (!weekData) return out;
  const perDay = width / 7;
  const short = perDay < 72;
  const every = perDay < 40 ? 2 : 1;
  let day = 0;
  for (let i = 0; i < 168; i++) {
    const hour = Number(new Intl.DateTimeFormat("pl-PL", { timeZone: "Europe/Warsaw", hour: "2-digit", hour12: false }).format(localTime(weekData.a + i)));
    if (hour !== 0) continue;
    if (day++ % every === 0) {
      const label = localLabel(weekData.a + i, false);
      out.push({ i, label: short ? label.split(" ")[1] : label });
    }
  }
  return out;
}

function renderValidation() {
  const v = META.validation;
  if (!v) return;
  const rows = Object.entries(v.rows).map(([k, r]) => {
    const d = r.unit === "h" || r.unit === "PLN/MWh" ? 0 : 1;
    return `<tr><td>${VALIDATION_LABELS[k] ?? k}</td><td class="r">${fmt(r.actual, d)}</td><td class="r">${fmt(r.model, d)}</td><td>${r.unit}</td></tr>`;
  });
  $("validation-table").innerHTML = `<thead><tr><th>Wielkość 2025</th><th class="r">PSE</th><th class="r">Model</th><th></th></tr></thead><tbody>${rows.join("")}</tbody>`;
  const hh = v.hourly;
  $("validation-note").textContent = `Godzinowo: duże bloki cieplne R² ${fmt(hh.large_thermal_r2, 2)} (korelacja ${fmt(hh.large_thermal_corr, 2)}), ` +
    `cena: korelacja z RCE ${fmt(hh.price_corr, 2)}, rangowa ${fmt(hh.price_spearman, 2)}, średni błąd ${fmt(hh.price_mae, 0)} PLN/MWh. ` +
    "Model zaniża eksport (eksportuje tylko nadwyżkę, a w 2025 Polska eksportowała też przy wyższych cenach u sąsiadów), " +
    "zaniża gaz (elektrociepłownie pracują pod ciepło) i cenę średnią (brak narzutów i kosztów uruchomień).";
}

function renderSources() {
  const s = META.sources || {};
  $("sources").innerHTML = "Źródła założeń: " + Object.values(s).map((txt) => {
    const m = txt.match(/https?:\/\/\S+/);
    const label = txt.replace(/:?\s*https?:\/\/\S+/, "").replace(/[,;]\s*$/, "");
    return m ? `<a href="${m[0]}" rel="noopener">${label}</a>` : label;
  }).join("; ") + `. Dane zbudowane ${META.built}.`;
}

async function main() {
  try {
    const t = localStorage.getItem("theme");
    if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  } catch { /* storage may be blocked */ }
  $("tiles").innerHTML = `<p class="loading">Ładowanie danych…</p>`;
  [META, REF] = await Promise.all([loadJson("data/meta.json"), loadJson("data/reference.json.gz")]);
  BASE_PROFILES = {
    demand: Float64Array.from(REF.demand),
    pv: decode(REF.pv, REF.scale), wind_on: decode(REF.wind_on, REF.scale), wind_off: decode(REF.wind_off, REF.scale),
    other: decode(REF.other, REF.scale), mustrun: decode(REF.mustrun, REF.scale),
  };
  const gw = (v) => fmt(v / 1000, 0);
  weekChart = new Chart($("week-chart"), { height: 300, kind: "stack", yFormat: (v) => `${gw(v)} GW`, xTicks: dayTicks, tooltip: weekTooltip });
  priceChart = new Chart($("price-chart"), { height: 140, kind: "line", yMin: 0, yMax: 1200, yFormat: (v) => fmt(v, 0), xTicks: dayTicks,
    tooltip: (i) => `<div class="title">${localLabel(weekData.a + i)}</div><div class="row"><span>Cena</span><span class="num">${fmt(result.hourly.price[weekData.a + i], 0)} PLN/MWh</span></div>` });
  residualChart = new Chart($("residual-chart"), { height: 220, kind: "line", yMin: 0, yFormat: (v) => `${gw(v)}`, xTicks: hourTicks,
    tooltip: (i) => `<div class="row"><span>${fmt(i / (durationData.res.length - 1) * durationData.n, 0)} h</span><span class="num">${fmt(durationData.res[i] / 1000, 1)} GW</span></div>` });
  durationChart = new Chart($("duration-chart"), { height: 220, kind: "line", yMin: 0, yMax: 1200, yFormat: (v) => fmt(v, 0), xTicks: hourTicks,
    tooltip: (i) => `<div class="row"><span>${fmt(i / (durationData.price.length - 1) * durationData.n, 0)} h</span><span class="num">${fmt(durationData.price[i], 0)} PLN/MWh</span></div>` });
  buildControls();
  readHash();
  const today = META.scenarios.today.values;
  baseline = simulate(BASE_PROFILES, today, META.model).totals;
  renderValidation();
  renderSources();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", redraw);
  // a link pasted into the open page changes only the hash
  window.addEventListener("hashchange", () => {
    if (location.hash.slice(1) !== lastHash) { readHash(); update(); }
  });
  await update();
}

main().catch((err) => {
  $("tiles").innerHTML = `<p class="loading">Nie udało się wczytać danych: ${String(err.message).replace(/[<>&]/g, "")}</p>`;
  console.error(err);
});
