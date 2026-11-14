"""SYNTHETIC raster generators for tests and demos. EVERYTHING here is fake and says so.

Every GeoTIFF written here carries the tag PRECURSOR_SYNTHETIC_FIXTURE=1 (and a description). The generators have
analytic truth (plane slope/azimuth, cone radial aspect, known tile values) so tests can use numerical oracles. The
HGT/zip variant imitates the NASADEM file LAYOUT as believed from SRTM conventions; it is NOT a NASADEM tile and has not
been compared against one. Passing tests on these files is not real-data validation.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

import zipfile
from pathlib import Path

import numpy as np
from affine import Affine
from pyproj import Geod

from app.services.environmental.raster.io import write_geotiff
from app.services.environmental.types import SYNTHETIC_TAG

_GEOD = Geod(ellps="WGS84")
SYNTHETIC_TAGS = {SYNTHETIC_TAG: "1", "description": "SYNTHETIC TEST DATA: not a satellite observation"}


def _write(path: Path, arr: np.ndarray, transform: Affine, crs: str, units: str | None = "metre", **tags) -> Path:
    t = {**SYNTHETIC_TAGS, **{k: str(v) for k, v in tags.items()}}
    if units:
        t["units"] = units
    return write_geotiff(path, arr, transform, crs, t)


def make_plane(path: Path, *, slope_deg: float = 30.0, downslope_azimuth_deg: float = 90.0, shape=(40, 40),
               crs: str = "EPSG:32650", res: float = 30.0, z0: float = 1000.0) -> Path:
    """Projected plane descending toward `downslope_azimuth_deg` (clockwise from N) at exactly `slope_deg`."""
    h, w = shape
    x0, y0 = 500_000.0, 1_000_000.0
    xs = (np.arange(w) + 0.5) * res
    ys = -(np.arange(h) + 0.5) * res  # metres north of the top edge
    xx, yy = np.meshgrid(xs, ys)
    az = np.deg2rad(downslope_azimuth_deg)
    z = z0 - np.tan(np.deg2rad(slope_deg)) * (xx * np.sin(az) + yy * np.cos(az))
    return _write(path, z, Affine(res, 0, x0, 0, -res, y0 + 0.0), crs)


def make_plane_geographic(path: Path, *, lat0: float, slope_deg: float = 30.0, downslope_azimuth_deg: float = 90.0,
                          shape=(40, 40), res_deg: float = 1 / 3600, lon0: float = 116.0, z0: float = 1000.0) -> Path:
    """EPSG:4326 plane whose heights come from true WGS84 geodesic distances (pyproj Geod), independent of slope.py."""
    h, w = shape
    lats = lat0 - (np.arange(h) + 0.5) * res_deg
    lons = lon0 + (np.arange(w) + 0.5) * res_deg
    lat_c, lon_c = lats[h // 2], lons[w // 2]
    LON, LAT = np.meshgrid(lons, lats)
    # geodesic east offset along each row's parallel (via a point on the centre column) and north offset along the meridian
    east = np.array([_GEOD.inv(np.full(w, lon_c), np.full(w, la), lons, np.full(w, la))[2] for la in lats])
    east = np.where(LON >= lon_c, east, -east)
    north = np.array([_GEOD.inv(lon_c, lat_c, lon_c, la)[2] for la in lats])[:, None] * np.sign(LAT - lat_c + 1e-300)
    az = np.deg2rad(downslope_azimuth_deg)
    z = z0 - np.tan(np.deg2rad(slope_deg)) * (east * np.sin(az) + north * np.cos(az))
    return _write(path, z, Affine(res_deg, 0, lon0, 0, -res_deg, lat0), "EPSG:4326")


def make_cone(path: Path, *, slope_deg: float = 20.0, shape=(61, 61), res: float = 30.0, apex: float = 2000.0,
              crs: str = "EPSG:32650") -> Path:
    """Projected cone apex at the centre; slope = slope_deg everywhere off the apex; aspect points radially outward."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - (w - 1) / 2, yy - (h - 1) / 2) * res
    return _write(path, apex - np.tan(np.deg2rad(slope_deg)) * r, Affine(res, 0, 500_000.0, 0, -res, 1_000_000.0), crs)


def make_noisy_terrain(path: Path, *, seed: int = 7, shape=(64, 64), hole=(20, 30, 25, 35), res: float = 30.0,
                       crs: str = "EPSG:32650") -> Path:
    """Smooth sinusoids + seeded noise, with a NaN hole (rows r0:r1, cols c0:c1) to exercise nodata handling."""
    h, w = shape
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    z = 500 + 80 * np.sin(xx / 9.0) + 60 * np.cos(yy / 7.0) + rng.normal(0, 0.5, shape)
    r0, r1, c0, c1 = hole
    z[r0:r1, c0:c1] = np.nan
    return _write(path, z, Affine(res, 0, 500_000.0, 0, -res, 1_000_000.0), crs)


def tile_value(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """The analytic surface all mosaic tiles sample (so overlapping tiles agree exactly)."""
    return 100.0 + 1000.0 * (lon - 116.0) + 500.0 * (lat - 6.0)


def make_mosaic_tiles(out_dir: Path, *, disagree_overlap: bool = False, res: float = 0.01) -> dict[str, Path]:
    """EPSG:4326 tiles of 20x20 px: a (cols 0-19), b (cols 15-34, overlaps a by 5 cols), c (cols 55-74; gap 35-54 = a
    MISSING tile). `disagree_overlap` adds +5 m to b so the overlap check must fire."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, col0 in (("tile_a", 0), ("tile_b", 15), ("tile_c", 55)):
        w = h = 20
        lons = 116.0 + (col0 + np.arange(w) + 0.5) * res
        lats = 6.2 - (np.arange(h) + 0.5) * res
        z = tile_value(*np.meshgrid(lons, lats))
        if disagree_overlap and name == "tile_b":
            z = z + 5.0
        out[name] = _write(out_dir / f"{name}.tif", z, Affine(res, 0, 116.0 + col0 * res, 0, -res, 6.2), "EPSG:4326",
                           vertical_datum="SYNTHETIC_DATUM")
    return out


def make_hgt_zip(path: Path, *, size: int = 3601, void_block: tuple[int, int, int, int] | None = (10, 20, 10, 20)) -> Path:
    """SYNTHETIC `NASADEM_HGT_n06e116.zip` holding `n06e116.hgt` (big-endian int16, size x size, 1 deg, void -32768)."""
    z = (100 + np.add.outer(np.arange(size) * 0.2, np.arange(size) * 0.1)).astype(">i2")
    if void_block:
        r0, r1, c0, c1 = void_block
        z[r0:r1, c0:c1] = -32768
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("n06e116.hgt", z.tobytes())
    return path


def make_hgt(path: Path, *, size: int = 1201) -> Path:
    """SYNTHETIC bare .hgt (file name must follow the tile-name convention, e.g. n06e116.hgt)."""
    z = (100 + np.add.outer(np.arange(size) * 0.2, np.arange(size) * 0.1)).astype(">i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(z.tobytes())
    return path


def make_land_cover(path: Path, *, crs: str = "EPSG:32650", res: float = 30.0) -> Path:
    """SYNTHETIC categorical raster (class ids 10/20/30/40, one NaN nodata cell); ids stored as float32."""
    z = np.kron(np.array([[10, 20], [30, 40]], dtype=np.float32), np.ones((8, 8), dtype=np.float32))
    z[0, 0] = np.nan
    return _write(path, z, Affine(res, 0, 500_000.0, 0, -res, 1_000_000.0), crs, units=None)
