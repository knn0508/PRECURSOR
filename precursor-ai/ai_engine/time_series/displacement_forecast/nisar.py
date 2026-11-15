"""NISAR GUNW / GCOV inspection and AOI extraction (observation layer only).

These layers are shown as *observations*. They are never fed to the
OPERA-trained model (different sensor, wavelength, geometry, corrections).
"""
from __future__ import annotations

import h5py
import numpy as np
from pyproj import CRS, Transformer


def list_datasets(h5: h5py.File, max_items: int = 400) -> list[str]:
    out = []
    h5.visititems(lambda n, o: out.append(f"{n} {o.shape} {o.dtype}") if isinstance(o, h5py.Dataset) and len(out) < max_items else None)
    return out


def find(h5: h5py.File, leaf: str, must: tuple[str, ...] = ()) -> list[str]:
    hits = []
    h5.visititems(lambda n, o: hits.append(n) if isinstance(o, h5py.Dataset) and n.split("/")[-1] == leaf and all(m in n for m in must) else None)
    return sorted(hits)


def _grid_crs(grp: h5py.Group) -> CRS:
    for key in ("projection",):
        if key in grp:
            ds = grp[key]
            for a in ("spatial_ref", "crs_wkt"):
                if a in ds.attrs:
                    v = ds.attrs[a]
                    return CRS.from_wkt(v.decode() if isinstance(v, bytes) else v)
            if "epsg_code" in ds.attrs:
                return CRS.from_epsg(int(ds.attrs["epsg_code"]))
            return CRS.from_epsg(int(ds[()]))
    raise ValueError(f"no projection in {grp.name}")


def read_layer(h5: h5py.File, path: str, aoi) -> dict:
    """Read one geocoded 2-D layer inside the AOI using its sibling x/yCoordinates + projection."""
    ds = h5[path]
    grp = ds.parent
    while grp is not None and "xCoordinates" not in grp:
        grp = grp.parent if grp.name != "/" else None
    if grp is None:
        raise ValueError(f"no coordinates for {path}")
    x, y = grp["xCoordinates"][()], grp["yCoordinates"][()]
    crs = _grid_crs(grp)
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = tr.transform([aoi.west, aoi.east, aoi.west, aoi.east], [aoi.south, aoi.south, aoi.north, aoi.north])
    ix = np.where((x >= min(xs)) & (x <= max(xs)))[0]
    iy = np.where((y >= min(ys)) & (y <= max(ys)))[0]
    if len(ix) == 0 or len(iy) == 0:
        raise ValueError(f"AOI does not intersect {path}")
    # coordinate arrays may be pixel-edge or pixel-centre; slicing is the same
    if ds.shape[-2:] != (len(y), len(x)):
        raise ValueError(f"shape {ds.shape} does not match coords {(len(y), len(x))} for {path}")
    arr = ds[..., iy.min():iy.max() + 1, ix.min():ix.max() + 1].astype(np.float32)
    fill = ds.attrs.get("_FillValue")
    if fill is not None:
        arr[arr == np.asarray(fill).astype(np.float32)] = np.nan
    units = ds.attrs.get("units", b"")
    return {"data": arr, "x": x[ix.min():ix.max() + 1], "y": y[iy.min():iy.max() + 1],
            "crs_wkt": crs.to_wkt(), "path": path,
            "units": units.decode() if isinstance(units, bytes) else str(units)}


def identification(h5: h5py.File) -> dict:
    out = {}
    for grp_name in ("science/LSAR/identification",):
        if grp_name in h5:
            for k, v in h5[grp_name].items():
                if isinstance(v, h5py.Dataset) and v.size <= 4:
                    val = v[()]
                    out[k] = val.decode() if isinstance(val, bytes) else (val.tolist() if hasattr(val, "tolist") else val)
    return out


def wavelength_m(h5: h5py.File) -> float | None:
    for p in find(h5, "centerFrequency", ("frequencyA",)):
        f = float(np.ravel(h5[p][()])[0])
        return 299792458.0 / f
    return None


def to_db(power: np.ndarray) -> np.ndarray:
    out = np.full_like(power, np.nan, dtype=np.float32)
    ok = np.isfinite(power) & (power > 0)
    out[ok] = 10 * np.log10(power[ok])
    return out
