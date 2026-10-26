import copy

import numpy as np
import pytest

from mix_sandbox.config import load_scenarios, model_assumptions

SUPPLY = ("pv", "wind_on", "wind_off", "other", "nuclear", "lignite", "hard_coal", "gas", "import", "discharge", "ens")
SINKS = ("charge", "export")


@pytest.fixture
def assumptions():
    return copy.deepcopy(model_assumptions())


@pytest.fixture
def today():
    return dict(load_scenarios()["today"]["values"])


def synthetic_profiles(hours: int = 24 * 28, seed: int = 0) -> dict[str, np.ndarray]:
    """Four weeks of made-up but plausible hourly profiles: daily PV bell, noisy wind, daily demand cycle."""
    rng = np.random.default_rng(seed)
    t = np.arange(hours)
    hour = t % 24
    pv = np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None) * rng.uniform(0.3, 0.9, hours // 24).repeat(24)
    wind = np.clip(0.3 + 0.25 * np.sin(t / 40.0) + rng.normal(0, 0.08, hours), 0.0, 1.0)
    demand = 18000 + 3000 * np.sin((hour - 9) / 24 * 2 * np.pi) + rng.normal(0, 300, hours)
    return {
        "demand": demand,
        "pv": pv * 0.6,
        "wind_on": wind,
        "wind_off": np.clip(wind * 1.4, 0, 1),
        "other": np.ones(hours),
        "mustrun": np.ones(hours),
    }


@pytest.fixture
def profiles():
    return synthetic_profiles()
