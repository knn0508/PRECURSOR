"""Small h5py helpers. Dataset paths are DISCOVERED by name, never hard-coded: the exact NISAR layout
has not been verified against a real granule in this repository."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import h5py
import numpy as np

SYNTHETIC_MARKER = "precursor_synthetic_fixture"
POLARIZATIONS = ("HH", "HV", "VH", "VV", "RH", "RV", "LH", "LV")


def index_datasets(f: h5py.File) -> dict[str, list[str]]:
    """basename -> [full paths] for every dataset (metadata only; no data is read)."""
    out: dict[str, list[str]] = {}

    def visit(name: str, obj: Any) -> None:
        if isinstance(obj, h5py.Dataset):
            out.setdefault(name.rsplit("/", 1)[-1], []).append("/" + name)

    f.visititems(visit)
    return out


def decode(v: Any) -> Any:
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace").strip()
    if isinstance(v, np.ndarray) and v.shape == ():
        return decode(v.item())
    if isinstance(v, np.generic):
        return decode(v.item())
    return v


def read_scalar(f: h5py.File, path: str) -> Any:
    ds = f[path]
    if ds.size == 0:
        return None
    if ds.size > 1:
        return None
    return decode(ds[()])


def nearest(f: h5py.File, ds_path: str, name: str) -> str | None:
    """Closest dataset called `name` in the same group or an ancestor group."""
    parts = ds_path.strip("/").split("/")[:-1]
    while True:
        grp = "/" + "/".join(parts)
        g = f[grp] if parts else f["/"]
        if name in g and isinstance(g[name], h5py.Dataset):
            return (grp.rstrip("/") + "/" + name)
        if not parts:
            return None
        parts.pop()


def polarization_of(path: str) -> str | None:
    for p in path.strip("/").split("/"):
        if p in POLARIZATIONS:
            return p
    return None


def parse_time(v: Any) -> datetime | None:
    """ISO-8601 like '2025-11-02T12:00:00.123456' (UTC assumed when no zone is given)."""
    s = decode(v)
    if not isinstance(s, str) or not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    m = re.match(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$", s)
    if not m:
        return None
    frac = (m.group(2) or "")[:7]
    try:
        dt = datetime.fromisoformat(m.group(1).replace(" ", "T") + frac + (m.group(3) or ""))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def is_complex_dtype(dt: np.dtype) -> bool:
    """True for native complex and for HDF5 compound {r, i} complex layouts."""
    return dt.kind == "c" or (dt.names is not None and set(dt.names) >= {"r", "i"})


def fill_value_of(ds: h5py.Dataset) -> float | None:
    for k in ("_FillValue", "fill_value", "missing_value"):
        if k in ds.attrs:
            try:
                return float(np.asarray(ds.attrs[k]).ravel()[0])
            except (TypeError, ValueError):
                return None
    return None


def units_of(ds: h5py.Dataset) -> str | None:
    u = ds.attrs.get("units")
    u = decode(u) if u is not None else None
    return u if isinstance(u, str) else None
