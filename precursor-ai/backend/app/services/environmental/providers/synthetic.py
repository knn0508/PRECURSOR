"""SYNTHETIC fixtures for tests and demos. Everything produced here is fabricated and labelled (raster tag SYNTHETIC_TAG,
USGS-style ids prefixed "synthetic"). Passing tests on these is NOT real-data validation."""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from app.services.environmental.types import SYNTHETIC_TAG


def write_synthetic_raster(path: Path, data: np.ndarray, *, crs: str | CRS = "EPSG:4326", west: float, north: float,
                           pixel: float, nodata: float | None = None, tags: dict[str, str] | None = None) -> Path:
    """Single-band GeoTIFF with the synthetic tag. `pixel` is in CRS units."""
    with rasterio.open(path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1, dtype=data.dtype,
                       crs=crs, transform=from_origin(west, north, pixel, pixel), nodata=nodata) as dst:
        dst.write(data, 1)
        dst.update_tags(**{SYNTHETIC_TAG: "1", **(tags or {})})
    return path


def write_synthetic_soil(dir_: Path, prop: str, top: int, bottom: int, stat: str, raw: np.ndarray, **kw: Any) -> Path:
    """File named per the ISRIC convention; `raw` holds MAPPED integers (e.g. clay in g/kg), int16, nodata -32768."""
    p = dir_ / f"{prop}_{top}-{bottom}cm_{stat}.tif"
    kw.setdefault("nodata", -32768)
    return write_synthetic_raster(p, raw.astype("int16"), tags={"property": prop, "depth_cm": f"{top}-{bottom}", "statistic": stat}, **kw)


def write_synthetic_land_cover(path: Path, ids: np.ndarray, **kw: Any) -> Path:
    kw.setdefault("nodata", 0)
    return write_synthetic_raster(path, ids.astype("uint8"), **kw)


def usgs_feature(eid: str, lon: float, lat: float, depth: float | None, mag: float | None, time_ms: Any,
                 place: str = "synthetic place") -> dict[str, Any]:
    return {"type": "Feature", "id": eid,
            "properties": {"mag": mag, "place": place, "time": time_ms, "updated": time_ms, "url": f"https://example.invalid/{eid}",
                           "status": "reviewed", "magType": "mww", "type": "earthquake", "net": "synthetic", "ids": f",{eid},"},
            "geometry": {"type": "Point", "coordinates": [lon, lat] if depth is None else [lon, lat, depth]}}


def usgs_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "metadata": {"title": "SYNTHETIC USGS-style collection", "count": len(features)},
            "features": features}
