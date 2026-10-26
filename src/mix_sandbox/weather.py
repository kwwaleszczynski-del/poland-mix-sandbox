"""Wind and PV output from ERA5 series: power curves, a simple PV model and a non-negative fit to PSE profiles.

Times: PSE hours are labelled by their start (UTC). Open-Meteo labels radiation by the END of the hour it
averages and gives wind as instantaneous values, so the PSE hour starting at S uses radiation labelled S + 1 h
(sun position at S + 30 min) and the mean power of the wind at S and S + 1 h.

Usage:
    cf = wind_cf(speed_100m, curve="onshore")
    feats = pv_features(frame, lat, lon)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# normalised power curves: P/P_rated = (v^3 - vin^3) / (vr^3 - vin^3) between cut-in and rated speed, smoothed with
# a Gaussian of sigma m/s for the spread of wind speeds inside a 0.25 deg cell and a fleet of turbines
CURVES = {
    # generic onshore fleet turbine, rated ~12 m/s at ERA5 100 m (older and newer turbines mixed)
    "onshore": {"cut_in": 3.0, "rated": 12.0, "cut_out": 25.0, "sigma": 1.2, "shear": 1.0},
    # IEA 15 MW reference turbine (rated 10.59 m/s, 150 m hub); 100 m wind raised with a 1/10 power law
    "offshore": {"cut_in": 3.0, "rated": 10.59, "cut_out": 25.0, "sigma": 0.8, "shear": 1.5 ** 0.1},
}


def power_curve(v: np.ndarray, cut_in: float, rated: float, cut_out: float) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    p = (v ** 3 - cut_in ** 3) / (rated ** 3 - cut_in ** 3)
    p = np.where(v < cut_in, 0.0, np.where(v >= rated, 1.0, p))
    return np.where(v >= cut_out, 0.0, p)


def smoothed_curve(name: str) -> tuple[np.ndarray, np.ndarray]:
    c = CURVES[name]
    grid = np.arange(0.0, 40.0, 0.05)
    raw = power_curve(grid, c["cut_in"], c["rated"], c["cut_out"])
    half = int(round(4 * c["sigma"] / 0.05))
    offsets = np.arange(-half, half + 1) * 0.05
    kernel = np.exp(-0.5 * (offsets / c["sigma"]) ** 2)
    kernel /= kernel.sum()
    smooth = np.convolve(np.pad(raw, (half, half), mode="edge"), kernel, mode="valid")
    return grid, smooth


def wind_cf(speed: pd.Series, curve: str) -> pd.Series:
    """Capacity factor per PSE hour (start label) from instantaneous ERA5 100 m wind speed (m/s)."""
    grid, smooth = smoothed_curve(curve)
    p = pd.Series(np.interp(speed.to_numpy() * CURVES[curve]["shear"], grid, smooth), index=speed.index)
    return 0.5 * (p + p.shift(-1))


def solar_geometry(times: pd.DatetimeIndex, lat: float, lon: float) -> tuple[np.ndarray, np.ndarray]:
    """cos(zenith) and cos(incidence) on a south-facing plane tilted 30 deg (NOAA approximations)."""
    doy = times.day_of_year.to_numpy()
    hour = times.hour.to_numpy() + times.minute.to_numpy() / 60.0
    g = 2 * np.pi / 365 * (doy - 1 + (hour - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g) - 0.014615 * np.cos(2 * g)
                       - 0.040849 * np.sin(2 * g))
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
            + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    ha = np.radians((hour * 60 + eqtime + 4 * lon) / 4 - 180)
    phi = np.radians(lat)
    beta = np.radians(30.0)
    cos_zen = np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(ha)
    cos_inc = np.sin(decl) * np.sin(phi - beta) + np.cos(decl) * np.cos(phi - beta) * np.cos(ha)
    return cos_zen, cos_inc


def pv_features(frame: pd.DataFrame, lat: float, lon: float) -> pd.DataFrame:
    """Relative PV output (kW per kWp, before losses) per PSE hour of a 30 deg south plane and of a horizontal
    plane, from ERA5 global and diffuse irradiance (W/m2) and 2 m air temperature (deg C)."""
    shifted = frame.shift(-1)                     # value of the hour that starts at the index
    times = frame.index + pd.Timedelta(minutes=30)
    cos_zen, cos_inc = solar_geometry(times, lat, lon)
    ghi = shifted["shortwave_radiation"].to_numpy()
    dhi = np.minimum(shifted["diffuse_radiation"].to_numpy(), ghi)
    temp = shifted["temperature_2m"].to_numpy()
    dni = np.where(cos_zen > 0.087, (ghi - dhi) / np.maximum(cos_zen, 0.087), 0.0)
    beta = np.radians(30.0)
    poa = dni * np.maximum(cos_inc, 0.0) + dhi * (1 + np.cos(beta)) / 2 + ghi * 0.2 * (1 - np.cos(beta)) / 2

    def output(irr: np.ndarray) -> np.ndarray:
        cell = temp + 0.03 * irr
        return irr / 1000.0 * (1 - 0.004 * (cell - 25.0))

    return pd.DataFrame({"tilted": output(poa), "horizontal": output(ghi)}, index=frame.index).fillna(0.0)


def year_hours(year: int) -> pd.DatetimeIndex:
    """Hour starts (UTC) of a Polish local calendar year without 29 February: always 8760 hours."""
    local = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq="h", tz="Europe/Warsaw", inclusive="left")
    utc = pd.date_range(local[0].tz_convert("UTC"), local[-1].tz_convert("UTC"), freq="h")
    keep = ~((utc.tz_convert("Europe/Warsaw").month == 2) & (utc.tz_convert("Europe/Warsaw").day == 29))
    return utc[keep]
