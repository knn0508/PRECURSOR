"""M3 preprocessing and harmonization (ML track, ADR-0009). No modelling, no feature selection.

Builds, per study window, on ONE metric reference grid (Phase 4 `build_reference_grid`, UTM chosen from the window centroid,
analysis cell `grid.cell_m` = 5 km, see ml/reports/M3_preprocessing.md for why):
  * terrain factors aggregated from the 30 m NASADEM (slope/aspect by the Phase 4 Horn implementation, strip-wise for memory),
  * land-cover and lithology class FRACTIONS (built on a ~100 m fine grid, then area-averaged),
  * IMERG monthly climatology features (bilinear to the grid; native 0.1 deg is coarser than the cell: OVERSAMPLING recorded),
  * GLC event labels with location-accuracy radii and per-cell label weights.
Phase 2-4 code is imported read-only; nothing here touches the backend, DB or API.
"""
from __future__ import annotations

import hashlib
import json
import warnings
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
import app.core.geo_env  # noqa: E402,F401  (fixes PROJ_LIB before geo libraries load)
import geopandas as gpd  # noqa: E402
import rasterio  # noqa: E402
from app.services.environmental.dem.aspect import aspect_from_gradients  # noqa: E402
from app.services.environmental.dem.slope import slope_from_gradients, terrain_gradients  # noqa: E402
from app.services.environmental.raster.reference_grid import build_reference_grid  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.transform import Affine  # noqa: E402
from rasterio.warp import reproject  # noqa: E402
from rasterio.windows import Window  # noqa: E402
from shapely.geometry import box  # noqa: E402

RAW = ROOT / "data/ml/raw"
INTERIM = ROOT / "data/ml/interim/m3"
CONFIG = ROOT / "ml/configs/m3_study.yaml"
HGT_NODATA = -32768
WC_CLASSES = {10: "tree_cover", 20: "shrubland", 30: "grassland", 40: "cropland", 50: "built_up", 60: "bare_sparse",
              70: "snow_ice", 80: "water", 90: "herbaceous_wetland", 95: "mangroves", 100: "moss_lichen"}
BLOCKS_PER_DEG = 1200  # fine grid: 1/1200 deg ~ 100 m; WorldCover has 12000 px/deg, so 10x10 pixels per block

# ---- ONE lithology class system for the three state maps (all use the shared USGS field GENERALIZE) -------------------
LITH_CLASSES = {1: "IGN_VOLCANIC", 2: "IGN_INTRUSIVE", 3: "METAMORPHIC", 4: "SERPENTINITE", 5: "SED_CLASTIC",
                6: "SED_CARBONATE_CHEMICAL", 7: "UNCONSOLIDATED", 8: "MIXED_UNDIFFERENTIATED", 9: "WATER_ICE"}
LITH_MAP = {
    "Igneous, volcanic": 1,
    "Igneous, intrusive": 2, "Igneous, undifferentiated": 2,
    "Metamorphic, amphibolite": 3, "Metamorphic, carbonate": 3, "Metamorphic, gneiss": 3, "Metamorphic, other": 3,
    "Metamorphic, schist": 3, "Metamorphic, sedimentary clastic": 3, "Metamorphic, sedimentary": 3,
    "Metamorphic, undifferentiated": 3, "Metamorphic, volcanic": 3,
    "Metamorphic, serpentinite": 4,
    "Sedimentary, clastic": 5, "Sedimentary, undifferentiated": 5,
    "Sedimentary, carbonate": 6, "Sedimentary, chemical": 6,
    "Unconsolidated, undifferentiated": 7,
    "Igneous and Metamorphic, undifferentiated": 8, "Igneous and Sedimentary, undifferentiated": 8,
    "Metamorphic and Sedimentary, undifferentiated": 8, "Unconsolidated and Sedimentary, undifferentiated": 8, "Melange": 8,
    "Water": 9, "Ice": 9,
}


