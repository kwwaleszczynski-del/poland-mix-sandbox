"""poland-mix-sandbox: data preparation and reference model for a browser-based toy of the Polish power mix.

The browser runs the hourly dispatch in plain JavaScript (``docs/model.js``); this package downloads the public
data, builds the hourly profiles the page loads and holds a Python copy of the same dispatch, used for the 2025
validation and to test the JavaScript against.

Usage:
    python -m mix_sandbox fetch        # PSE reports and ERA5 time series into data/ (cached)
    python -m mix_sandbox build        # profiles and assumptions into docs/data/
    python -m mix_sandbox validate     # 2025 validation against PSE data
    python -m mix_sandbox simulate --scenario kpeik2030
"""

__version__ = "0.1.0"
