"""Social preview image of the page (docs/card.png, 1200 x 630 px, used as og:image): the hardest week of the
KPEiK 2030 preset in the calm weather year 2018, hour by hour, with the yearly headline numbers.

Usage:
    python -m mix_sandbox card
"""

from __future__ import annotations

import logging

import numpy as np

from . import model, site_data
from .config import load_scenarios, model_assumptions
from .paths import ROOT

log = logging.getLogger(__name__)

# light-mode colours of the page, same stack order (bottom -> top)
LAYERS = [
    ("nuclear", "Atom", "#6250d6"),
    ("coal", "Węgiel", "#e34948"),
    ("other", "Inne", "#008300"),
    ("wind", "Wiatr", "#2a78d6"),
    ("gas", "Gaz", "#eb6834"),
    ("discharge", "Magazyny", "#1baf7a"),
    ("pv", "PV", "#eda100"),
    ("import", "Import", "#e87ba4"),
    ("ens", "Niedobór", "#d03b3b"),
]


def run(scenario: str = "kpeik2030", weather_year: int = 2018) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    values = load_scenarios()[scenario]["values"]
    r = model.simulate(site_data.load_profiles(weather_year), values, model_assumptions())
    h, t = r.hourly, r.totals
    scores = [(h["ens"][w * 168:(w + 1) * 168] * 100 + h["residual"][w * 168:(w + 1) * 168]).sum() for w in range(52)]
    w = int(np.argmax(scores))
    sl = slice(w * 168, (w + 1) * 168)
    series = {
        "coal": h["lignite"][sl] + h["hard_coal"][sl],
        "wind": h["wind_on"][sl] + h["wind_off"][sl],
        **{k: h[k][sl] for k in ("nuclear", "other", "gas", "discharge", "pv", "import", "ens")},
    }
    # residual = demand - available wind and PV (used + curtailed)
    demand = h["residual"][sl] + h["pv"][sl] + h["wind_on"][sl] + h["wind_off"][sl] + h["curtail"][sl]

    fig = plt.figure(figsize=(12, 6.3), dpi=100, facecolor="#fcfcfb")
    fig.text(0.04, 0.88, "Piaskownica miksu Polski", fontsize=30, weight="bold", color="#0b0b0b")
    fig.text(0.04, 0.81, "Zbuduj polski system 2030 suwakami: 8760 godzin na danych PSE i ERA5, w przeglądarce",
             fontsize=14, color="#52514e")
    ax = fig.add_axes((0.06, 0.17, 0.6, 0.55))
    x = np.arange(168)
    base = np.zeros(168)
    for key, label, color in LAYERS:
        top = base + series[key] / 1000
        if series[key].max() > 1:
            ax.fill_between(x, base, top, color=color, linewidth=0, label=label,
                            hatch="///" if key == "ens" else None, alpha=0.95 if key != "ens" else 0.6)
        base = top
    ax.plot(x, demand / 1000, color="#0b0b0b", linewidth=2, label="Zapotrzebowanie")
    ax.set_xlim(0, 167)
    ax.set_ylim(0, None)
    ax.set_xticks(range(0, 168, 24), [f"dzień {d + 1}" for d in range(7)], fontsize=10, color="#6f6d68")
    ax.tick_params(axis="y", labelsize=10, colors="#6f6d68")
    ax.set_ylabel("GW", color="#6f6d68")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#c3c2b7")
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.grid(axis="y", color="#e1e0d9", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_facecolor("#fcfcfb")
    ax.set_title(f"2030 wg KPEiK, pogoda {weather_year}: najtrudniejszy tydzień", loc="left", fontsize=13,
                 color="#0b0b0b")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=9, frameon=False, fontsize=9,
              handlelength=1.2, columnspacing=1.0)
    stats = [
        ("Emisje CO₂", f"{t['co2_mt']:.0f} Mt".replace(".", ",")),
        ("Wiatr i PV", f"{t['vre_share'] * 100:.0f}%"),
        ("Obcięcia OZE", f"{t['curtail_twh']:.1f} TWh".replace(".", ",")),
        ("Niedobór", f"{t['ens_twh'] * 1000:.0f} GWh w {t['ens_hours']} h"),
    ]
    for i, (label, value) in enumerate(stats):
        y = 0.62 - i * 0.14
        fig.text(0.72, y + 0.06, label, fontsize=13, color="#52514e")
        fig.text(0.72, y, value, fontsize=24, weight="bold", color="#0b0b0b")
    fig.text(0.04, 0.03, "kwwaleszczynski-del.github.io/poland-mix-sandbox", fontsize=11, color="#2a78d6")
    out = ROOT / "docs" / "card.png"
    fig.savefig(out, dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    log.info("wrote %s (week %d)", out, w + 1)
