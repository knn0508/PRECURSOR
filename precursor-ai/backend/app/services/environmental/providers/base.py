"""Provider contract for Phase 4 environmental sources and a small local-raster clip helper.

Providers here NEVER download anything: `plan_acquisition` returns a proposal for the user to approve, `local_inputs`
lists files the user already placed in data/external/<provider>/, `read_local` processes them.
(The USGS provider has one extra read-only `fetch` for small JSON, see usgs_earthquake.py.)
"""
from __future__ import annotations

from shapely.geometry.base import BaseGeometry

import app.core.geo_env  # noqa: F401  (must precede geo libraries)

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.errors import RasterioIOError, WindowError
from rasterio.windows import Window, from_bounds

from app.services.environmental.types import SYNTHETIC_TAG, DataOrigin, EnvError, NotAvailable

BBox = tuple[float, float, float, float]  # (west, south, east, north), EPSG:4326 degrees


def aoi_bounds(aoi: Any) -> BBox:
    """AOI -> validated (west, south, east, north). Accepts a 4-tuple or any object with `.bounds` (shapely)."""
    b = tuple(float(v) for v in (aoi.bounds if hasattr(aoi, "bounds") else aoi))
    if len(b) != 4 or not all(np.isfinite(b)):
        raise EnvError("AOI must be four finite numbers (west, south, east, north)")
    w, s, e, n = b
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise EnvError(f"AOI out of range or empty: {b} (antimeridian-crossing AOIs are not supported)")
    return w, s, e, n


@dataclass
class AcquisitionProposal:
    """A PROPOSAL only. Nothing has been downloaded; the user must approve files (name, source, size) first."""

    provider: str
    dataset: str
    version: str | None
    source_urls: list[str]
    aoi_bbox: BBox
    expected_file_count: int | None
    estimated_size_mb: float | None  # ESTIMATE, see size_basis
    size_basis: str
    requires_auth: bool
    auth_note: str
    intended_use: str
    destination: str  # data/external/<provider>/
    notes: list[str] = field(default_factory=list)
    status: str = "PROPOSAL_ONLY_NOT_DOWNLOADED"

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


class EnvironmentalProvider(ABC):
    name: str

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Verified specs + implementation status. No network."""

    @abstractmethod
    def plan_acquisition(self, aoi: Any, **kw: Any) -> AcquisitionProposal:
        """Proposal only. No network, no download."""

    @abstractmethod
    def local_inputs(self, data_root: Path, aoi: Any) -> list[Path]:
        """Files already present in data/external/<provider>/ that cover the AOI."""

    @abstractmethod
    def read_local(self, files: list[Path], aoi: Any, **kw: Any) -> Any:
        """Process local files; raises NotAvailable when there are none."""


def raster_origin(path: Path) -> DataOrigin:
    """SYNTHETIC_FIXTURE iff the file carries the repository's synthetic tag, else LOCAL_UNVERIFIED (never upgraded)."""
    with rasterio.open(path) as src:
        return DataOrigin.SYNTHETIC_FIXTURE if src.tags().get(SYNTHETIC_TAG) else DataOrigin.LOCAL_UNVERIFIED


def _native_bounds(src: rasterio.DatasetReader, bbox: BBox) -> tuple[float, float, float, float]:
    if src.crs is None:
        raise EnvError(f"{Path(src.name).name} has no CRS; refusing to assume one")
    tr = Transformer.from_crs("EPSG:4326", CRS.from_wkt(src.crs.to_wkt()), always_xy=True)
    return tr.transform_bounds(*bbox, densify_pts=21)  # explicit transform; edges densified for projected CRSs


def raster_covers(path: Path, bbox: BBox) -> bool:
    try:
        with rasterio.open(path) as src:
            l, b, r, t = _native_bounds(src, bbox)
            return not (r <= src.bounds.left or l >= src.bounds.right or t <= src.bounds.bottom or b >= src.bounds.top)
    except (RasterioIOError, EnvError):
        return False


