# poland-mix-sandbox

[![tests](https://github.com/kwwaleszczynski-del/poland-mix-sandbox/actions/workflows/ci.yml/badge.svg)](https://github.com/kwwaleszczynski-del/poland-mix-sandbox/actions/workflows/ci.yml)

**Build the Polish power system of 2030 with sliders and see what happens, hour by hour.**
Set the capacity of PV, onshore and offshore wind, storage (GW and GWh), nuclear, gas, lignite, hard coal and
interconnectors; the page dispatches all 8760 hours of a reference year built from PSE data and shows curtailment,
energy not served, CO2, residual load and an approximate price. Everything runs in the browser (GitHub Pages, no
server), every scenario is a shareable link.

Live page: <https://kwwaleszczynski-del.github.io/poland-mix-sandbox/> (Polish interface).

> This is an educational toy, not a power-system model. It has no grid, no unit commitment, no reserves, no
> neighbouring markets and a fixed demand shape. Use it to build intuition about why curtailment, storage and firm
> capacity matter, not to plan anything.

## What you can do

- start from a preset: **today** (fleet at the end of 2025), **2030 according to KPEiK** (the national energy and
  climate plan adopted in June 2026), **2030 without coal** and **2040 according to KPEiK**;
- move any slider: the year is recomputed in 30-100 ms, tiles, charts and the yearly balance follow;
- switch the weather year: 2025 as measured by PSE, or any year 2010-2025 from ERA5 (2017 was the windiest,
  2018 the calmest);
- choose the storage rule: "charge the surplus, discharge the deficit" or a better peak-shaving rule;
- change CO2, gas and coal prices and watch the merit order flip;
- look at the hardest week (largest shortfall) or the week with the largest surplus, hour by hour;
- copy the link: all parameters live in the URL hash, e.g.
  `#s=kpeik2030&pv=45&sgw=12&sgwh=48&wy=2018`.

## Results of the presets

Reference year 2025 (PSE weather), demand in the PSE definition (158.4 TWh in 2025); `python -m mix_sandbox simulate
--presets` writes this table to [results/presets.csv](results/presets.csv):

| preset | wind + PV share | CO2 | curtailed wind + PV | energy not served | mean price |
|---|---:|---:|---:|---:|---:|
| today (end of 2025 fleet) | 27.2% | 88.1 Mt (556 g/kWh) | 2.0 TWh | 0 | 339 PLN/MWh |
| 2030 KPEiK | 44.6% | 64.3 Mt (368 g/kWh) | 6.1 TWh | 0 | 312 PLN/MWh |
| 2030 without coal | 47.4% | 24.0 Mt (138 g/kWh) | 1.2 TWh | 8.7 TWh in 2705 h, up to 11.5 GW | 1799 PLN/MWh |
| 2040 KPEiK | 56.6% | 34.3 Mt (143 g/kWh) | 27.8 TWh | 0.10 TWh in 79 h | 266 PLN/MWh |

Over the 16 ERA5 weather years (2010-2025, same demand), from
[results/presets_weather_years.csv](results/presets_weather_years.csv):

| preset | CO2 [Mt] | curtailed [TWh] | years with energy not served | worst year |
|---|---:|---:|---:|---|
| today | 87.2-89.8 | 2.1-4.1 | 0 of 16 | - |
| 2030 KPEiK | 62.6-66.0 | 6.4-11.8 | 6 of 16 | 2022: 11.6 GWh in 20 h, up to 1.4 GW |
| 2030 without coal | 23.4-24.6 | 1.4-3.9 | 16 of 16 | 2018: 9.8 TWh in 2973 h, up to 13.2 GW |
| 2040 KPEiK | 32.9-35.3 | 27.8-43.2 | 16 of 16 | 2022: 0.61 TWh in 189 h, up to 8.0 GW |

What the toy suggests, with its assumptions: the 2030 plan cuts emissions by about a quarter but leaves a thin
margin in calm, cold weeks (import is capped at 70% of the 6.4 GW limit and thermal availability at 85-90%); taking
coal out by 2030 without building firm capacity in its place leaves 6-10 TWh of demand unserved; by 2040 the
inflexible part of the system (nuclear at 50% minimum load, must-run, other sources) plus 90 GW of wind and PV makes
curtailment the dominant issue (17-24% of the wind and PV available).

## Calibration check: how close does it get to 2025?

The model is run on the measured hourly inputs of 2025 (demand, wind and PV available = generation + PSE
non-market redispatch, "other" small sources, must-run envelope) with the large-unit fleet of 2025; everything else
is modelled and compared with PSE data (`python -m mix_sandbox validate`, file
[results/validation_2025.md](results/validation_2025.md)). This is an in-sample check, not a validation: five
parameters were fitted to the same year (below), so it shows how far a tuned toy can follow 2025, not how well it
would predict another year. An out-of-sample test would need the unit data and fleet of another year (for example
2026), which the toy does not include.

| quantity | PSE 2025 | model | comment |
|---|---:|---:|---|
| lignite, units >= 100 MW | 30.6 TWh | 29.4 TWh | lignite fuel cost calibrated to keep it baseload |
| hard coal, units >= 100 MW | 45.1 TWh | 48.9 TWh | takes over what gas does not get |
| gas, units >= 100 MW | 17.1 TWh | 12.4 TWh | gas CHPs run for heat; the model dispatches them on cost only |
| large thermal, total | 92.8 TWh | 90.7 TWh | hourly R2 0.80, correlation 0.90 |
| import (hourly balance > 0) | 5.5 TWh | 4.6 TWh | flat import price, calibrated |
| export (hourly balance < 0) | 4.6 TWh | 1.9 TWh | the model exports only surplus energy; Poland also exported when prices abroad were higher |
| net import | 0.9 TWh | 2.7 TWh | consequence of the line above |
| storage charging | 1.5 TWh | 1.6 TWh | |
| storage discharging | 0.9 TWh (PSH >= 100 MW; 1.1-1.2 TWh all PSH) | 1.3 TWh | one round-trip efficiency (80%) for all storage |
| curtailment of wind and PV | 1.38 TWh in 2400 h | 1.29 TWh in 655 h | PSE curtails little in many hours, the model a lot in fewer hours |
| mean price | 442 PLN/MWh (RCE) | 351 PLN/MWh | marginal cost only: no mark-ups, start-up costs or scarcity rents |
| hours with price <= 0 | 356 | 655 | every curtailment hour is priced at 0 |
| price, hourly | | correlation 0.67, Spearman 0.83, MAE 124 PLN/MWh | |
| CO2 | KOBiZE: 88.7 Mt for electricity in 2024 (2025 not yet published) | 89.0 Mt | order-of-magnitude check only |

Five behavioural parameters were calibrated on 2025 (grid search, `validate --calibrate`): must-run level (1.2 x
the monthly 2nd percentile of large-unit output, 7.9 GW on average), import price (410 PLN/MWh) and availability
(70% of the limit), export availability in surplus hours (40%) and the price in surplus hours without curtailment
(280 PLN/MWh, the mean RCE in those hours). They are fitted to one year, so treat them as part of the toy.

## Model

Each hour $`t`$, with demand $`D_t`$, available wind and PV $`V_t`$, "other" sources $`O_t`$, must-run of large
thermal units $`M_t`$ and nuclear between $`\underline{N}`$ and $`\overline{N}`$:

```math
R_t = D_t - V_t - O_t - M_t - \underline{N}
```

- $`R_t \le 0`$ (surplus): storage charges $`\min(-R_t, P, (E - S_t)/\eta)`$, then exports up to
  $`a_x X`$, the rest of wind and PV is curtailed (and, if even that is not enough, the inflexible sources);
- $`R_t > 0`$ (deficit): nuclear rises to $`\overline{N}`$, storage discharges, then blocks are dispatched by
  short-run marginal cost; what is left is energy not served.

Storage keeps its state of charge $`S_t`$ with $`\eta = \sqrt{\eta_{rt}}`$ on both sides:

```math
S_{t} = S_{t-1} + \eta \, c_t - \frac{d_t}{\eta}, \qquad 0 \le S_t \le E, \quad 0 \le c_t, d_t \le P
```

Rule "peak" discharges only above a level $`L_t`$ chosen so that the energy in store covers the highest net load
until the next surplus hour, at most 24 hours ahead ($`H`$ = hours of that window, $`R^+_k`$ = net load left after
nuclear):

```math
\sum_{k \in H} \min\left(P, \max(0, R^+_k - L_t)\right) = \eta \, S_{t-1}, \qquad d_t = \min\left(P, \max(0, R^+_t - L_t)\right)
```

Rule "greedy" discharges $`\min(P, R^+_t, \eta S_{t-1})`$, as much as it can.

Each thermal technology is split into four equal blocks with efficiency from best to worst; block $`k`$ with
efficiency $`\eta_k`$, fuel price $`p_f`$ (PLN/GJ), emission factor $`e_f`$ (t CO2/GJ), CO2 price $`p_{CO2}`$ and
variable cost $`v`$ has the marginal cost and emission rate

```math
c_k = \frac{3.6 \, p_f}{\eta_k} + p_{CO2} \, \frac{3.6 \, e_f}{\eta_k} + v \quad \text{[PLN/MWh]}, \qquad
\epsilon_k = \frac{3.6 \, e_f}{\eta_k} \quad \text{[t/MWh]}
```

Imports are one more block with a flat price and $`a_m`$ times the import limit. The must-run $`M_t`$ is shared by
the thermal blocks in proportion to their capacity. The price of an hour is $`c_k`$ of the last block used; when
storage alone covers the deficit, the cost of the block it displaces; 0 PLN/MWh when wind and PV are curtailed;
280 PLN/MWh in other surplus hours; 5000 PLN/MWh when demand is not served.

### Why plain JavaScript and not Pyodide

The model is a loop over 8760 hours with a dozen blocks: about 30-100 ms in plain JavaScript, fast enough to
recompute on every slider move, on a phone too, with a 9 kB script and no dependencies. Pyodide would add a 10+ MB
download and seconds of start-up for no gain. To keep one source of truth, `src/mix_sandbox/model.py` is a line by
line Python twin of `docs/model.js`; the tests run both on the page data and require identical hours (they agree
to the last bit, including the left-to-right float sums).

## Data

All inputs are public. Downloads are cached in `data/` (not in git); the page data in `docs/data/` (0.8 MB: 17
gzip-compressed JSON files and `meta.json`, 97 kB loaded at start) is committed.

| input | source | use |
|---|---|---|
| demand, wind, PV, generation, storage charging, cross-border balance, 2024-06-14..2026-09-30 | PSE reports API `his-wlk-cal` via [pse-opendata](https://pypi.org/project/pse-opendata/) (downloaded with commit 8b01ec8, now `pse-opendata>=0.2,<0.3`) | reference year, calibration check |
| non-market redispatch of wind and PV | PSE `poze-redoze` | added back to get the available wind and PV; check of curtailment |
| generation of units >= 100 MW, 2025 | PSE `gen-jw`, plants classified by fuel in [config/plants.csv](config/plants.csv) | large-unit fleet, calibration check |
| market price RCE, 2025 | PSE `rce-pln` | check of the price |
| wind speed at 100 m, irradiance, temperature, 2010-01..2026-09 | ERA5 through the Open-Meteo archive API, 15 onshore + 4 Baltic + 14 PV points ([config/era5_points.toml](config/era5_points.toml)) | offshore wind, weather years |
| installed capacity, KPEiK plan, NTC, fuel and CO2 prices, emission factors | listed with dates in [config/assumptions.toml](config/assumptions.toml) and [config/scenarios.toml](config/scenarios.toml) | scaling, presets, costs |

**Reference year 2025.** Wind and PV available = measured generation + PSE redispatch (1.38 TWh), divided by the
installed capacity interpolated day by day between dated values (PV 21.3 GW end-2024, 24.5 GW 1.9.2025, 25.9 GW
end-2025; onshore wind 10.6, 11.15 and 11.2 GW) into capacity factors: PV 9.8%, wind 23.3% in 2025. "Other" is all
generation outside wind, PV and the units >= 100 MW (small CHP, industrial plants, hydro, biomass): 24.2 TWh,
2.76 GW on average, with its 2025 shape (winter 3.5 GW, summer 2.1 GW); its emission factor (0.45 t/MWh) is an
estimate from the 2025 mix by fuel (Forum Energii) minus the large units.

**Weather years.** Onshore wind: a smoothed generic power curve on ERA5 100 m wind at 15 points; PV: global and
diffuse irradiance on a 30-degree south plane and on a horizontal plane with a temperature loss at 14 points. The
point weights are fitted by non-negative least squares to the 2025 PSE profiles (no capacity map needed) and the
result is rescaled to the measured 2025 mean:

| fit | R2 2025 (fit) | R2 Jun-Dec 2024 | R2 Jan-Sep 2026 |
|---|---:|---:|---:|
| onshore wind | 0.885 | 0.892 | 0.800 (correlation 0.935; the fleet grew) |
| PV | 0.968 | 0.964 | 0.941 |

Offshore wind: the mean of four points in the Polish Baltic areas through the IEA 15 MW reference curve (hub
150 m, 1/10 power law) minus 18% for wakes, electrical losses and availability: capacity factor 42-50% depending on
the year. Capacity factors by weather year: onshore 22.6% (2018) to 27.9% (2017), offshore 41.9-49.6%, PV
8.9-10.0%. 2025 was a calm year (onshore 23.2%). Demand, "other" and must-run always come from 2025.

**Presets.** The thermal sliders are the large units of `gen-jw` (2025: 7.0 GW lignite, 15.7 GW hard coal, 4.0 GW
gas, i.e. 84%, 68% and 63% of the capacity in the PSE annual report); KPEiK capacities are converted with the same
shares. Future demand grows like KPEiK gross generation (196.5 TWh in 2030, 270.5 TWh in 2040, against 178.1 TWh
for 2025 in the same tables). KPEiK gives batteries in MW only; 3 hours of storage are assumed. Every conversion is
written next to the numbers in [config/scenarios.toml](config/scenarios.toml).

Main cost assumptions (2025 averages): EUA 74 EUR/t (ESMA), TTF 36 EUR/MWh + 4 EUR/MWh transport, steam coal
18 PLN/GJ delivered (PSCMI 1 ~16 PLN/GJ), EUR/PLN 4.24 (NBP); KOBiZE emission factors (hard coal 93.89, lignite
110.64, gas 56.18 kg CO2/GJ); efficiencies 33-41% lignite, 32-45% hard coal, 48-60% gas; availability 85-90%.

## Limitations

- one bus: no grid constraints, no redispatch, no reserves or balancing, no ramping or start-up costs;
- neighbours are a flat-price import block and a capped sink for surplus; there are no prices abroad and no
  transit flows;
- demand keeps its 2025 shape: no heat pumps, electric cars, electrolysers or demand response, and no link between
  weather and demand in other weather years;
- storage is one pool with one efficiency, run by a rule with at most 24 hours of foresight, never charged from
  the grid;
- the price is a marginal-cost proxy; it does not reproduce negative prices, mark-ups or the level of RCE;
- the calibrated parameters are fitted to a single year and the future presets reuse them;
- capacity numbers of 2025-2026 partly come from press articles citing PSE, marked as such in the config.

## Run it

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[data,dev]"     # Linux/macOS: .venv/bin/python
python -m mix_sandbox fetch          # PSE and ERA5 into data/ (cached; ERA5 ~2800 Open-Meteo request units)
python -m mix_sandbox validate       # results/validation_2025.* (calibration check)
python -m mix_sandbox build          # docs/data/
python -m mix_sandbox card           # docs/card.png, the link preview (og:image)
python -m mix_sandbox simulate --scenario kpeik2030 --weather-year 2018 --set storage_gwh=60
python -m mix_sandbox simulate --presets   # results/presets.csv, results/presets_weather_years.csv
python -m http.server 8000 --directory docs
pytest -q                            # Python model, page data, JavaScript parity (needs Node.js)
node --test "tests/js/*.test.mjs"    # JavaScript model
```

The tests and the page need only the committed `docs/data`; `requests`, `scipy`, `matplotlib` and `pse-opendata`
(extra `data`) are only needed to download and rebuild it.

## Repository

| path | content |
|---|---|
| `docs/` | the page: `index.html`, `app.js` (controls, URL state), `model.js` (dispatch), `charts.js`, `data/` |
| `src/mix_sandbox/` | `fetch.py`, `pse_data.py`, `era5.py`, `weather.py`, `profiles.py`, `build.py`, `model.py`, `validate.py`, `simulate.py`, `card.py`, `cli.py` |
| `config/` | assumptions with sources, presets, ERA5 points, plant fuels |
| `tests/` | pytest (model properties, page data, JS parity) and `tests/js` (node:test) |
| `results/` | calibration check 2025, preset results on every weather year |

## Data sources and terms

- **PSE S.A.** reports API and www.pse.pl: information obtained from www.pse.pl (reports `his-wlk-cal`,
  `poze-redoze`, `gen-jw`, `rce-pln`), state as of 26 October 2026. The information has been processed: quarter
  hours averaged to hours, wind and PV divided by installed capacity, profiles normalised, units summed by fuel.
  PSE publishes its re-use conditions in its BIP ("Ponowne wykorzystywanie informacji sektora publicznego"). This
  project is not affiliated with PSE.
- **ERA5** (Copernicus Climate Change Service) via [Open-Meteo](https://open-meteo.com), CC BY 4.0: contains
  modified Copernicus Climate Change Service information 2010-2026.
- Numbers quoted from the PSE annual report 2025, KPEiK (Council of Ministers, 8 June 2026), Forum Energii
  "Rocznik 2026", KOBiZE, ESMA, European Commission, NBP and gramwzielone.pl are cited with links in
  `config/assumptions.toml` (read on 26 October 2026). Plans and regulations change; check the current versions.

## License

Code: MIT, see [LICENSE](LICENSE). Data: see the section above.
