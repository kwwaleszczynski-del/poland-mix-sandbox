"""Checks of the committed page data, the configuration and the helpers that built them."""

import numpy as np
import pandas as pd
import pytest

from mix_sandbox import site_data, weather
from mix_sandbox.config import SCENARIO_KEYS, load_scenarios, model_assumptions
from mix_sandbox.paths import SITE_DATA


def test_reference_year_is_complete():
    ref = site_data.read_json_gz(SITE_DATA / "reference.json.gz")
    assert ref["hours"] == 8760
    assert ref["start_utc"] == "2024-12-31T23:00:00Z"
    for key in ("demand", "pv", "wind_on", "wind_off", "other", "mustrun"):
        assert len(ref[key]) == 8760, key
    p = site_data.load_profiles()
    assert p["demand"].sum() / 1e6 == pytest.approx(158.4, abs=0.1)
    for key in ("pv", "wind_on", "wind_off"):
        assert p[key].min() >= 0 and p[key].max() <= 1.0, key
    for key in ("other", "mustrun"):
        assert p[key].mean() == pytest.approx(1.0, abs=1e-3), key


@pytest.mark.parametrize("year", range(2010, 2026))
def test_weather_years(year):
    p = site_data.load_profiles(year)
    for key, lo, hi in (("pv", 0.08, 0.12), ("wind_on", 0.20, 0.32), ("wind_off", 0.38, 0.55)):
        assert len(p[key]) == 8760
        assert lo < p[key].mean() < hi, (key, p[key].mean())
        assert p[key].min() >= 0 and p[key].max() <= 1.0


def test_page_data_is_small():
    total = sum(f.stat().st_size for f in SITE_DATA.rglob("*") if f.is_file())
    assert total < 1.5e6
    assert (SITE_DATA / "reference.json.gz").stat().st_size < 150e3


def test_meta_matches_config():
    meta = site_data.load_meta()
    assert meta["model"] == model_assumptions()
    assert set(meta["scenarios"]) == set(load_scenarios())
    for s in meta["scenarios"].values():
        assert set(SCENARIO_KEYS) <= set(s["values"])
    assert set(meta["weather_years"]) == {str(y) for y in range(2010, 2026)}


def test_encode_round_trip():
    values = np.array([0.0, 0.12345, 0.99999, 1.0])
    assert np.allclose(site_data.decode(site_data.encode(values)), values, atol=0.5 / site_data.SCALE)


def test_year_hours_drop_leap_day_and_follow_local_time():
    for year in (2024, 2025):
        hours = weather.year_hours(year)
        assert len(hours) == 8760
        local = hours.tz_convert("Europe/Warsaw")
        assert local[0] == pd.Timestamp(f"{year}-01-01 00:00", tz="Europe/Warsaw")
        assert not ((local.month == 2) & (local.day == 29)).any()


def test_power_curves():
    for name in weather.CURVES:
        grid, curve = weather.smoothed_curve(name)
        assert len(grid) == len(curve)
        assert curve.min() >= 0 and curve.max() <= 1 + 1e-9
        below_rated = grid < weather.CURVES[name]["rated"]
        assert np.all(np.diff(curve[below_rated]) >= -1e-12)   # rising up to rated speed
        assert np.interp(2.0, grid, curve) < 0.05
        assert np.interp(15.0, grid, curve) > 0.95


def test_solar_geometry_noon_and_night():
    times = pd.DatetimeIndex(["2025-06-21 10:45", "2025-12-21 23:00"], tz="UTC")
    cos_zen, cos_inc = weather.solar_geometry(times, 52.2, 21.0)
    # Warsaw, solar noon in June: sun ~61 deg high; midnight: below the horizon
    assert np.degrees(np.arcsin(cos_zen[0])) == pytest.approx(61.2, abs=1.0)
    assert cos_zen[1] < 0
    assert cos_inc[0] > cos_zen[0] * 0.9