def load_config(path: Path = CONFIG) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg["_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return cfg


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def code_version() -> dict:
    def run(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True, cwd=ROOT).stdout.strip()

    return {"git_commit": run("rev-parse", "HEAD") or "UNKNOWN", "dirty": bool(run("status", "--porcelain", "--", "ml/src", "ml/scripts", "ml/configs"))}


# ---------------------------------------------------------------------------------------------------- grid
def make_grid(bbox, cell_m: float):
    return build_reference_grid(box(*bbox), resolution_m=cell_m)


def cell_centres(ref):
    g = ref.grid
    cols, rows = np.meshgrid(np.arange(g.width) + 0.5, np.arange(g.height) + 0.5)
    x = g.transform.c + cols * g.transform.a
    y = g.transform.f + rows * g.transform.e
    lon, lat = Transformer.from_crs(g.crs, 4326, always_xy=True).transform(x, y)
    return x, y, lon, lat


def inside_mask(ref, bbox):
    _, _, lon, lat = cell_centres(ref)
    w, s, e, n = bbox
    return (lon >= w) & (lon < e) & (lat >= s) & (lat < n)


def aggregate(src, src_transform, src_crs, ref, method, src_nodata=np.nan):
    """Area-aggregate a fine raster onto the reference grid (GDAL average/max/q3/...). Nodata stays NaN, never 0."""
    dst = np.full((ref.grid.height, ref.grid.width), np.nan, np.float32)
    reproject(source=src, destination=dst, src_transform=src_transform, src_crs=src_crs, dst_transform=ref.grid.transform,
              dst_crs=ref.grid.crs, resampling=method, src_nodata=src_nodata, dst_nodata=np.nan, init_dest_nodata=True)
    return dst


# ---------------------------------------------------------------------------------------------------- DEM / terrain
def dem_tile_names(bbox):
    w, s, e, n = bbox
    return [(la, lo) for la in range(math.floor(s), math.ceil(n)) for lo in range(math.floor(w), math.ceil(e))]


def tile_file(la, lo, raw=RAW):
    name = f"{'n' if la >= 0 else 's'}{abs(la):02d}{'e' if lo >= 0 else 'w'}{abs(lo):03d}"
    return name, raw / "nasadem" / f"NASADEM_HGT_{name}.zip"


def build_dem_mosaic(bbox, raw=RAW):
    """int16 mosaic of the 1x1 degree HGT tiles covering `bbox` (nodata -32768) + its geographic transform. Tiles overlap by
    one pixel row/column; a missing tile (ocean) stays nodata and is reported."""
    tiles = dem_tile_names(bbox)
    lats = [t[0] for t in tiles]
    lons = [t[1] for t in tiles]
    min_lo, max_la = min(lons), max(lats)
    h = (max(lats) - min(lats) + 1) * 3600 + 1
    w = (max(lons) - min(lons) + 1) * 3600 + 1
    mosaic = np.full((h, w), HGT_NODATA, np.int16)
    missing = []
    for la, lo in tiles:
        name, p = tile_file(la, lo, raw)
        if not p.exists():
            missing.append(name)
            continue
        with rasterio.open(f"/vsizip/{p.as_posix()}/{name}.hgt") as d:
            a = d.read(1)
        r0, c0 = (max_la - la) * 3600, (lo - min_lo) * 3600
        sub = mosaic[r0:r0 + a.shape[0], c0:c0 + a.shape[1]]
        ok = a != HGT_NODATA
        sub[ok] = a[ok]
    px = 1 / 3600
    tr = Affine(px, 0, min_lo - px / 2, 0, -px, (max_la + 1) + px / 2)
    return mosaic, tr, missing


def terrain_strips(mosaic, transform, crs="EPSG:4326", band_rows=3600):
    """Slope (deg, float32) and aspect (deg x10, int16, -1 = undefined) from the Phase 4 Horn functions, computed in
    latitude strips with a one-row halo so seams are exact and memory stays bounded."""
    height, width = mosaic.shape
    slope = np.full((height, width), np.nan, np.float32)
    aspect = np.full((height, width), -1, np.int16)
    for r0 in range(0, height, band_rows):
        r1 = min(height, r0 + band_rows)
        a, b = max(0, r0 - 1), min(height, r1 + 1)
        z = mosaic[a:b].astype(np.float32)
        z[mosaic[a:b] == HGT_NODATA] = np.nan
        gx, gy = terrain_gradients(z, crs, transform @ Affine.translation(0, a))
        sl = slope_from_gradients(gx, gy)
        ap = aspect_from_gradients(gx, gy).aspect
        core = slice(r0 - a, r0 - a + (r1 - r0))
        slope[r0:r1] = sl[core].astype(np.float32)
        apc = ap[core]
        aspect[r0:r1] = np.where(np.isfinite(apc), np.round(np.nan_to_num(apc) * 10), -1).astype(np.int16)
        del z, gx, gy, sl, ap
    return slope, aspect


def _sincos(aspect, fn):
    out = np.full(aspect.shape, np.nan, np.float32)
    for r in range(0, aspect.shape[0], 1000):
        a = aspect[r:r + 1000]
        out[r:r + 1000] = np.where(a >= 0, fn(np.deg2rad(a.astype(np.float32) / 10.0)), np.nan)
    return out


def terrain_features(mosaic, transform, ref, thresholds=(15, 30)):
    """Per-cell terrain statistics. Returns (dict name -> array, band metadata)."""
    slope, aspect = terrain_strips(mosaic, transform)
    crs = "EPSG:4326"
    f, meta = {}, {}

    def put(name, arr, unit, desc, how):
        f[name] = arr
        meta[name] = {"unit": unit, "description": desc, "aggregation": how, "source": "NASADEM_HGT 001 (30 m)"}

    put("elev_mean", aggregate(mosaic, transform, crs, ref, Resampling.average, HGT_NODATA), "m", "mean elevation", "area average of 30 m cells")
    put("elev_min", aggregate(mosaic, transform, crs, ref, Resampling.min, HGT_NODATA), "m", "minimum elevation", "GDAL min")
    put("elev_max", aggregate(mosaic, transform, crs, ref, Resampling.max, HGT_NODATA), "m", "maximum elevation", "GDAL max")
    f["relief"] = f["elev_max"] - f["elev_min"]
    meta["relief"] = {"unit": "m", "description": "max - min elevation inside the cell", "aggregation": "derived", "source": "NASADEM"}
    valid = (mosaic != HGT_NODATA).astype(np.float32)
    put("dem_cover", aggregate(valid, transform, crs, ref, Resampling.average, None), "fraction", "fraction of the cell with DEM data", "area average of validity")
    del valid
    z0 = np.float32(np.median(mosaic[::50, ::50][mosaic[::50, ::50] != HGT_NODATA])) if (mosaic != HGT_NODATA).any() else np.float32(0)
    zc = mosaic.astype(np.float32)
    zc[mosaic == HGT_NODATA] = np.nan
    zc -= z0
    zc *= zc
    msq = aggregate(zc, transform, crs, ref, Resampling.average, np.nan)
    del zc
    var = msq - (f["elev_mean"] - z0) ** 2
    put("elev_std", np.sqrt(np.maximum(var, 0)).astype(np.float32), "m", "standard deviation of 30 m elevation in the cell", "sqrt(E[z^2]-E[z]^2)")
    put("slope_mean", aggregate(slope, transform, crs, ref, Resampling.average, np.nan), "deg", "mean of 30 m slope (not the 5 km-scale slope)", "area average")
    put("slope_q3", aggregate(slope, transform, crs, ref, Resampling.q3, np.nan), "deg", "3rd quartile of 30 m slope", "GDAL q3")
    put("slope_max", aggregate(slope, transform, crs, ref, Resampling.max, np.nan), "deg", "maximum 30 m slope", "GDAL max")
    for t in thresholds:
        ind = np.where(np.isnan(slope), np.nan, (slope > t).astype(np.float32)).astype(np.float32)
        put(f"slope_frac_gt{t}", aggregate(ind, transform, crs, ref, Resampling.average, np.nan), "fraction", f"fraction of 30 m cells steeper than {t} deg", "area average of indicator")
        del ind
    del slope
    sn = aggregate(_sincos(aspect, np.sin), transform, crs, ref, Resampling.average, np.nan)
    cs = aggregate(_sincos(aspect, np.cos), transform, crs, ref, Resampling.average, np.nan)
    put("aspect_sin_mean", sn, "unitless", "mean sin(aspect): east-west component of downslope direction", "area average (flat cells excluded)")
    put("aspect_cos_mean", cs, "unitless", "mean cos(aspect): north-south component of downslope direction", "area average (flat cells excluded)")
    put("aspect_resultant", np.sqrt(sn ** 2 + cs ** 2).astype(np.float32), "unitless", "mean resultant length of aspect (0 = all directions, 1 = uniform)", "derived")
    return f, meta


# ---------------------------------------------------------------------------------------------------- fine grid helpers
def fine_grid(bbox):
    w, s, e, n = bbox
    lon0, lon1 = math.floor(w * BLOCKS_PER_DEG), math.ceil(e * BLOCKS_PER_DEG)
    top, bot = math.ceil(n * BLOCKS_PER_DEG), math.floor(s * BLOCKS_PER_DEG)
    wb, hb = lon1 - lon0, top - bot
    tr = Affine(1 / BLOCKS_PER_DEG, 0, lon0 / BLOCKS_PER_DEG, 0, -1 / BLOCKS_PER_DEG, top / BLOCKS_PER_DEG)
    return lon0, top, wb, hb, tr


def worldcover_counts(bbox, raw=RAW):
    """Per 100 m block: count (0..100) of WorldCover pixels per class and of valid pixels (class 0 = no data)."""
    lon0, top, wb, hb, tr = fine_grid(bbox)
    counts = np.zeros((len(WC_CLASSES), hb, wb), np.uint8)
    valid = np.zeros((hb, wb), np.uint8)
    tiles, missing = [], []
    for p in sorted((raw / "worldcover").glob("ESA_WorldCover_10m_2021_v200_*_Map.tif")):
        tag = p.name.split("_")[5]
        lat_s = int(tag[1:3]) * (1 if tag[0] == "N" else -1)
        lon_w = int(tag[4:7]) * (1 if tag[3] == "E" else -1)
        lat_n = lat_s + 3
        l_min, l_max = max(lon0, lon_w * BLOCKS_PER_DEG), min(lon0 + wb, (lon_w + 3) * BLOCKS_PER_DEG)
        t_max, t_min = min(top, lat_n * BLOCKS_PER_DEG), max(top - hb + 1, lat_s * BLOCKS_PER_DEG + 1)
        if l_max <= l_min or t_max < t_min:
            continue
        tiles.append(p.name)
        c0, r0 = l_min - lon0, top - t_max
        nl, nt = l_max - l_min, t_max - t_min + 1
        pc0, pr0 = (l_min - lon_w * BLOCKS_PER_DEG) * 10, (lat_n * BLOCKS_PER_DEG - t_max) * 10
        with rasterio.open(p) as d:
            for k in range(0, nt, 100):
                m = min(100, nt - k)
                a = d.read(1, window=Window(pc0, pr0 + k * 10, nl * 10, m * 10)).reshape(m, 10, nl, 10)
                valid[r0 + k:r0 + k + m, c0:c0 + nl] = (a != 0).sum(axis=(1, 3))
                for i, c in enumerate(WC_CLASSES):
                    counts[i, r0 + k:r0 + k + m, c0:c0 + nl] = (a == c).sum(axis=(1, 3))
    return counts, valid, tr, tiles


def landcover_features(bbox, ref, raw=RAW):
    counts, valid, tr, tiles = worldcover_counts(bbox, raw)
    crs = "EPSG:4326"
    vfrac = aggregate(valid.astype(np.float32), tr, crs, ref, Resampling.average, None)
    f, meta = {"lc_valid_frac": vfrac / 100.0}, {"lc_valid_frac": {"unit": "fraction", "description": "fraction of the cell with WorldCover data (ocean = no data)",
                                                                   "aggregation": "area average", "source": "ESA WorldCover 2021 v200"}}
    for i, (c, name) in enumerate(WC_CLASSES.items()):
        a = aggregate(counts[i].astype(np.float32), tr, crs, ref, Resampling.average, None)
        with np.errstate(invalid="ignore", divide="ignore"):
            frac = np.where(vfrac > 0, a / vfrac, np.nan).astype(np.float32)
        f[f"lc_{name}"] = frac
        meta[f"lc_{name}"] = {"unit": "fraction", "description": f"WorldCover class {c} ({name}) share of valid 10 m pixels", "aggregation": "class counts per 100 m block -> area average -> / valid share",
                              "source": "ESA WorldCover 2021 v200"}
    return f, meta, tiles


def read_geology(bbox, raw=RAW):
    parts, report = [], {}
    for st in ("CA", "OR", "WA"):
        z = raw / "geology_state" / f"{st}.zip"
        g = gpd.read_file(f"zip://{z.as_posix()}!{st}_geol_poly.shp", bbox=tuple(bbox))
        parts.append(g[["GENERALIZE", "geometry"]].assign(state=st))
        report[st] = int(len(g))
    gdf = pd.concat(parts, ignore_index=True) if parts else gpd.GeoDataFrame()
    code = gdf["GENERALIZE"].map(LITH_MAP)
    unmapped = sorted(gdf.loc[code.isna(), "GENERALIZE"].astype(str).unique().tolist())
    gdf["lith"] = code.fillna(0).astype(np.uint8)
    return gdf, unmapped, report


def lithology_features(bbox, ref, raw=RAW):
    gdf, unmapped, report = read_geology(bbox, raw)
    lon0, top, wb, hb, tr = fine_grid(bbox)
    shapes = [(geom, int(c)) for geom, c in zip(gdf.geometry, gdf["lith"]) if c > 0 and geom is not None and not geom.is_empty]
    cls = rasterize(shapes, out_shape=(hb, wb), transform=tr, fill=0, dtype="uint8", all_touched=False) if shapes else np.zeros((hb, wb), np.uint8)
    crs = "EPSG:4326"
    cover = aggregate((cls > 0).astype(np.float32), tr, crs, ref, Resampling.average, None)
    f, meta = {"lith_cover": cover}, {"lith_cover": {"unit": "fraction", "description": "fraction of the cell covered by a mapped geologic polygon (CA/OR/WA only; elsewhere no data)",
                                                      "aggregation": "area average of rasterised coverage", "source": "USGS per-state geologic maps"}}
    for c, name in LITH_CLASSES.items():
        a = aggregate((cls == c).astype(np.float32), tr, crs, ref, Resampling.average, None)
        with np.errstate(invalid="ignore", divide="ignore"):
            frac = np.where(cover > 0, a / cover, np.nan).astype(np.float32)
        f[f"lith_{name}"] = frac
        meta[f"lith_{name}"] = {"unit": "fraction", "description": f"share of covered area in class {c} {name} (GENERALIZE mapping)", "aggregation": "class raster at ~100 m -> area average / cover",
                                "source": "USGS per-state geologic maps (relation to SGMC v1.1 NOT_VERIFIED)"}
    present = {k: int(v) for k, v in zip(*np.unique(gdf["GENERALIZE"].astype(str), return_counts=True))}
    return f, meta, {"unmapped_generalize_values": unmapped, "polygons_read_by_state": report, "generalize_values_present": present}


# ---------------------------------------------------------------------------------------------------- IMERG
def imerg_files(raw=RAW):
    return sorted((raw / "imerg_monthly").glob("3B-MO.MS.MRG.3IMERG.*.HDF5"))


def month_of(p: Path):
    s = p.name.split(".")[4][:8]
    return datetime(int(s[:4]), int(s[4:6]), 1, tzinfo=timezone.utc)


def read_imerg_window(bbox, raw=RAW, margin=0.2):
    """Monthly precipitation (mm/month, float32, north-up) over `bbox` (+margin) at the native 0.1 deg grid, from GDAL's
    HDF5 driver. The array is [lon, lat] (dims time, lon, lat; cell centres, registration CENTER, origin south-west)."""
    w, s, e, n = bbox
    i0, i1 = math.floor((w - margin + 180) / 0.1), math.ceil((e + margin + 180) / 0.1)
    j0, j1 = math.floor((s - margin + 90) / 0.1), math.ceil((n + margin + 90) / 0.1)
    files = imerg_files(raw)
    months, data = [], []
    for p in files:
        with warnings.catch_warnings():  # GDAL sees a plain array without a geotransform; the grid is applied explicitly below
            warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
            with rasterio.open(f'HDF5:"{p.as_posix()}"://Grid/precipitation') as d:
                a = d.read(1, window=Window(j0, i0, j1 - j0, i1 - i0)).astype(np.float32)  # rows = lon index, cols = lat index
        a[a < -9000] = np.nan
        m = month_of(p)
        nxt = datetime(m.year + (m.month == 12), m.month % 12 + 1, 1, tzinfo=timezone.utc)
        hours = (nxt - m).days * 24
        data.append(np.flipud(a.T) * hours)  # -> [lat north-down, lon], mm per month
        months.append(m)
    lon = -180 + 0.05 + 0.1 * np.arange(i0, i1)
    lat = (-90 + 0.05 + 0.1 * np.arange(j0, j1))[::-1]
    west, north = -180 + 0.1 * i0, -90 + 0.1 * j1
    return {"months": months, "precip_mm_month": np.stack(data), "lon": lon, "lat": lat,
            "transform": Affine(0.1, 0, west, 0, -0.1, north), "n_files": len(files)}


def rainfall_climatology(series, years):
    """Climatology on the native grid from full calendar years `years` = (first, last). All inputs are monthly sums in mm."""
    months = series["months"]
    p = series["precip_mm_month"]
    y0, y1 = years
    idx = {(m.year, m.month): k for k, m in enumerate(months)}
    need = [(y, m) for y in range(y0, y1 + 1) for m in range(1, 13)]
    if any(k not in idx for k in need):
        raise ValueError("IMERG months missing for the climatology years")
    ann = np.stack([sum(p[idx[(y, m)]] for m in range(1, 13)) for y in range(y0, y1 + 1)])
    clim = np.stack([np.mean([p[idx[(y, m)]] for y in range(y0, y1 + 1)], axis=0) for m in range(1, 13)])  # 12 monthly means
    mapv = ann.mean(0)
    djf = np.mean([p[idx[(y - 1, 12)]] + p[idx[(y, 1)]] + p[idx[(y, 2)]] for y in range(y0, y1 + 1) if (y - 1, 12) in idx], axis=0)
    jja = np.mean([p[idx[(y, 6)]] + p[idx[(y, 7)]] + p[idx[(y, 8)]] for y in range(y0, y1 + 1)], axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        si = np.abs(clim - mapv / 12).sum(0) / mapv  # Walsh & Lawler seasonality index
        cv = ann.std(0) / mapv
    return {"rain_map_mm": mapv, "rain_djf_mm": djf, "rain_jja_mm": jja, "rain_max_month_clim_mm": clim.max(0),
            "rain_interannual_cv": cv, "rain_seasonality_index": si}


def rainfall_features(series, ref, years):
    clim = rainfall_climatology(series, years)
    tr = series["transform"]
    f, meta = {}, {}
    units = {"rain_map_mm": "mm/yr", "rain_djf_mm": "mm/season", "rain_jja_mm": "mm/season", "rain_max_month_clim_mm": "mm/month",
             "rain_interannual_cv": "ratio", "rain_seasonality_index": "ratio"}
    for k, a in clim.items():
        f[k] = aggregate(a.astype(np.float32), tr, "EPSG:4326", ref, Resampling.bilinear, np.nan)
        meta[k] = {"unit": units[k], "description": f"IMERG V07 Final monthly climatology {years[0]}-{years[1]}: {k}",
                   "aggregation": "native 0.1 deg field, bilinear to the 5 km grid (OVERSAMPLING: no new detail)", "source": "GPM_3IMERGM V07 (UTC calendar months)"}
    return f, meta


# ---------------------------------------------------------------------------------------------------- labels
def load_glc(path=RAW / "census/glc.csv"):
    g = pd.read_csv(path)
    g["date"] = pd.to_datetime(g.event_date, format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    return g


def build_events(bbox, ref, cfg, series=None, glc=None):
    """GLC rows inside `bbox` with usability flags, accuracy radius, grid cell and per-cell label weights."""
    g = load_glc() if glc is None else glc
    w, s, e, n = bbox
    ev = g[(g.longitude >= w) & (g.longitude < e) & (g.latitude >= s) & (g.latitude < n)].copy()
    lab = cfg["labels"]
    ev["acc"] = ev.location_accuracy.fillna("unknown")
    ev["radius_m"] = ev.acc.map(lab["accuracy_radius_m"]).astype(float)  # NaN for 'unknown'
    rain = {"rain", "downpour", "continuous_rain", "tropical_cyclone", "monsoon"}
    bad_cat = {"snow_avalanche", "lahar", "riverbank_collapse", "unknown"}
    base = ev.date.notna() & ev.landslide_trigger.isin(rain) & ~ev.landslide_category.fillna("unknown").isin(bad_cat)
    lo, hi = (pd.Timestamp(x) for x in lab["in_period"])
    ev["usable_base"] = base
    ev["strict_all_years"] = base & ev.acc.isin(lab["strict_classes"])
    ev["strict_in_period"] = ev.strict_all_years & ev.date.between(lo, hi)
    x, y = Transformer.from_crs(4326, ref.grid.crs, always_xy=True).transform(ev.longitude.values, ev.latitude.values)
    ev["x_m"], ev["y_m"] = x, y
    t = ref.grid.transform
    res = ref.resolution_m
    col = np.floor((x - t.c) / res).astype(int)
    row = np.floor((y - t.f) / t.e).astype(int)
    ev["row"], ev["col"] = row, col
    ev["in_grid"] = (row >= 0) & (row < ref.grid.height) & (col >= 0) & (col < ref.grid.width)
    n_cells = np.zeros(len(ev), int)
    cells = []
    for k, (xx, yy, r) in enumerate(zip(x, y, ev.radius_m.values)):
        if not np.isfinite(r):
            cells.append([])
            continue
        c0, c1 = math.floor((xx - r - t.c) / res), math.floor((xx + r - t.c) / res)
        r0, r1 = math.floor((t.f - (yy + r)) / res), math.floor((t.f - (yy - r)) / res)
        lst = []
        for rr in range(r0, r1 + 1):
            for cc in range(c0, c1 + 1):
                if not (0 <= rr < ref.grid.height and 0 <= cc < ref.grid.width):
                    continue
                left, top = t.c + cc * res, t.f - rr * res
                dx = max(left - xx, 0, xx - (left + res))
                dy = max(top - res - yy, 0, yy - top)
                if dx * dx + dy * dy <= r * r:
                    lst.append((rr, cc))
        cells.append(lst)
        n_cells[k] = len(lst)
    ev["n_cells_in_radius"] = n_cells
    ev["label_ambiguous"] = ev.n_cells_in_radius > 1
    if series is not None:
        ev = _attach_prior_rain(ev, series)
    return ev, cells


def _attach_prior_rain(ev, series):
    """Rainfall of the 1 and 3 calendar months STRICTLY BEFORE the event month (nearest 0.1 deg cell). The event month itself is
    deliberately not provided: it contains post-event days (leakage)."""
    months = series["months"]
    idx = {(m.year, m.month): k for k, m in enumerate(months)}
    lon, lat = series["lon"], series["lat"]
    p1, p3 = [], []
    for lo, la, d in zip(ev.longitude.values, ev.latitude.values, ev.date):
        j, i = int(np.argmin(np.abs(lat - la))), int(np.argmin(np.abs(lon - lo)))
        prev = [(d.year + (d.month - k - 1) // 12, (d.month - k - 1) % 12 + 1) for k in range(1, 4)]
        try:
            vals = [series["precip_mm_month"][idx[m], j, i] for m in prev]
            p1.append(vals[0])
            p3.append(float(np.sum(vals)))
        except KeyError:
            p1.append(np.nan)
            p3.append(np.nan)
    ev["rain_prev_1m_mm"], ev["rain_prev_3m_mm"] = p1, p3
    return ev


def label_rasters(ev, cells, ref):
    h, w = ref.grid.height, ref.grid.width
    out = {}
    for tag in ("strict_all_years", "strict_in_period"):
        pc, wt = np.zeros((h, w), np.float32), np.zeros((h, w), np.float32)
        for use, lst, r, c, ing in zip(ev[tag].values, cells, ev.row.values, ev.col.values, ev.in_grid.values):
            if not use:
                continue
            if ing:
                pc[r, c] += 1
            if lst:
                for rr, cc in lst:
                    wt[rr, cc] += 1.0 / len(lst)
        out[f"label_point_count_{tag}"], out[f"label_weight_{tag}"] = pc, wt
    return out


# ---------------------------------------------------------------------------------------------------- persistence
def write_multiband(path: Path, arrays: dict, ref, meta: dict | None = None):
    names = list(arrays)
    path.parent.mkdir(parents=True, exist_ok=True)
    g = ref.grid
    with rasterio.open(path, "w", driver="GTiff", height=g.height, width=g.width, count=len(names), dtype="float32", crs=g.crs,
                       transform=g.transform, nodata=np.nan, compress="deflate", predictor=3, tiled=True, blockxsize=256, blockysize=256) as d:
        for i, nme in enumerate(names, 1):
            d.write(arrays[nme].astype(np.float32), i)
            d.set_band_description(i, nme)
        d.update_tags(**{k: str(v) for k, v in (meta or {}).items()})
    return path


def run_window(name, bbox, cfg, out_root=INTERIM, raw=RAW, series_cache=None):
    """Full M3 product set for one window. Deterministic (no randomness)."""
    out = Path(out_root) / name
    out.mkdir(parents=True, exist_ok=True)
    cell = float(cfg["grid"]["cell_m"])
    ref = make_grid(bbox, cell)
    inside = inside_mask(ref, bbox)
    warns = list(ref.warnings)
    mosaic, tr, missing = build_dem_mosaic(bbox, raw)
    feats, meta = terrain_features(mosaic, tr, ref, tuple(cfg["terrain"]["slope_thresholds_deg"]))
    del mosaic
    lc, lcm, lc_tiles = landcover_features(bbox, ref, raw)
    li, lim, lith_report = lithology_features(bbox, ref, raw)
    series = read_imerg_window(bbox, raw)
    rf, rfm = rainfall_features(series, ref, tuple(cfg["rainfall"]["climatology_years"]))
    feats.update(lc)
    feats.update(li)
    feats.update(rf)
    meta.update(lcm)
    meta.update(lim)
    meta.update(rfm)
    for k in feats:  # cells whose centre lies outside the window are not part of the study area
        feats[k] = np.where(inside, feats[k], np.nan).astype(np.float32)
    feats["inside_aoi"] = inside.astype(np.float32)
    meta["inside_aoi"] = {"unit": "flag", "description": "cell centre inside the window polygon", "aggregation": "n/a", "source": "config"}
    sf = write_multiband(out / "static_factors.tif", feats, ref, {"study": cfg["study"], "cell_m": cell, "config_sha256": cfg["_sha256"]})
    ev, cells = build_events(bbox, ref, cfg, series)
    lr = label_rasters(ev, cells, ref)
    lg = write_multiband(out / "labels_grid.tif", lr, ref, {"note": "weights spread each event over the cells its accuracy circle touches"})
    ev.drop(columns=["event_description", "photo_link", "notes"], errors="ignore").to_parquet(out / "events.parquet", index=False)
    np.savez_compressed(out / "imerg_monthly.npz", precip_mm_month=series["precip_mm_month"],
                        month_start_utc=np.array([m.isoformat() for m in series["months"]]), lon=series["lon"], lat=series["lat"])
    x, y, lon, lat = cell_centres(ref)
    tab = pd.DataFrame({"window": name, "row": np.repeat(np.arange(ref.grid.height), ref.grid.width), "col": np.tile(np.arange(ref.grid.width), ref.grid.height),
                        "x_m": x.ravel(), "y_m": y.ravel(), "lon": lon.ravel(), "lat": lat.ravel()})
    for k, a in {**feats, **lr}.items():
        tab[k] = a.ravel()
    tab = tab[tab.inside_aoi == 1].drop(columns="inside_aoi")
    tab.to_parquet(out / "cells.parquet", index=False)
    (out / "static_factors.json").write_text(json.dumps({"grid": ref.to_dict(), "bands": meta}, indent=1, default=str), encoding="utf-8")
    quality = {k: {"valid_frac_inside": float(np.isfinite(a[inside]).mean()) if inside.any() else None,
                   "min": float(np.nanmin(a[inside])) if np.isfinite(a[inside]).any() else None,
                   "max": float(np.nanmax(a[inside])) if np.isfinite(a[inside]).any() else None} for k, a in feats.items() if k != "inside_aoi"}
    summary = {
        "window": name, "bbox_wsen": list(bbox), "grid": ref.to_dict(), "cells_total": int(ref.grid.width * ref.grid.height), "cells_inside": int(inside.sum()),
        "warnings": warns + [f"DEM tiles missing from the catalog/download (treated as nodata): {missing}"] * bool(missing),
        "dem_tiles_missing": missing, "worldcover_tiles": lc_tiles, "lithology": lith_report, "imerg_files": series["n_files"],
        "events_in_window": int(len(ev)), "events_strict_all_years": int(ev.strict_all_years.sum()), "events_strict_in_period": int(ev.strict_in_period.sum()),
        "events_ambiguous_strict": int((ev.strict_all_years & ev.label_ambiguous).sum()),
        "events_strict_outside_grid": int((ev.strict_all_years & ~ev.in_grid).sum()),
        "label_cells_with_point_strict_all": int((lr["label_point_count_strict_all_years"] > 0).sum()),
        "label_point_count_strict_all_max": float(lr["label_point_count_strict_all_years"].max()), "quality": quality,
        "outputs": {p.name: sha256_file(p) for p in (sf, lg, out / "events.parquet", out / "cells.parquet", out / "imerg_monthly.npz")},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    return summary
