import pandas as pd

from mix_sandbox import simulate
from mix_sandbox.paths import RESULTS_DIR


def test_committed_preset_tables_match_the_model(tmp_path, monkeypatch):
    """results/presets*.csv (the README tables) are what `simulate --presets` computes from the page data."""
    monkeypatch.setattr(simulate, "RESULTS_DIR", tmp_path)
    ref, era5 = simulate.presets(weather_years=[2018])
    pd.testing.assert_frame_equal(ref.reset_index(drop=True), pd.read_csv(RESULTS_DIR / "presets.csv"),
                                  check_dtype=False)
    committed = pd.read_csv(RESULTS_DIR / "presets_weather_years.csv")
    pd.testing.assert_frame_equal(era5.reset_index(drop=True),
                                  committed[committed["weather"] == "ERA5 2018"].reset_index(drop=True),
                                  check_dtype=False)
