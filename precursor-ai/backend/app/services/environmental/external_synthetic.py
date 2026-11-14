"""LABELLED SYNTHETIC generators for the user-provided layers (lithology, NDVI, river/fault/road). Test/demo use only: every
file carries SYNTHETIC_TAG (rasters) or a top-level "properties": {"synthetic": true} (GeoJSON). Class names are obviously fake."""
from __future__ import annotations

import app.core.geo_env  # noqa: F401  (must precede geo libraries)

import json
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from shapely.geometry import Polygon, box, mapping

from app.services.environmental.raster.alignment import TargetGrid
from app.services.environmental.types import SYNTHETIC_TAG


def utm_epsg(lon: float, lat: float) -> str:
    return f"EPSG:{(32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1}"


def synthetic_grid(lon: float, lat: float, width: int, height: int, res: float = 30.0) -> tuple[TargetGrid, Polygon]:
    """A UTM TargetGrid centred on (lon, lat) and the EPSG:4326 polygon of exactly its extent."""
    crs = utm_epsg(lon, lat)
    x0, y0 = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)
    left, top = x0 - width * res / 2, y0 + height * res / 2
    grid = TargetGrid(crs, Affine(res, 0, left, 0, -res, top), width, height)
    back = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    ring = [back.transform(left + dx * width * res, top - dy * height * res) for dx, dy in ((0, 0), (1, 0), (1, 1), (0, 1))]
    return grid, Polygon(ring)


def write_tif(path: Path, arr: np.ndarray, bounds, crs: str, dtype: str, nodata, tags: dict) -> Path:
    h, w = arr.shape
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=1, dtype=dtype, crs=crs, nodata=nodata,
                       transform=rasterio.transform.from_bounds(*bounds, w, h)) as ds:
        ds.write(arr.astype(dtype), 1)
        ds.update_tags(**{SYNTHETIC_TAG: "1", **tags})
    return path


def make_lithology_raster(d: Path, bounds, crs: str, shape=(30, 30), with_legend: bool = True) -> Path:
    """Three vertical stripes with ids 10, 20, 30; sidecar legend with fake names 'synthetic unit A/B/C'."""
    d.mkdir(parents=True, exist_ok=True)
    cols = np.arange(shape[1]) * 3 // shape[1]
    arr = np.tile(np.array([10, 20, 30])[cols], (shape[0], 1))
    p = write_tif(d / "synthetic_lithology.tif", arr, bounds, crs, "uint16", 65535, {"units": "class id"})
    if with_legend:
        legend = {"classes": [{"id": 10, "name": "synthetic unit A", "color": "#aa0000"}, {"id": 20, "name": "synthetic unit B"},
                              {"id": 30, "name": "synthetic unit C"}], "source": "SYNTHETIC test legend (not real geology)", "synthetic": True}
        (d / "synthetic_lithology.legend.json").write_text(json.dumps(legend), encoding="utf-8")
    return p


def _fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "properties": {"synthetic": True}, "features": features}


def make_lithology_geojson(d: Path, bbox: tuple[float, float, float, float]) -> Path:
    """Two side-by-side EPSG:4326 polygons with attribute 'unit' = 'synthetic unit A/B' (legend sidecar names the attribute)."""
    d.mkdir(parents=True, exist_ok=True)
    w, s, e, n = bbox
    m = (w + e) / 2
    feats = [{"type": "Feature", "properties": {"unit": u}, "geometry": mapping(box(a, s, b, n))}
             for u, a, b in (("synthetic unit A", w, m), ("synthetic unit B", m, e))]
    (d / "synthetic_geology.geojson").write_text(json.dumps(_fc(feats)), encoding="utf-8")
    (d / "synthetic_geology.legend.json").write_text(json.dumps(
        {"classes": [{"id": 1, "name": "synthetic unit A"}, {"id": 2, "name": "synthetic unit B"}], "attribute": "unit",
         "source": "SYNTHETIC test legend (not real geology)"}), encoding="utf-8")
    return d / "synthetic_geology.geojson"


def make_ndvi_raster(d: Path, bounds, crs: str, shape=(30, 30), modis: bool = False) -> Path:
    """Generic: float32 gradient -0.2..0.8. modis=True: int16 DN = NDVI*10000 with scale_factor/_FillValue/valid_range tags
    (MOD13 convention) and one fill pixel at (0, 0)."""
    d.mkdir(parents=True, exist_ok=True)
    g = np.tile(np.linspace(-0.2, 0.8, shape[1]), (shape[0], 1))
    if not modis:
        return write_tif(d / "synthetic_ndvi.tif", g, bounds, crs, "float32", -9999.0, {"units": "NDVI"})
    dn = np.round(g * 10000)
    dn[0, 0] = -3000
    return write_tif(d / "synthetic_MOD13Q1.A2020001.ndvi.tif", dn, bounds, crs, "int16", -3000,
                  {"scale_factor": "0.0001", "_FillValue": "-3000", "valid_range": "-2000, 10000"})


def make_vector_geojson(d: Path, kind: str, bbox: tuple[float, float, float, float]) -> Path:
    """river/fault: a diagonal LineString across bbox; road: a horizontal line through the middle. EPSG:4326."""
    d.mkdir(parents=True, exist_ok=True)
    w, s, e, n = bbox
    coords = [[w, (s + n) / 2], [e, (s + n) / 2]] if kind == "road" else [[w, s], [e, n]]
    doc = _fc([{"type": "Feature", "properties": {"name": f"synthetic {kind}"}, "geometry": {"type": "LineString", "coordinates": coords}}])
    p = d / f"synthetic_{kind}.geojson"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p
