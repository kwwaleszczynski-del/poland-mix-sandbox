"""The browser model (docs/model.js, run in Node) and the Python reference give the same hours on the page data."""

import copy
import json
import shutil
import subprocess

import numpy as np
import pytest

from mix_sandbox import model, site_data
from mix_sandbox.config import load_scenarios, model_assumptions
from mix_sandbox.paths import ROOT

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js not installed")


def cases() -> list[dict]:
    a = model_assumptions()
    out = [{"name": key, "scenario": s["values"], "weather": "pse", "assumptions": a}
           for key, s in load_scenarios().items()]
    expensive = copy.deepcopy(a)
    expensive["co2_price_pln_t"] = 150 * 4.24
    expensive["tech"]["gas"]["fuel_pln_gj"] = 70 * 4.24 / 3.6
    kpeik = load_scenarios()["kpeik2030"]["values"]
    out += [
        {"name": "kpeik2030-2018", "scenario": kpeik, "weather": 2018, "assumptions": a},
        {"name": "kpeik2030-greedy-2017", "scenario": {**kpeik, "storage_rule": "greedy"}, "weather": 2017,
         "assumptions": a},
        {"name": "today-expensive-co2", "scenario": load_scenarios()["today"]["values"], "weather": "pse",
         "assumptions": expensive},
    ]
    return out


@pytest.fixture(scope="module")
def js_results():
    request = {"cases": [{k: c[k] for k in ("scenario", "weather", "assumptions")} for c in cases()]}
    proc = subprocess.run([NODE, str(ROOT / "tests" / "js" / "run_model.mjs")], input=json.dumps(request),
                          capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(proc.stdout)


@pytest.mark.parametrize("index", range(len(cases())), ids=[c["name"] for c in cases()])
def test_js_matches_python(js_results, index):
    case = cases()[index]
    weather = None if case["weather"] == "pse" else case["weather"]
    py = model.simulate(site_data.load_profiles(weather), case["scenario"], case["assumptions"])
    js = js_results[index]
    for key in model.SERIES:
        a = np.asarray(js["hourly"][key])
        b = py.hourly[key]
        assert np.allclose(a, b, rtol=1e-9, atol=1e-6), f"{key}: max diff {np.abs(a - b).max()}"
    for key, value in py.totals.items():
        assert js["totals"][key] == pytest.approx(value, rel=1e-9, abs=1e-9), key


def test_js_is_fast_enough(js_results):
    # the page recomputes on every slider move; one year must take well under a frame budget on a laptop
    assert min(r["ms"] for r in js_results) < 200
