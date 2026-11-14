"""SYNTHETIC Phase-4-style stacks for Phase 5 tests. Everything here is fabricated (raster tag PRECURSOR_SYNTHETIC_FIXTURE,
manifest entries flagged synthetic). Passing tests on it is NOT real-data validation."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import numpy as np
from affine import Affine
from pyproj import Transformer

from app.services.environmental.dem.slope import slope_degrees
from app.services.environmental.providers.synthetic import write_synthetic_raster

ZONE50 = dict(epsg=32650, x0=600000.0, y0=630000.0)  # near 5.7 N, 116.3 E
ZONE39 = dict(epsg=32639, x0=600000.0, y0=4470000.0)  # near 40.4 N, 49.8 E


def terrain(n: int = 96, res: float = 30.0, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    z = 100 + 40 * np.sin(xx / 17.0) + 30 * np.cos(yy / 23.0) + 0.05 * xx * res + rng.normal(0, 0.3, (n, n))
    return z.astype(np.float32)


def grid_dict(epsg: int, x0: float, y0: float, n: int, res: float) -> dict:
    return {"crs": f"EPSG:{epsg}", "transform": [res, 0.0, x0, 0.0, -res, y0], "width": n, "height": n, "resolution_m": res}


def _entry(lt: str, file: str, *, kind="raster", units=None, temporal="static", origin="SYNTHETIC_FIXTURE", name="synthetic") -> dict:
    return {"layer_id": str(uuid.uuid4()), "layer_type": lt, "kind": kind, "temporal_kind": temporal, "status": "PROCESSED", "units": units,
            "crs": None, "on_reference_grid": True, "source": {"provider": "SYNTHETIC", "dataset_name": name, "dataset_version": None},
            "data_origin": origin, "synthetic": origin == "SYNTHETIC_FIXTURE", "validation_status": "NOT_VALIDATED", "lineage_hash": uuid.uuid4().hex,
            "file": file, "reason": None}


def write_stack(root: Path, area_id: uuid.UUID | None = None, *, epsg: int = 32650, x0: float = 600000.0, y0: float = 630000.0, n: int = 96,
                res: float = 30.0, seed: int = 1, nan_hole: tuple[slice, slice] | None = None, ndvi: bool = True, insar: bool = True,
                slope_layer: bool = True) -> tuple[uuid.UUID, dict, dict[str, np.ndarray]]:
    area_id = area_id or uuid.uuid4()
    env = root / "processed" / "environmental" / str(area_id)
    (env / "aligned").mkdir(parents=True, exist_ok=True)
    (env / "features").mkdir(parents=True, exist_ok=True)
    g = grid_dict(epsg, x0, y0, n, res)
    tf = Affine(*g["transform"])
    z = terrain(n, res, seed)
    if nan_hole is not None:
        z[nan_hole] = np.nan
    arrays = {"ELEVATION": z}
    entries = [_entry("ELEVATION", "elevation.tif", units="metre")]
    if slope_layer:
        arrays["SLOPE"] = slope_degrees(z, g["crs"], tf)
        entries.append(_entry("SLOPE", "slope.tif", units="degree"))
    if ndvi:
        yy, xx = np.mgrid[0:n, 0:n]
        arrays["NDVI"] = (0.5 + 0.3 * np.sin(xx / 9.0) * np.cos(yy / 11.0)).astype(np.float32)
        entries.append(_entry("NDVI", "ndvi.tif", units="NDVI", temporal="dynamic"))
    if insar:
        arrays["INSAR_VELOCITY"] = np.random.default_rng(seed + 7).normal(0, 1, (n, n)).astype(np.float32)
        entries.append(_entry("INSAR_VELOCITY", "insar_velocity.tif", units="mm/yr", temporal="dynamic"))
    for e in entries:
        write_synthetic_raster(env / "aligned" / e["file"], arrays[e["layer_type"]], crs=g["crs"], west=x0, north=y0, pixel=res, nodata=float("nan"))
    ref = {"crs": g["crs"], "epsg": epsg, "resolution": {"x": res, "y": res, "unit": "metre"}, "width": n, "height": n,
           "bounds": [x0, y0 - n * res, x0 + n * res, y0], "transform": g["transform"], "chosen_by": "auto", "warnings": []}
    manifest = {"area_id": str(area_id), "run_id": str(uuid.uuid4()), "reference_grid": ref, "entries": entries, "real_data_validation": "NOT_PERFORMED"}
    (env / "features" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return area_id, g, arrays


def lonlat(g: dict, row: float, col: float) -> tuple[float, float]:
    tf = Affine(*g["transform"])
    cc, rr = col + 0.5, row + 0.5
    x, y = tf.a * cc + tf.b * rr + tf.c, tf.d * cc + tf.e * rr + tf.f
    return Transformer.from_crs(g["crs"], 4326, always_xy=True).transform(x, y)
