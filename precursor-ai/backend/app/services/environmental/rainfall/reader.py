"""Read ONE daily IMERG-like HDF5/netCDF4 file and reduce it to an AOI statistic.

Nothing about the real GPM_3IMERGDF V07 layout is hard-coded as verified: variables and coordinates are DISCOVERED by
name (see docs/scientific/RAINFALL_METHODOLOGY.md). Only the AOI index window is read, not the global grid.
Units are checked: a daily file must be mm/day; mm/hr is refused (never silently treated as mm/day).
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401  (must precede geo libs)
from app.core.synthetic_guard import refuse_if_synthetic

import re
from dataclasses import dataclass, field
from datetime import date as Date
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry

from app.services.environmental.types import EnvError, NotAvailable
from app.services.insar.hdf import decode, index_datasets

SYNTHETIC_ATTR = "precursor_synthetic_fixture"
PRECIP_NAMES = ("precipitation", "precipitationCal")  # V07 renamed precipitationCal -> precipitation (per NASA FAQ)
LAT_NAMES = ("lat", "latitude")
LON_NAMES = ("lon", "longitude")
_DAILY_UNITS = {"mm/day", "mm/d", "mm day-1", "mm day^-1", "mm d-1", "mm per day", "mm/day."}
_RATE_UNITS = {"mm/hr", "mm/h", "mm hr-1", "mm h-1", "mm hr^-1", "mm/hour", "mm per hour"}


@dataclass
class AoiStat:
    mean_mm_day: float | None  # None when no valid cell (missing, NEVER zero)
    min_mm_day: float | None
    max_mm_day: float | None
    n_cells: int  # cells used (centre inside AOI, or the 1 centroid cell)
    n_valid: int
    method: str  # "cell_centres_in_aoi" | "centroid_cell"
    warnings: list[str] = field(default_factory=list)


@dataclass
class DailyAoi:
    date: Date
    stat: AoiStat
    units: str | None
    units_verified: bool
    fill_value: float | None
    variable_path: str
    native_resolution_deg: dict[str, float]
    synthetic: bool
    dataset_version: str | None
    discovered: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def _attr(obj: Any, name: str) -> Any:
    return decode(obj.attrs[name]) if name in obj.attrs else None


def _first_scalar(v: Any) -> float | None:
    if v is None:
        return None
    a = np.asarray(v).ravel()
    return float(a[0]) if a.size else None


def normalize_units(u: str | None) -> str:
    """'daily' | 'rate' | 'unknown' | 'other'."""
    if u is None or not str(u).strip():
        return "unknown"
    s = re.sub(r"\s+", " ", str(u).strip().lower())
    if s in _DAILY_UNITS:
        return "daily"
    if s in _RATE_UNITS:
        return "rate"
    return "other"


def _find_one(idx: dict[str, list[str]], names: tuple[str, ...], what: str) -> str:
    for n in names:
        paths = idx.get(n, [])
        if len(paths) == 1:
            return paths[0]
        if len(paths) > 1:
            raise EnvError(f"ambiguous {what}: {n!r} found at {paths}")
    near = sorted(p for k, v in idx.items() for p in v if "precip" in k.lower() or "lat" in k.lower() or "lon" in k.lower())
    raise EnvError(f"{what} not found (looked for {list(names)}); related datasets present: {near}")


def _axes(ds: h5py.Dataset, nlat: int, nlon: int) -> tuple[int, int]:
    """(lat_axis, lon_axis) from dimension scales when present, else from sizes (square grids are refused)."""
    found: dict[str, int] = {}
    for i in range(ds.ndim):
        try:
            keys = [k.rsplit("/", 1)[-1].lower() for k in ds.dims[i].keys()]
        except (RuntimeError, ValueError, KeyError):
            keys = []
        for k in keys:
            if k in LAT_NAMES:
                found["lat"] = i
            if k in LON_NAMES:
                found["lon"] = i
    if len(found) == 2:
        return found["lat"], found["lon"]
    lat_ax = [i for i, n in enumerate(ds.shape) if n == nlat]
    lon_ax = [i for i, n in enumerate(ds.shape) if n == nlon]
    if nlat == nlon:
        raise EnvError("lat and lon have equal length and the dataset has no dimension scales: axis order is ambiguous")
    if len(lat_ax) != 1 or len(lon_ax) != 1:
        raise EnvError(f"cannot match dataset shape {ds.shape} to lat({nlat})/lon({nlon})")
    return lat_ax[0], lon_ax[0]


def _window(coord: np.ndarray, lo: float, hi: float, res: float) -> slice | None:
    """Index slice of coordinate centres touching [lo, hi] (one-cell margin); None if disjoint from the grid."""
    if hi < coord.min() - res / 2 or lo > coord.max() + res / 2:
        return None
    ix = np.where((coord >= lo - res) & (coord <= hi + res))[0]
    return slice(int(ix.min()), int(ix.max()) + 1) if ix.size else None


def _file_date(f: h5py.File, idx: dict[str, list[str]]) -> Date | None:
    paths = idx.get("time", [])
    if len(paths) != 1:
        return None
    ds = f[paths[0]]
    m = re.match(r"^(\w+) since (.+)$", str(_attr(ds, "units") or ""))
    if ds.size != 1 or not m:
        return None
    unit = {"days": "D", "day": "D", "seconds": "s", "hours": "h", "minutes": "min"}.get(m.group(1).lower())
    if unit is None:
        return None
    try:
        return (pd.Timestamp(m.group(2).replace("Z", "")) + pd.to_timedelta(float(ds[()].ravel()[0]), unit=unit)).date()
    except (ValueError, TypeError):
        return None


def aoi_statistic(field2d: np.ndarray, lat: np.ndarray, lon: np.ndarray, aoi: BaseGeometry) -> AoiStat:
    """AOI value from a (lat, lon) field with NaN for invalid.

    Cells whose CENTRE lies inside the AOI are averaged. If none do, the single cell containing the AOI centroid is used
    with an explicit warning. This never increases the information resolution: it is a ~0.1 degree cell value.
    """
    lon2, lat2 = np.meshgrid(lon, lat)
    inside = shapely.contains_xy(aoi, lon2, lat2)
    warns: list[str] = []
    method = "cell_centres_in_aoi"
    if not inside.any():
        c = aoi.centroid
        res_lat = float(np.median(np.abs(np.diff(lat)))) if lat.size > 1 else 0.1
        res_lon = float(np.median(np.abs(np.diff(lon)))) if lon.size > 1 else 0.1
        i, j = int(np.argmin(np.abs(lat - c.y))), int(np.argmin(np.abs(lon - c.x)))
        if abs(lat[i] - c.y) > res_lat / 2 + 1e-9 or abs(lon[j] - c.x) > res_lon / 2 + 1e-9:
            raise NotAvailable("AOI centroid lies outside the rainfall grid window")
        inside = np.zeros_like(inside)
        inside[i, j] = True
        method = "centroid_cell"
        warns.append("AOI is smaller than an IMERG cell: the value is the ~10 km cell value at the AOI centroid, "
                     "not local rainfall.")
    vals = field2d[inside]
    ok = vals[np.isfinite(vals)]
    if ok.size == 0:
        warns.append("all cells for this AOI are missing/fill: the day is treated as MISSING (not zero)")
        return AoiStat(None, None, None, int(vals.size), 0, method, warns)
    return AoiStat(float(ok.mean()), float(ok.min()), float(ok.max()), int(vals.size), int(ok.size), method, warns)


def read_daily_aoi(path: str | Path, aoi: BaseGeometry, date: Date | None = None,
                   expected_units: str = "daily") -> DailyAoi:
    """Open one daily file, read only the AOI window, return the AOI statistic and metadata.

    Raises EnvError (unreadable structure, ambiguous/missing variables, wrong units, date mismatch) or NotAvailable
    (AOI outside the grid)."""
    path = Path(path)
    if aoi.is_empty or not aoi.is_valid:
        raise EnvError("AOI geometry is empty or invalid")
    try:
        f = h5py.File(path, "r")
    except OSError as e:
        raise EnvError(f"cannot open {path.name} as HDF5/netCDF4: {e}") from e
    with f:
        idx = index_datasets(f)
        var = _find_one(idx, PRECIP_NAMES, "precipitation variable")
        lat_p = _find_one(idx, LAT_NAMES, "latitude coordinate")
        lon_p = _find_one(idx, LON_NAMES, "longitude coordinate")
        lat, lon = np.asarray(f[lat_p][()], dtype=float), np.asarray(f[lon_p][()], dtype=float)
        if lat.ndim != 1 or lon.ndim != 1 or lat.size < 1 or lon.size < 1:
            raise EnvError("lat/lon must be 1-D coordinate vectors")
        if np.nanmax(lon) > 180.0:
            raise EnvError("longitude in 0-360 convention is not supported")
        ds = f[var]
        lat_ax, lon_ax = _axes(ds, lat.size, lon.size)
        other = [i for i in range(ds.ndim) if i not in (lat_ax, lon_ax)]
        if any(ds.shape[i] != 1 for i in other):
            raise EnvError(f"daily file must have a single time step; dataset shape is {ds.shape}")
        res_lat = float(np.median(np.abs(np.diff(lat)))) if lat.size > 1 else float("nan")
        res_lon = float(np.median(np.abs(np.diff(lon)))) if lon.size > 1 else float("nan")
        if not (np.isfinite(res_lat) and np.isfinite(res_lon)):
            raise EnvError("cannot determine grid resolution from a single-cell axis")
        minx, miny, maxx, maxy = aoi.bounds
        ws_lat, ws_lon = _window(lat, miny, maxy, res_lat), _window(lon, minx, maxx, res_lon)
        if ws_lat is None or ws_lon is None:
            raise NotAvailable("AOI is outside the extent of the rainfall grid")

        warns: list[str] = []
        units = _attr(ds, "units")
        kind = normalize_units(units)
        if expected_units == "rate":  # half-hourly product: values are mm/hr RATES (stat fields keep the legacy *_mm_day names)
            if kind in ("daily", "other"):
                raise EnvError(f"{path.name}: units {units!r} are not mm/hr; a half-hourly file must be an mm/hr rate")
            if kind == "unknown":
                warns.append("units attribute missing: mm/hr is ASSUMED for a half-hourly file (not verified in the file)")
        elif kind in ("rate", "other"):
            raise EnvError(f"{path.name}: units {units!r} are not mm/day; a daily file must be mm/day "
                           "(mm/hr rates are never treated as daily accumulations)")
        elif kind == "unknown":
            warns.append("units attribute missing: mm/day is ASSUMED for a daily file (not verified in the file)")

        sl: list[Any] = [0] * ds.ndim
        sl[lat_ax], sl[lon_ax] = ws_lat, ws_lon
        raw = np.asarray(ds[tuple(sl)])
        if lat_ax > lon_ax:
            raw = raw.T
        fill = _first_scalar(ds.attrs.get("_FillValue", ds.attrs.get("missing_value")))
        bad = ~np.isfinite(raw.astype(float))
        if fill is not None:
            bad |= np.isclose(raw.astype(float), fill, rtol=1e-6, atol=0.0)
        vals = raw.astype(np.float64)
        scale, offset = _first_scalar(ds.attrs.get("scale_factor")), _first_scalar(ds.attrs.get("add_offset"))
        if scale is not None:
            vals = vals * scale
        if offset is not None:
            vals = vals + offset
        vals[bad] = np.nan

        file_date = _file_date(f, idx)
        if date is not None and file_date is not None and file_date != date:
            raise EnvError(f"{path.name}: declared date {date} != date in file {file_date}")
        day = date or file_date
        if day is None:
            raise EnvError(f"{path.name}: no date given and none found in the file")

        refuse_if_synthetic(SYNTHETIC_ATTR in f.attrs, EnvError, path.name)
        stat = aoi_statistic(vals, lat[ws_lat], lon[ws_lon], aoi)
        warns += stat.warnings
        ver = _attr(f, "ProductVersion") or _attr(f, "algorithm_version") or _attr(f, "version")
        return DailyAoi(
            date=day, stat=stat, units="mm/hr" if expected_units == "rate" else "mm/day",
            units_verified=(kind == expected_units), fill_value=fill, variable_path=var,
            native_resolution_deg={"lat": res_lat, "lon": res_lon}, synthetic=SYNTHETIC_ATTR in f.attrs,
            dataset_version=str(ver) if ver is not None else None,
            discovered={"precipitation": var, "lat": lat_p, "lon": lon_p, "axes": {"lat": lat_ax, "lon": lon_ax},
                        "shape": list(ds.shape), "window_shape": list(vals.shape)},
            warnings=warns,
        )


__all__ = ["AoiStat", "DailyAoi", "aoi_statistic", "read_daily_aoi", "normalize_units"]
