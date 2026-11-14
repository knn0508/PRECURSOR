"""LABELLED SYNTHETIC SMAP-L3-like daily files for tests and demos (HDF5 root attribute precursor_synthetic_fixture).

Group/variable names, fill -9999.0, the uint16 retrieval_qual_flag with fill 65534, and the _pm suffix for PM variables follow the
NSIDC SPL3SMP_E V006 user guide (VERIFIED). ASSUMED (not verified): the `units` / `_FillValue` HDF5 attribute names, 2-D
float32 latitude/longitude arrays, and the grid size (small, not 1624 x 3856). Values are arbitrary and known exactly.
"""
from __future__ import annotations

from datetime import date as Date
from pathlib import Path

import h5py
import numpy as np

SYNTHETIC_ATTR = "precursor_synthetic_fixture"
FILL = -9999.0
QFILL = 65534


def default_grid(nlat: int = 20, nlon: int = 24, lat0: float = 4.05, lon0: float = 116.05, res: float = 0.1
                 ) -> tuple[np.ndarray, np.ndarray]:
    """2-D cell CENTRES (lat descending along rows like a north-up grid, lon ascending); edges on x.0 for exact oracles."""
    lat = lat0 + res * np.arange(nlat)[::-1]
    lon = lon0 + res * np.arange(nlon)
    lon2, lat2 = np.meshgrid(lon, lat)
    return lat2, lon2


def default_field(nlat: int = 20, nlon: int = 24, base: float = 0.10) -> np.ndarray:
    """Row i (northmost = 0) / col j: base + 0.001*(nlat-1-i)*... simple exact value, increasing with latitude index."""
    return base + 0.001 * (nlat - 1 - np.arange(nlat))[:, None] + 0.0001 * np.arange(nlon)[None, :]


def _write_group(f: h5py.File, ov: str, field: np.ndarray, qual: np.ndarray | None, lat2: np.ndarray, lon2: np.ndarray,
                 units: str | None, declare_fill: bool, fill_block: tuple[slice, slice] | None, sm_name: str,
                 swap_latlon_axes: bool) -> None:
    sfx = "_pm" if ov == "pm" else ""
    g = f.create_group(f"Soil_Moisture_Retrieval_Data_{ov.upper()}")
    arr = np.array(field, dtype=np.float32)
    if fill_block is not None:
        arr[fill_block] = FILL
    la, lo = (lat2.T, lon2.T) if swap_latlon_axes else (lat2, lon2)
    g.create_dataset(f"latitude{sfx}", data=la.astype(np.float32))
    g.create_dataset(f"longitude{sfx}", data=lo.astype(np.float32))
    ds = g.create_dataset(sm_name + sfx, data=arr.T if swap_latlon_axes else arr)
    if declare_fill:
        ds.attrs["_FillValue"] = np.float32(FILL)
    if units is not None:
        ds.attrs["units"] = units
    if qual is not None:
        q = g.create_dataset(f"retrieval_qual_flag{sfx}", data=np.array(qual, dtype=np.uint16).T
                             if swap_latlon_axes else np.array(qual, dtype=np.uint16))
        q.attrs["_FillValue"] = np.uint16(QFILL)


def write_synthetic_smap(path: str | Path, day: Date, am: np.ndarray | None = "default", pm: np.ndarray | None = "default", *,
                         lat2: np.ndarray | None = None, lon2: np.ndarray | None = None,
                         qual_am: np.ndarray | None = None, qual_pm: np.ndarray | None = None,
                         units: str | None = "cm**3/cm**3", declare_fill: bool = True,
                         fill_block_am: tuple[slice, slice] | None = None, fill_block_pm: tuple[slice, slice] | None = None,
                         sm_name: str = "soil_moisture", swap_latlon_axes: bool = False,
                         axis_vectors: bool = False, square_vectors: bool = False) -> Path:
    """One SMAP-L3-like file. `am`/`pm` are 2-D fields on the (lat2, lon2) grid (default grid 20 x 24); None omits that group.
    swap_latlon_axes stores everything transposed (ambiguous axis order, must be refused). axis_vectors writes 1-D lat/lon
    vectors instead of 2-D arrays; square_vectors makes them equal length (ambiguous, must be refused)."""
    path = Path(path)
    glat, glon = default_grid() if lat2 is None or lon2 is None else (lat2, lon2)
    fa = default_field(*glat.shape) if isinstance(am, str) else am
    fp = default_field(*glat.shape, base=0.20) if isinstance(pm, str) else pm
    with h5py.File(path, "w") as f:
        f.attrs[SYNTHETIC_ATTR] = "SYNTHETIC SMAP-L3-like daily fixture: not real soil moisture"
        for ov, fld, q, fb in (("am", fa, qual_am, fill_block_am), ("pm", fp, qual_pm, fill_block_pm)):
            if fld is None:
                continue
            if axis_vectors:
                g = f.create_group(f"Soil_Moisture_Retrieval_Data_{ov.upper()}")
                sfx = "_pm" if ov == "pm" else ""
                la, lo = glat[:, 0], glon[0, :]
                if square_vectors:
                    n = min(la.size, lo.size)
                    la, lo, fld = la[:n], lo[:n], np.asarray(fld)[:n, :n]
                g.create_dataset(f"latitude{sfx}", data=la.astype(np.float64))
                g.create_dataset(f"longitude{sfx}", data=lo.astype(np.float64))
                arr = np.array(fld, dtype=np.float32)
                ds = g.create_dataset(sm_name + sfx, data=arr)
                ds.attrs["_FillValue"] = np.float32(FILL)
                if units is not None:
                    ds.attrs["units"] = units
            else:
                _write_group(f, ov, fld, q, glat, glon, units, declare_fill, fb, sm_name, swap_latlon_axes)
    return path


def write_corrupt_file(path: str | Path) -> Path:
    """Not an HDF5 file at all (synthetic corruption)."""
    Path(path).write_bytes(b"SYNTHETIC CORRUPT FILE - not hdf5")
    return Path(path)
