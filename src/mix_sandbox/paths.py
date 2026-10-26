"""Folders of the project: raw downloads in data/ (not in git), published page data in docs/data/."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
PSE_CACHE = DATA_DIR / "pse"
ERA5_DIR = DATA_DIR / "era5"
INTERIM_DIR = DATA_DIR / "interim"
SITE_DATA = ROOT / "docs" / "data"
RESULTS_DIR = ROOT / "results"
