"""Raster/metadata writers. Missing data is written as NaN (nodata=NaN), never as zero."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import rasterio.shutil
from affine import Affine
from rasterio.crs import CRS
from rasterio.windows import Window

from app.services.insar.types import GridInfo


class BlockWriter:
    """Writes a float32 single-band tiled GeoTIFF row-block by row-block (bounded memory)."""

    def __init__(self, path: Path, grid: GridInfo, tags: dict[str, str]):
        self.path = path
        crs = CRS.from_epsg(grid.epsg) if grid.epsg else None
        self.ds = rasterio.open(
            path, "w", driver="GTiff", width=grid.width, height=grid.height, count=1, dtype="float32",
            crs=crs, transform=Affine(*grid.transform_tuple()), nodata=float("nan"),
            tiled=True, blockxsize=256, blockysize=256, compress="deflate",
        )
        self.ds.update_tags(**tags)

    def write(self, row0: int, block: np.ndarray) -> None:
        self.ds.write(block.astype("float32"), 1, window=Window(0, row0, block.shape[1], block.shape[0]))

    def close(self) -> None:
        self.ds.close()


def to_cog(src: Path, dst: Path) -> None:
    """Convert via GDAL's COG driver (tiled, overviews, DEFLATE). Tags are carried over."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    rasterio.shutil.copy(src, dst, driver="COG", compress="DEFLATE", blocksize=256)


@dataclass
class RunningStats:
    """Online statistics (no full-array copies)."""

    count: int = 0
    nodata: int = 0
    s: float = 0.0
    ss: float = 0.0
    lo: float = float("inf")
    hi: float = float("-inf")
    extra: dict[str, Any] = field(default_factory=dict)

    def update(self, a: np.ndarray) -> None:
        ok = np.isfinite(a)
        v = a[ok].astype(np.float64)
        self.nodata += int(a.size - v.size)
        if v.size:
            self.count += v.size
            self.s += float(v.sum())
            self.ss += float((v * v).sum())
            self.lo = min(self.lo, float(v.min()))
            self.hi = max(self.hi, float(v.max()))

    def result(self, unit: str) -> dict[str, Any]:
        n, total = self.count, self.count + self.nodata
        mean = self.s / n if n else None
        var = max(self.ss / n - mean * mean, 0.0) if n else None
        return {
            "unit": unit, "valid_pixels": n, "nodata_pixels": self.nodata,
            "nodata_percent": (100.0 * self.nodata / total) if total else None,
            "mean": mean, "std": var ** 0.5 if var is not None else None,
            "min": self.lo if n else None, "max": self.hi if n else None,
        }


def preview_png(cog: Path, vmax: float | None = None, max_size: int = 512, diverging: bool = True) -> bytes:
    """Quick-look PNG for the UI. Values are rendered, not altered; nodata is fully transparent.

    Diverging scale centred on 0 (blue = negative, red = positive). `vmax` is configurable; default is the
    98th percentile of |value| of the (down-sampled) preview, which is stated in the response headers by the API.
    """
    with rasterio.open(cog) as ds:
        scale = max(ds.width, ds.height) / max_size
        h, w = (max(1, int(ds.height / max(scale, 1))), max(1, int(ds.width / max(scale, 1))))
        a = ds.read(1, out_shape=(h, w), resampling=rasterio.enums.Resampling.nearest).astype("float64")
    ok = np.isfinite(a)
    if vmax is None:
        vmax = float(np.percentile(np.abs(a[ok]), 98)) if ok.any() else 1.0
    vmax = vmax if vmax and vmax > 0 else 1.0
    t = np.clip(a / vmax, -1, 1) if diverging else np.clip(a / vmax, 0, 1)
    rgba = np.zeros((4, h, w), dtype="uint8")
    if diverging:
        pos, neg = np.clip(t, 0, 1), np.clip(-t, 0, 1)
        rgba[0] = (255 * (1 - neg * 0.8)).astype("uint8")
        rgba[1] = (255 * (1 - pos * 0.8 - neg * 0.8)).clip(0, 255).astype("uint8")
        rgba[2] = (255 * (1 - pos * 0.8)).astype("uint8")
    else:
        rgba[0] = rgba[1] = rgba[2] = (255 * (1 - t)).astype("uint8")
    rgba[3] = np.where(ok, 255, 0).astype("uint8")
    with rasterio.MemoryFile() as mem:
        with mem.open(driver="PNG", width=w, height=h, count=4, dtype="uint8") as dst:
            dst.write(rgba)
        return mem.read()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def bounds_4326(grid: GridInfo) -> tuple[float, float, float, float]:
    """Bounding box of the grid in EPSG:4326 (corner-transform bbox; an approximation for non-geographic CRS)."""
    a, _, c, _, e, f = grid.transform_tuple()
    xs = [c, c + a * grid.width]
    ys = [f, f + e * grid.height]
    if not grid.epsg or grid.epsg == 4326:
        return (min(xs), min(ys), max(xs), max(ys))
    from pyproj import Transformer

    t = Transformer.from_crs(grid.epsg, 4326, always_xy=True)
    pts = [t.transform(x, y) for x in xs for y in ys]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
