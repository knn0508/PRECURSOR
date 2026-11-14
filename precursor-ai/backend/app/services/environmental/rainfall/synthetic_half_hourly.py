"""LABELLED SYNTHETIC IMERG-like HALF-HOURLY file (one 30-min interval, values in mm/hr) for tests and demos.

Reuses rainfall/synthetic.py. The layout is the same ASSUMED imitation as the daily fixture (Grid/precipitation,
(time, lon, lat), _FillValue -9999.9); the time variable is ASSUMED to be seconds since 1970-01-01 of the interval START.
Not a copy of a verified real file; passing tests on it is not real-data validation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

from app.services.environmental.rainfall.synthetic import SYNTHETIC_ATTR, write_synthetic_imerg


def write_synthetic_half_hour(path: str | Path, start_time: datetime, rate_mm_hr: float | np.ndarray = 2.0, *,
                              units: str | None = "mm/hr", fill_block: tuple[slice, slice] | None = None,
                              include_time: bool = True) -> Path:
    """`rate_mm_hr` is a scalar (constant field on the default 20x24 grid) or a [lat, lon] array (exact oracle values)."""
    field = np.full((20, 24), float(rate_mm_hr)) if np.isscalar(rate_mm_hr) else np.asarray(rate_mm_hr, dtype=float)
    p = write_synthetic_imerg(path, start_time.date(), field, units=units, fill_block=fill_block, include_time=False)
    with h5py.File(p, "a") as f:
        f.attrs[SYNTHETIC_ATTR] = "SYNTHETIC IMERG-like HALF-HOURLY fixture (mm/hr): not real rainfall"
        if include_time:
            secs = (start_time.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds()
            t = f["Grid"].create_dataset("time", data=np.array([secs], dtype=np.float64))
            t.attrs["units"] = "seconds since 1970-01-01"
    return p
