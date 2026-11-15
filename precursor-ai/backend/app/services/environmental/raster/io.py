"""Raster inspection, reading and writing for Phase 4. Reads GeoTIFF, SRTM/NASADEM `.hgt` and `.zip` archives holding one.

Rules: the CRS is never guessed (missing CRS is reported, not defaulted); missing data is NaN, never zero; arrays are
read whole (a 1x1 degree 1-arc-second tile is ~13 M pixels = ~52 MB as float32, fine in memory; larger inputs must be
tiled by the caller).
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401  (must precede geo libraries)

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.errors import RasterioIOError

from app.core.synthetic_guard import refuse_if_synthetic
from app.services.environmental.types import SYNTHETIC_TAG, EnvError

HGT_NODATA = -32768.0  # SRTM HGT void convention (GDAL's HGT driver also reports it); see TERRAIN_METHODOLOGY.md
_RASTER_SUFFIXES = (".hgt", ".tif", ".tiff")


@dataclass
class RasterMeta:
    source_name: str
    source_kind: str  # "tif" | "hgt" | "zip-hgt" | "zip-tif"
    crs: str | None
    crs_error: str | None
    width: int
    height: int
    count: int
    dtype: str
    transform: tuple[float, float, float, float, float, float]  # affine a,b,c,d,e,f
    bounds: tuple[float, float, float, float]  # left, bottom, right, top (raster CRS)
    res_x: float
    res_y: float
    nodata: float | None
    units: str | None
    tags: dict[str, str] = field(default_factory=dict)
    is_synthetic: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def is_geographic(self) -> bool:
        return self.crs is not None and CRS.from_string(self.crs).is_geographic

    def resolution(self) -> dict[str, Any]:
        unit = "unknown"
        if self.crs:
            unit = "degree" if self.is_geographic else "crs_linear_unit"
        return {"x": self.res_x, "y": self.res_y, "unit": unit}


def gdal_path(path: str | Path) -> str:
    """`x.zip` -> /vsizip/ path to its single .hgt/.tif member; anything else is passed through."""
    p = Path(path)
    if str(path).startswith("/vsi"):
        return str(path)
    if not p.exists():
        raise FileNotFoundError(p.name)
    if p.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(p) as z:
                members = [n for n in z.namelist() if n.lower().endswith(_RASTER_SUFFIXES)]
        except zipfile.BadZipFile as exc:
            raise EnvError(f"{p.name}: not a valid zip archive") from exc
        if len(members) != 1:
            raise EnvError(f"{p.name}: expected exactly one .hgt/.tif member, found {len(members)}")
        return f"/vsizip/{p.resolve().as_posix()}/{members[0]}"
    if p.suffix.lower() not in _RASTER_SUFFIXES:
        raise EnvError(f"{p.name}: unsupported raster extension {p.suffix!r}")
    return str(p)


def _kind(path: str | Path, gpath: str) -> str:
    inner = gpath.lower()
    base = "hgt" if inner.endswith(".hgt") else "tif"
    return f"zip-{base}" if Path(path).suffix.lower() == ".zip" else base


def inspect_raster(path: str | Path) -> RasterMeta:
    """Metadata only (no pixel read). A missing/invalid CRS is reported in `crs`/`crs_error`, never defaulted."""
    gp = gdal_path(path)
    try:
        with rasterio.open(gp) as ds:
            crs, crs_error = None, None
            if ds.crs is None or ds.crs.to_string() in ("", None):
                crs_error = "raster has no CRS"
            else:
                crs = ds.crs.to_string()
            tags = dict(ds.tags())
            tags.update({k: v for k, v in ds.tags(1).items() if k not in tags})
            units = tags.get("units") or tags.get("UNITS") or (ds.units[0] if ds.units and ds.units[0] else None)
            kind = _kind(path, gp)
            nodata, notes = ds.nodata, []
            if nodata is None and kind.endswith("hgt"):
                nodata = HGT_NODATA
                notes.append("nodata not declared by file; SRTM HGT void value -32768 assumed")
            refuse_if_synthetic(tags.get(SYNTHETIC_TAG) == "1", EnvError, Path(path).name)
            t = ds.transform
            return RasterMeta(
                source_name=Path(path).name, source_kind=kind, crs=crs, crs_error=crs_error, width=ds.width,
                height=ds.height, count=ds.count, dtype=ds.dtypes[0], transform=(t.a, t.b, t.c, t.d, t.e, t.f),
                bounds=tuple(ds.bounds), res_x=abs(t.a), res_y=abs(t.e), nodata=nodata, units=units, tags=tags,
                is_synthetic=tags.get(SYNTHETIC_TAG) == "1", notes=notes)
    except RasterioIOError as exc:
        raise EnvError(f"{Path(path).name}: cannot be opened as a raster ({exc})") from exc


def read_float(path: str | Path, band: int = 1) -> tuple[np.ndarray, RasterMeta]:
    """Band as float32 with nodata (declared, or HGT -32768) replaced by NaN. Existing NaN stays NaN; 0 stays 0."""
    meta = inspect_raster(path)
    with rasterio.open(gdal_path(path)) as ds:
        arr = ds.read(band).astype(np.float32)
    if meta.nodata is not None and not np.isnan(meta.nodata):
        arr[arr == np.float32(meta.nodata)] = np.nan
    return arr, meta


def write_geotiff(path: str | Path, arr: np.ndarray, transform, crs: str, tags: dict[str, str] | None = None) -> Path:
    """Single-band float32 GeoTIFF, NaN nodata, deflate, tiled when large enough. Whole-array write (memory bound)."""
    if arr.ndim != 2:
        raise EnvError("write_geotiff expects a 2-D array")
    h, w = arr.shape
    opts: dict[str, Any] = {"compress": "deflate"}
    if min(h, w) >= 256:
        opts.update(tiled=True, blockxsize=256, blockysize=256)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=1, dtype="float32", crs=crs,
                       transform=transform, nodata=np.nan, **opts) as ds:
        ds.write(arr.astype(np.float32, copy=False), 1)
        ds.update_tags(**{k: str(v) for k, v in (tags or {}).items()})
    return Path(path)


def crs_is_geographic(crs: str) -> bool:
    return CRS.from_string(crs).is_geographic
