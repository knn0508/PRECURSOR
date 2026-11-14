"""Read the Phase 4 stack (manifest.json + aligned rasters) and manage the Phase 5 output layout.

Layout:  data/processed/features/<area_id>/{manifest.json, rasters/}      data/processed/datasets/<area_id>/{manifest.json, samples.parquet, excluded.json}
Source files are only READ. Only file NAMES from the Phase 4 manifest are used, resolved inside the area's `aligned/` directory.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.services.environmental import storage as env_storage
from app.services.environmental.raster.io import inspect_raster, read_float
from app.services.features_cv.tiling import assert_same_grid
from app.services.features_cv.types import FeatureError, NotAvailable

GOOD = ("PROCESSED", "PARTIALLY_PROCESSED")
_SLUG = re.compile(r"[^A-Za-z0-9]+")


def features_dir(data_root: Path, area_id: uuid.UUID) -> Path:
    d = data_root / "processed" / "features" / str(area_id)
    (d / "rasters").mkdir(parents=True, exist_ok=True)
    return d


def datasets_dir(data_root: Path, area_id: uuid.UUID) -> Path:
    d = data_root / "processed" / "datasets" / str(area_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def layer_key(entry: dict[str, Any], taken: set[str]) -> str:
    """Stable column/array key: the layer type, plus a dataset slug only when the type occurs more than once."""
    base = entry["layer_type"]
    if base not in taken:
        return base
    return f"{base}_{_SLUG.sub('_', entry['source'].get('dataset_name') or 'x').strip('_')[:40]}"


@dataclass
class Stack:
    manifest: dict[str, Any]
    manifest_sha256: str
    grid: dict[str, Any]  # crs, transform, width, height, resolution_m
    arrays: dict[str, np.ndarray] = field(default_factory=dict)  # key -> array on the reference grid
    layers: dict[str, dict[str, Any]] = field(default_factory=dict)  # key -> Phase 4 manifest entry
    skipped: list[dict[str, str]] = field(default_factory=list)

    @property
    def contains_synthetic(self) -> bool:
        return any(e.get("synthetic") for e in self.layers.values())


def load_stack(data_root: Path, area_id: uuid.UUID) -> Stack:
    mpath = data_root / "processed" / "environmental" / str(area_id) / "features" / "manifest.json"
    if not mpath.exists():
        raise NotAvailable("no Phase 4 stack manifest for this area: run the environmental pipeline first")
    m = read_json(mpath)
    rg = m.get("reference_grid")
    if not rg:
        raise NotAvailable("the Phase 4 manifest has no reference grid: the stack is not aligned")
    grid = {"crs": rg["crs"], "transform": list(rg["transform"])[:6], "width": rg["width"], "height": rg["height"],
            "resolution_m": float(rg["resolution"]["x"])}
    st = Stack(m, sha256_file(mpath), grid)
    aligned = env_storage.area_dir(data_root, area_id, "aligned").resolve()
    for e in m.get("entries", []):
        if e.get("kind") != "raster":
            continue
        lt = e["layer_type"]
        if e.get("status") not in GOOD or not e.get("file"):
            st.skipped.append({"layer": lt, "reason": f"status {e.get('status')}: {e.get('reason') or 'no file'}"})
            continue
        if not e.get("on_reference_grid"):
            st.skipped.append({"layer": lt, "reason": "not on the reference grid (no aligned copy)"})
            continue
        name = Path(e["file"]).name
        p = (aligned / name).resolve()
        if name != e["file"] or not p.is_relative_to(aligned) or not p.exists():
            st.skipped.append({"layer": lt, "reason": "aligned file missing or name unsafe"})
            continue
        arr, meta = read_float(p)
        assert_same_grid(grid, {"crs": meta.crs, "transform": list(meta.transform), "width": meta.width, "height": meta.height})
        key = layer_key(e, set(st.arrays))
        st.arrays[key], st.layers[key] = arr, e
    if not st.arrays:
        raise NotAvailable("the Phase 4 stack holds no raster layer on the reference grid")
    return st


def inspect_grid(path: Path) -> dict[str, Any]:
    m = inspect_raster(path)
    return {"crs": m.crs, "transform": list(m.transform), "width": m.width, "height": m.height}