@dataclass
class ClipResult:
    data: np.ma.MaskedArray  # band 1, native pixels, mask = nodata (and NaN)
    crs: str
    resolution: tuple[float, float]  # native pixel size in CRS units
    coverage: float  # fraction (0-1) of the AOI window that lies inside the raster
    nodata: float | None
    tags: dict[str, str]
    dtype: str
    warnings: list[str] = field(default_factory=list)  # e.g. AOI smaller than one raster cell
    transform: Any = None  # Affine of the clipped window (native grid, in `crs`)


def clip_raster(path: Path, bbox: BBox, aoi: BaseGeometry | None = None) -> ClipResult:
    """Native-pixel window read (no resampling, so categorical ids stay intact). The AOI is transformed INTO the raster CRS."""
    with rasterio.open(path) as src:
        l, b, r, t = _native_bounds(src, bbox)
        want = from_bounds(l, b, r, t, src.transform)
        try:
            got = want.intersection(Window(0, 0, src.width, src.height))
        except WindowError:
            raise NotAvailable(f"{path.name} does not cover the AOI") from None
        if got.width <= 0 or got.height <= 0:
            raise NotAvailable(f"{path.name} does not cover the AOI")
        cov = float(got.width * got.height / (want.width * want.height))
        # Integer window that fully contains the AOI window: always at least one cell (an AOI smaller than a cell
        # selects the cell(s) it touches instead of failing).
        c0, r0 = int(np.floor(got.col_off)), int(np.floor(got.row_off))
        c1, r1 = int(np.ceil(got.col_off + got.width)), int(np.ceil(got.row_off + got.height))
        c0, r0 = max(c0, 0), max(r0, 0)
        c1, r1 = min(max(c1, c0 + 1), src.width), min(max(r1, r0 + 1), src.height)
        win = Window(c0, r0, c1 - c0, r1 - r0)
        data = src.read(1, window=win, masked=True)
        notes: list[str] = []
        if np.issubdtype(data.dtype, np.floating):
            data = np.ma.masked_invalid(data)
        if aoi is not None and hasattr(aoi, "geom_type"):  # a bare bbox tuple means bbox-only statistics
            # Mask cells whose centre is outside the AOI POLYGON (not just its bbox): statistics are "of the AOI".
            from pyproj import Transformer
            from rasterio.features import geometry_mask
            from shapely.ops import transform as shp_transform

            tr = Transformer.from_crs(4326, src.crs, always_xy=True)
            poly = shp_transform(tr.transform, aoi)
            wt = src.window_transform(win)
            inside = ~geometry_mask([poly], out_shape=data.shape, transform=wt, all_touched=False)
            if not inside.any():  # AOI smaller than a cell: use the cell(s) it touches, and say so
                inside = ~geometry_mask([poly], out_shape=data.shape, transform=wt, all_touched=True)
                notes.append(f"{path.name}: AOI is smaller than one raster cell; the touched cell value is used (resolution not increased)")
            data = np.ma.masked_where(~inside | np.ma.getmaskarray(data), data)
        return ClipResult(data=data, crs=src.crs.to_string(), resolution=(abs(src.res[0]), abs(src.res[1])),
                          coverage=min(cov, 1.0), nodata=src.nodata, tags=src.tags(), dtype=str(src.dtypes[0]), warnings=notes,
                          transform=src.window_transform(win))


def write_clip_geotiff(clip: ClipResult, path: Path, *, tags: dict[str, str] | None = None) -> Path:
    """Write the clipped window on its NATIVE grid, keeping dtype. Masked pixels become the declared nodata (NaN for floats);
    integer rasters without a declared nodata get an unused dtype-max value so missing is never written as a real class/zero."""
    dt = np.dtype(clip.dtype)
    nodata = clip.nodata
    if nodata is None:
        if np.issubdtype(dt, np.floating):
            nodata = float("nan")
        else:
            nodata = int(np.iinfo(dt).max)
            if (clip.data.compressed() == nodata).any():
                raise EnvError("cannot choose a nodata value: raster declares none and dtype max is a data value")
    arr = np.ma.filled(clip.data.astype(dt), nodata)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=dt, crs=clip.crs,
                       transform=clip.transform, nodata=nodata, compress="deflate") as dst:
        dst.write(arr, 1)
        dst.update_tags(**{k: str(v) for k, v in {**clip.tags, **(tags or {})}.items()})
    return path
