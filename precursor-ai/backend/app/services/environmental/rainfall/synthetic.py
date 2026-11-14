"""LABELLED SYNTHETIC IMERG-like daily files for tests and demos (HDF5 root attribute precursor_synthetic_fixture).

The layout (Grid/precipitation with (time, lon, lat) order, lat/lon/time vectors, _FillValue -9999.9, units mm/day) is an
ASSUMED imitation of the daily product, not a copy of a verified real file. Values are arbitrary and known exactly.
"""
from __future__ import annotations

from datetime import date as Date
from pathlib import Path

import h5py
import numpy as np

SYNTHETIC_ATTR = "precursor_synthetic_fixture"
FILL = -9999.9


def default_grid(nlat: int = 20, nlon: int = 24, lat0: float = 4.05, lon0: float = 116.05, res: float = 0.1
                 ) -> tuple[np.ndarray, np.ndarray]:
    """Cell CENTRES (ascending). Cell edges fall on x.0 boundaries so oracles are exact."""
    return lat0 + res * np.arange(nlat), lon0 + res * np.arange(nlon)


def write_synthetic_imerg(path: str | Path, day: Date, field: np.ndarray | None = None, *,
                          lat: np.ndarray | None = None, lon: np.ndarray | None = None, units: str | None = "mm/day",
                          layout: str = "time_lon_lat", lat_descending: bool = False,
                          fill_block: tuple[slice, slice] | None = None, include_time: bool = True,
                          var_name: str = "precipitation") -> Path:
    """`field` is indexed [lat_index, lon_index] against the ascending `lat`/`lon` given (default grid 20 lat x 24 lon,
    default value lat_i + 0.01*lon_j). `fill_block` (lat_slice, lon_slice) is written as the fill value.
    layout: 'time_lon_lat' (assumed daily layout) | 'time_lat_lon' | 'lat_lon'. lat_descending flips the stored lat axis."""
    path = Path(path)
    glat, glon = default_grid() if lat is None or lon is None else (lat, lon)
    if field is None:
        field = np.arange(len(glat))[:, None] * 1.0 + np.arange(len(glon))[None, :] * 0.01
    arr = np.array(field, dtype=np.float32)
    if fill_block is not None:
        arr[fill_block] = FILL
    la = np.array(glat, dtype=np.float64)
    if lat_descending:
        la, arr = la[::-1], arr[::-1, :]
    with h5py.File(path, "w") as f:
        f.attrs[SYNTHETIC_ATTR] = "SYNTHETIC IMERG-like daily fixture: not real rainfall"
        g = f.create_group("Grid")
        g.create_dataset("lat", data=la)
        g.create_dataset("lon", data=np.array(glon, dtype=np.float64))
        if include_time:
            t = g.create_dataset("time", data=np.array([(day - Date(1970, 1, 1)).days], dtype=np.float64))
            t.attrs["units"] = "days since 1970-01-01"
        data = {"time_lon_lat": arr.T[None, :, :], "time_lat_lon": arr[None, :, :], "lat_lon": arr}[layout]
        ds = g.create_dataset(var_name, data=data)
        ds.attrs["_FillValue"] = np.float32(FILL)
        if units is not None:
            ds.attrs["units"] = units
    return path


def write_corrupt_file(path: str | Path) -> Path:
    """Not an HDF5 file at all (synthetic corruption)."""
    Path(path).write_bytes(b"SYNTHETIC CORRUPT FILE - not hdf5")
    return Path(path)
