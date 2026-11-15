"""Read ONE daily SMAP L3 radiometer soil-moisture HDF5 file (SPL3SMP_E layout) and reduce each overpass to an AOI statistic.

Verified from the NSIDC SPL3SMP_E V006 user guide (see docs/scientific/SMAP_METHODOLOGY.md): groups
Soil_Moisture_Retrieval_Data_AM / _PM (PM variable names carry the suffix _pm), variables soil_moisture, retrieval_qual_flag,
latitude, longitude (cell centres), fill -9999.0, retrieval_qual_flag bit 0 == 0 means recommended quality.
NOT verified (UNKNOWN): HDF5 attribute names for units/fill in real files, dimensionality of lat/lon in real files. Both 2-D
lat/lon arrays and 1-D axis vectors are therefore accepted, discovered BY NAME. Units are checked, never converted.
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
import shapely
from shapely.geometry.base import BaseGeometry

from app.services.environmental.types import EnvError, NotAvailable
from app.services.insar.hdf import decode

SYNTHETIC_ATTR = "precursor_synthetic_fixture"
GROUPS = {"am": "Soil_Moisture_Retrieval_Data_AM", "pm": "Soil_Moisture_Retrieval_Data_PM"}
VERIFIED_FILL = -9999.0  # NSIDC V006 guide, Table A-1 (soil_moisture, latitude, longitude)
QUAL_FILL = 65534  # NSIDC V006 guide, Table A-1 (retrieval_qual_flag fill/gap value)
QUALITY_BIT_RULE_VERIFIED = True  # bit 0 == 0: recommended quality (V006 guide, Table 6 / Table A-2)
_VOLUMETRIC = {"cm3/cm3", "m3/m3", "cm3cm-3", "m3m-3"}  # volumetric fraction: numerically identical, no conversion
_GLOBAL_9KM_SHAPE = (1624, 3856)  # V006 guide, Table 5


@dataclass
class OverpassStat:
    mean: float | None  # None when no valid cell (missing, NEVER zero)
    min: float | None
    max: float | None
    n_cells: int
    n_valid: int  # valid (finite, not fill, passing the quality filter when on)
    n_dropped_quality: int  # valid cells removed by the quality filter (0 when filter off)
    method: str  # "cell_centres_in_aoi" | "centroid_cell"
    warnings: list[str] = field(default_factory=list)


@dataclass
class DailySmap:
    date: Date
    overpasses: dict[str, OverpassStat | None]  # "am"/"pm"; None = overpass absent/unusable in the file
    units_declared: str | None
    fill_value: float | None  # fill actually applied
    fill_declared: bool
    quality_flag_present: dict[str, bool]
    native_resolution_deg: dict[str, float]
    native_resolution_km: float | None
    grid: str
    synthetic: bool
    dataset_name: str | None
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
    """'volumetric' | 'unknown' | 'other'."""
    if u is None or not str(u).strip():
        return "unknown"
    s = re.sub(r"\s+", "", str(u).strip().lower()).replace("**", "").replace("^", "")
    return "volumetric" if s in _VOLUMETRIC else "other"


def quality_recommended(flag: np.ndarray) -> np.ndarray:
    """True where retrieval_qual_flag has bit 0 (recommended quality), bit 1 (skipped) and bit 2 (unsuccessful) all 0.

    Bit 3 (failed freeze/thaw) is ignored: the guide accepts 0 or 8. The 65534 fill is never recommended."""
    f = np.asarray(flag).astype(np.int64)
    return ((f & 7) == 0) & (f != QUAL_FILL)


def aoi_statistic(field2d: np.ndarray, lat2: np.ndarray, lon2: np.ndarray, aoi: BaseGeometry,
                  keep: np.ndarray | None = None) -> OverpassStat:
    """AOI value from a field with NaN for invalid and 2-D cell-centre lat/lon.

    Cells whose CENTRE lies inside the AOI are used; if none, the single cell containing the AOI centroid (explicit warning).
    `keep` (bool, same shape) is the quality filter: valid cells where it is False are dropped and counted."""
    inside = shapely.contains_xy(aoi, lon2, lat2)
    warns: list[str] = []
    method = "cell_centres_in_aoi"
    if not inside.any():
        c = aoi.centroid
        res_lat = float(np.nanmedian(np.abs(np.diff(lat2, axis=0)))) if lat2.shape[0] > 1 else float("nan")
        res_lon = float(np.nanmedian(np.abs(np.diff(lon2, axis=1)))) if lon2.shape[1] > 1 else float("nan")
        if not (np.isfinite(res_lat) and np.isfinite(res_lon)):
            raise NotAvailable("cannot locate the AOI centroid cell in a single-row/column window")
        dy, dx = np.abs(lat2 - c.y), np.abs(lon2 - c.x)
        i, j = np.unravel_index(int(np.nanargmin(dy / res_lat + dx / res_lon)), dy.shape)
        if dy[i, j] > res_lat / 2 + 1e-9 or dx[i, j] > res_lon / 2 + 1e-9:
            raise NotAvailable("AOI centroid lies outside the SMAP grid window")
        inside = np.zeros_like(inside)
        inside[i, j] = True
        method = "centroid_cell"
        warns.append(f"AOI is smaller than a SMAP cell: the value is the ~{res_lat * 111:.0f} km cell value at the AOI "
                     "centroid (the 9 km grid is interpolated from a ~36 km radiometer footprint), not local soil moisture.")
    vals = field2d[inside]
    valid = np.isfinite(vals)
    dropped = 0
    if keep is not None:
        k = keep[inside]
        dropped = int((valid & ~k).sum())
        valid &= k
    ok = vals[valid]
    if ok.size == 0:
        warns.append("no valid cell for this AOI/overpass: MISSING (not zero)")
        return OverpassStat(None, None, None, int(vals.size), 0, dropped, method, warns)
    return OverpassStat(float(ok.mean()), float(ok.min()), float(ok.max()), int(vals.size), int(ok.size), dropped,
                        method, warns)


def _child(g: h5py.Group, names: tuple[str, ...]) -> h5py.Dataset | None:
    for n in names:
        d = g.get(n)
        if isinstance(d, h5py.Dataset):
            return d
    return None


def _names(base: str, ov: str) -> tuple[str, ...]:
    return (base,) if ov == "am" else (f"{base}_pm", base)


def _window_1d(coord: np.ndarray, lo: float, hi: float, res: float) -> slice | None:
    if hi < coord.min() - res / 2 or lo > coord.max() + res / 2:
        return None
    ix = np.where((coord >= lo - res) & (coord <= hi + res))[0]
    return slice(int(ix.min()), int(ix.max()) + 1) if ix.size else None


def _clean_coord(a: np.ndarray, fill: float | None) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    a[~np.isfinite(a) | np.isclose(a, VERIFIED_FILL) | (False if fill is None else np.isclose(a, fill))] = np.nan
    return a


def _locate(g: h5py.Group, ov: str, ds: h5py.Dataset, aoi: BaseGeometry
            ) -> tuple[tuple[slice, slice], np.ndarray, np.ndarray, dict[str, float], list[str]]:
    """(row, col) window plus 2-D window lat/lon and resolution. Axis-order ambiguity is refused."""
    lat_d, lon_d = _child(g, _names("latitude", ov)), _child(g, _names("longitude", ov))
    if lat_d is None or lon_d is None:
        have = sorted(g.keys())
        raise EnvError(f"{g.name}: latitude/longitude not found (looked for latitude/longitude[_pm]); present: {have}")
    lat, lon = _clean_coord(lat_d[()], _first_scalar(lat_d.attrs.get("_FillValue"))), \
        _clean_coord(lon_d[()], _first_scalar(lon_d.attrs.get("_FillValue")))
    if np.isfinite(lon).any() and np.nanmax(lon) > 180.0:
        raise EnvError("longitude in 0-360 convention is not supported")
    minx, miny, maxx, maxy = aoi.bounds
    if lat.ndim == 2 and lon.ndim == 2:
        if lat.shape != lon.shape or ds.shape != lat.shape:
            raise EnvError(f"{g.name}: lat {lat.shape}, lon {lon.shape} and soil_moisture {ds.shape} shapes differ "
                           "(axis order cannot be established)")
        if min(lat.shape) < 2:
            raise EnvError("grid needs at least 2 rows and 2 columns")
        res_lat = float(np.nanmedian(np.abs(np.diff(lat, axis=0))))
        res_lon = float(np.nanmedian(np.abs(np.diff(lon, axis=1))))
        if not (np.nanmedian(np.abs(np.diff(lat, axis=1))) <= res_lat and np.nanmedian(np.abs(np.diff(lon, axis=0))) <= res_lon):
            raise EnvError("latitude does not vary along rows / longitude along columns: axis order is ambiguous")
        m = (lat >= miny - res_lat) & (lat <= maxy + res_lat) & (lon >= minx - res_lon) & (lon <= maxx + res_lon)
        if not m.any():
            raise NotAvailable("AOI is outside the extent of the SMAP grid")
        r, c = np.where(m)
        win = (slice(int(r.min()), int(r.max()) + 1), slice(int(c.min()), int(c.max()) + 1))
        return win, lat[win], lon[win], {"lat": res_lat, "lon": res_lon}, []
    if lat.ndim == 1 and lon.ndim == 1:
        if lat.size == lon.size:
            raise EnvError("lat and lon vectors have equal length: axis order is ambiguous")
        if ds.shape != (lat.size, lon.size):
            raise EnvError(f"cannot match soil_moisture shape {ds.shape} to lat({lat.size}) x lon({lon.size}) "
                           "(only (lat, lon) order is accepted for axis vectors)")
        if lat.size < 2 or lon.size < 2:
            raise EnvError("grid needs at least 2 rows and 2 columns")
        res_lat, res_lon = float(np.nanmedian(np.abs(np.diff(lat)))), float(np.nanmedian(np.abs(np.diff(lon))))
        wl, wo = _window_1d(lat, miny, maxy, res_lat), _window_1d(lon, minx, maxx, res_lon)
        if wl is None or wo is None:
            raise NotAvailable("AOI is outside the extent of the SMAP grid")
        lon2, lat2 = np.meshgrid(lon[wo], lat[wl])
        return (wl, wo), lat2, lon2, {"lat": res_lat, "lon": res_lon}, []
    raise EnvError(f"{g.name}: latitude/longitude must both be 2-D arrays or both 1-D vectors")


def read_daily_aoi(path: str | Path, aoi: BaseGeometry, date: Date, quality_filter: bool = False) -> DailySmap:
    """Open one daily file, read only the AOI window of each overpass present, return the AOI statistics.

    Raises EnvError (unreadable, no overpass group, missing variable, wrong units, ambiguous axes, filter requested
    but no flag) or NotAvailable (AOI outside the grid)."""
    path = Path(path)
    if aoi.is_empty or not aoi.is_valid:
        raise EnvError("AOI geometry is empty or invalid")
    if quality_filter and not QUALITY_BIT_RULE_VERIFIED:  # pragma: no cover - guard if the rule is ever unverified
        raise EnvError("quality filter requested but the retrieval_qual_flag bit rule is not verified")
    try:
        f = h5py.File(path, "r")
    except OSError as e:
        raise EnvError(f"cannot open {path.name} as HDF5: {e}") from e
    with f:
        warns: list[str] = []
        stats: dict[str, OverpassStat | None] = {"am": None, "pm": None}
        qpresent = {"am": False, "pm": False}
        units_seen: set[str | None] = set()
        fills: set[float] = set()
        declared = True
        res: dict[str, float] | None = None
        shape: tuple[int, ...] | None = None
        disc: dict[str, Any] = {}
        for ov, gname in GROUPS.items():
            g = f.get(gname)
            if not isinstance(g, h5py.Group):
                warns.append(f"{gname} not found: {ov.upper()} overpass absent in this file")
                continue
            ds = _child(g, _names("soil_moisture", ov))
            if ds is None:
                near = sorted(k for k in g.keys() if "soil_moisture" in k)
                raise EnvError(f"{path.name}: soil_moisture variable not found in {gname}; related: {near}")
            units = _attr(ds, "units")
            kind = normalize_units(units)
            if kind == "other":
                raise EnvError(f"{path.name}: units {units!r} are not a volumetric fraction (cm3/cm3 or m3/m3); "
                               "values are never converted silently")
            if kind == "unknown":
                warns.append(f"{ov.upper()}: units attribute missing: volumetric fraction ASSUMED (NSIDC states m3/m3)")
            units_seen.add(str(units) if units is not None else None)
            win, lat2, lon2, r, w2 = _locate(g, ov, ds, aoi)
            res, shape = r, ds.shape
            raw = np.asarray(ds[win], dtype=np.float64)
            fill = _first_scalar(ds.attrs.get("_FillValue", ds.attrs.get("missing_value")))
            if fill is None:
                declared = False
                fill = VERIFIED_FILL
                warns.append(f"{ov.upper()}: fill value not declared in the file; the NSIDC-documented -9999.0 was applied")
            fills.add(fill)
            vals = raw.copy()
            vals[~np.isfinite(raw) | np.isclose(raw, fill)] = np.nan
            if np.isfinite(vals).any() and (np.nanmin(vals) < 0.0 or np.nanmax(vals) > 1.0):
                warns.append(f"{ov.upper()}: soil_moisture values outside 0..1 present (not altered)")
            qd = _child(g, _names("retrieval_qual_flag", ov))
            keep = None
            qpresent[ov] = qd is not None
            if qd is not None and qd.shape == ds.shape:
                keep = quality_recommended(qd[win])
            elif qd is not None:
                warns.append(f"{ov.upper()}: retrieval_qual_flag shape {qd.shape} != soil_moisture shape {ds.shape}: ignored")
            if quality_filter and keep is None:
                raise EnvError(f"{path.name}: quality_filter requested but {gname} has no usable retrieval_qual_flag")
            stats[ov] = aoi_statistic(vals, lat2, lon2, aoi, keep if quality_filter else None)
            warns += [f"{ov.upper()}: {w}" for w in stats[ov].warnings]
            disc[ov] = {"group": gname, "soil_moisture": ds.name, "quality_flag": qd.name if qd is not None else None,
                        "window_shape": list(vals.shape)}
        if res is None:
            raise EnvError(f"{path.name}: no Soil_Moisture_Retrieval_Data_AM/PM group found")
        if len(fills) > 1:
            warns.append("AM and PM declare different fill values")
        if len(units_seen) > 1:
            warns.append("AM and PM declare different units strings")
        km: float | None = 9.0 if shape == _GLOBAL_9KM_SHAPE else None
        if km is None:
            warns.append(f"grid shape {shape} is not the documented 9 km global grid {_GLOBAL_9KM_SHAPE}: native size not stated")
        ver = _attr(f, "ProductVersion") or _attr(f, "algorithm_version") or _attr(f, "version")
        name = _attr(f, "ShortName") or _attr(f, "short_name")
        refuse_if_synthetic(SYNTHETIC_ATTR in f.attrs, EnvError, path.name)
        return DailySmap(
            date=date, overpasses=stats, units_declared=sorted(u for u in units_seen if u)[0] if any(units_seen) else None,
            fill_value=sorted(fills)[0], fill_declared=declared, quality_flag_present=qpresent,
            native_resolution_deg=res, native_resolution_km=km,
            grid="EASE-Grid 2.0 global cylindrical (per NSIDC; projection not read from the file; 2-D/1-D lat/lon used)",
            synthetic=SYNTHETIC_ATTR in f.attrs, dataset_name=str(name) if name else None,
            dataset_version=str(ver) if ver is not None else None, discovered=disc, warnings=warns)


__all__ = ["OverpassStat", "DailySmap", "aoi_statistic", "read_daily_aoi", "normalize_units", "quality_recommended"]
