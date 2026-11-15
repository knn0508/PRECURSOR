"""M3b: round 2 factors on the SAME 5 km (and 10 km sensitivity) reference grids as M3 (ML track, ADR-0009).

Adds: distance to rivers and Quaternary faults (metric CRS), SoilGrids soil properties (area-averaged), VIIRS NDVI climatology
(2013-2017). No modelling, no selection. Rules that define the factors are fixed here, outcome-blind (before any label is looked at):
  * rivers: HydroRIVERS v10 NA reaches. 'all' = every reach (upstream area >= ~10 km2); 'major' = UPLAND_SKM >= 1000 km2.
  * faults: Qfaults_US_Database traces. 'all' = every trace; 'young' = age in {historic, latest Quaternary, late Quaternary}.
    The CA offshore layer is NOT used (offshore cells are an M4 question).
  * distance: lines rasterised at 250 m in the window CRS (+50 km margin), Euclidean distance transform (error < ~180 m), then the
    MEAN and the MINIMUM over each analysis cell.
  * NDVI: monthly 1 km VNP13A3 v002 NDVI x 0.0001, kept where pixel_reliability in {0,1,2} and -1 <= NDVI <= 1; statistics over
    the 60 months 2013-01..2017-12; pixels with fewer than 12 valid months are NaN.
"""
from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from precursor_ml import m3  # noqa: F401  (imports the backend path hook and geo_env first)
from precursor_ml.m3 import RAW, ROOT, aggregate, cell_centres, inside_mask, make_grid, sha256_file, write_multiband  # noqa: E402

import geopandas as gpd  # noqa: E402
import rasterio  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.transform import Affine  # noqa: E402
from scipy.ndimage import distance_transform_edt  # noqa: E402

HYDRO = RAW / "hydrorivers/HydroRIVERS_v10_na_shp.zip"
QFAULT = RAW / "faults/Qfaults_GIS.zip"
SOIL_PLAN = ROOT / "ml/reports/m2b_probe/soil_plan.json"
R2_MANIFEST = RAW / "manifest_round2.json"
NDVI_CACHE = ROOT / "data/ml/interim/m3b/ndvi_climatology.npz"
IGH = "+proj=igh +ellps=WGS84 +units=m +no_defs"
SINU = "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +R=6371007.181 +units=m +no_defs"
TILE_M = 1111950.5196666666
SOIL_SCALE = {"clay": 10.0, "sand": 10.0, "silt": 10.0, "cfvo": 10.0}  # SoilGrids mapped units -> % (g/kg /10, volume permille /10)
SOIL_UNIT = {"clay": "%", "sand": "%", "silt": "%", "cfvo": "vol%"}
DEPTHS = {"0-5cm": 5.0, "5-15cm": 10.0, "15-30cm": 15.0}  # thickness (cm) used for the 0-30 cm weighted mean
YOUNG = {"historic", "latest Quaternary", "late Quaternary", "Late Quaternary"}
MAJOR_UPLAND_SKM = 1000.0


# ----------------------------------------------------------------------------------------------- distances
def read_rivers(bbox, margin=0.8):
    w, s, e, n = bbox
    g = gpd.read_file(f"zip://{HYDRO.as_posix()}!HydroRIVERS_v10_na_shp/HydroRIVERS_v10_na.shp", bbox=(w - margin, s - margin, e + margin, n + margin), columns=["UPLAND_SKM"])
    return g


def read_faults(bbox, margin=0.8):
    w, s, e, n = bbox
    return gpd.read_file(f"zip://{QFAULT.as_posix()}!SHP/Qfaults_US_Database.shp", bbox=(w - margin, s - margin, e + margin, n + margin), columns=["age", "class"])


def distance_stats(lines, ref, res=250.0, margin_m=50_000.0):
    """Mean and minimum distance (m) from the pixels of each analysis cell to the nearest line. `lines` is a GeoSeries in the grid CRS."""
    g = ref.grid
    cell = ref.resolution_m
    k, off = int(round(cell / res)), int(round(margin_m / res))
    h, w = g.height * k + 2 * off, g.width * k + 2 * off
    tr = Affine(res, 0, g.transform.c - margin_m, 0, -res, g.transform.f + margin_m)
    geoms = [x for x in lines if x is not None and not x.is_empty]
    nan = np.full((g.height, g.width), np.nan, np.float32)
    if not geoms:
        return nan, nan.copy(), 0
    mask = rasterize([(x, 1) for x in geoms], out_shape=(h, w), transform=tr, fill=0, dtype="uint8", all_touched=True)
    if not mask.any():
        return nan, nan.copy(), len(geoms)
    dist = distance_transform_edt(mask == 0) * res
    sub = dist[off:off + g.height * k, off:off + g.width * k].reshape(g.height, k, g.width, k)
    return sub.mean(axis=(1, 3)).astype(np.float32), sub.min(axis=(1, 3)).astype(np.float32), len(geoms)


def distance_features(bbox, ref):
    f, meta, counts = {}, {}, {}
    rv = read_rivers(bbox).to_crs(ref.grid.crs)
    fl = read_faults(bbox).to_crs(ref.grid.crs)
    sets = {"river_all": rv.geometry, "river_major": rv[rv.UPLAND_SKM >= MAJOR_UPLAND_SKM].geometry,
            "fault_all": fl.geometry, "fault_young": fl[fl["age"].isin(YOUNG)].geometry}
    src = {"river": "HydroRIVERS v10 NA (about 500 m positional accuracy)", "fault": "USGS Quaternary Fault and Fold Database (mapped traces, incomplete)"}
    for name, geoms in sets.items():
        mean, mn, n = distance_stats(geoms, ref)
        counts[name] = n
        for stat, arr in (("mean", mean), ("min", mn)):
            key = f"dist_{name}_{stat}_m"
            f[key] = arr
            meta[key] = {"unit": "m", "description": f"{stat} distance from the cell's 250 m pixels to the nearest {name.replace('_', ' ')} line", "aggregation": "Euclidean distance transform at 250 m, then cell mean/min",
                         "source": src[name.split("_")[0]]}
    return f, meta, counts


# ----------------------------------------------------------------------------------------------- soil
def soil_layer_mosaic(plan, layer, window):
    files = [f for f in plan["files"] if f["layer"] == layer and window in f["windows"]]
    if not files:
        return None, None
    x0, y0 = math.floor(min(f["x"] for f in files)), math.floor(min(f["y"] for f in files))
    x1, y1 = math.ceil(max(f["x"] + f["w"] for f in files)), math.ceil(max(f["y"] + f["h"] for f in files))
    mosaic = np.full((y1 - y0, x1 - x0), -32768, np.int16)
    for f in files:
        p = RAW / "soilgrids" / f["prop"] / f["depth"] / (Path(f["rel"]).stem + f"__{layer}.tif")
        with rasterio.open(p) as d:
            a = d.read(1)
        r, c = int(round(f["y"])) - y0, int(round(f["x"])) - x0
        sub = mosaic[r:r + a.shape[0], c:c + a.shape[1]]
        ok = a != -32768
        sub[ok[:sub.shape[0], :sub.shape[1]]] = a[:sub.shape[0], :sub.shape[1]][ok[:sub.shape[0], :sub.shape[1]]]
    gt = plan["geotransform"]
    return mosaic, Affine(gt[1], 0, gt[0] + x0 * gt[1], 0, gt[5], gt[3] + y0 * gt[5])


def soil_features(window, ref, plan=None):
    plan = plan or json.loads(SOIL_PLAN.read_text())
    layers = sorted({f["layer"] for f in plan["files"]})
    f, meta, cover = {}, {}, None
    for layer in layers:
        prop, depth = layer.split("_", 1)
        mosaic, tr = soil_layer_mosaic(plan, layer, window)
        if mosaic is None:
            continue
        avg = aggregate(mosaic, tr, IGH, ref, Resampling.average, -32768)
        if cover is None:
            cover = aggregate((mosaic != -32768).astype(np.float32), tr, IGH, ref, Resampling.average, None)
        key = f"soil_{prop}_{depth.replace('-', '_').replace('cm', '')}"
        f[key] = (avg / SOIL_SCALE[prop]).astype(np.float32)
        meta[key] = {"unit": SOIL_UNIT[prop], "description": f"SoilGrids 2.0 {prop} mean, {depth}", "aggregation": "250 m area average (nodata ignored), mapped units / documented factor",
                     "source": "ISRIC SoilGrids 2.0, modelled (uncertain in mountains and forests)"}
    for prop in sorted({k.split("_")[1] for k in f}):
        parts = [(f.get(f"soil_{prop}_{d.replace('-', '_').replace('cm', '')}"), w) for d, w in DEPTHS.items()]
        if all(a is not None for a, _ in parts):
            num = sum(a * w for a, w in parts)
            f[f"soil_{prop}_0_30"] = (num / sum(w for _, w in parts)).astype(np.float32)
            meta[f"soil_{prop}_0_30"] = {"unit": SOIL_UNIT[prop], "description": f"{prop} 0-30 cm, thickness-weighted mean of the 0-5, 5-15, 15-30 cm layers (weights 5/10/15)",
                                         "aggregation": "derived from the aggregated layers", "source": "ISRIC SoilGrids 2.0"}
    if cover is not None:
        f["soil_cover"] = cover
        meta["soil_cover"] = {"unit": "fraction", "description": "fraction of the cell with SoilGrids data (water, urban and ice are no data)", "aggregation": "area average of validity", "source": "ISRIC SoilGrids 2.0"}
    return f, meta


# ----------------------------------------------------------------------------------------------- NDVI
def tile_origin(h, v):
    return -20015109.354 + h * TILE_M, 10007554.677 - v * TILE_M


def read_ndvi_month(path):
    base = f'HDF5:"{Path(path).as_posix()}"://HDFEOS/GRIDS/VIIRS_Grid_monthly_VI_1km/Data_Fields/'
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
        with rasterio.open(base + "1_km_monthly_NDVI") as d:
            nd = d.read(1)
        with rasterio.open(base + "1_km_monthly_pixel_reliability") as d:
            rel = d.read(1)
    ok = (rel >= 0) & (rel <= 2) & (nd >= -10000) & (nd <= 10000)
    return np.where(ok, nd.astype(np.float32) * 1e-4, np.nan).astype(np.float32)


def build_ndvi_climatology(cache=NDVI_CACHE):
    man = json.loads(R2_MANIFEST.read_text())
    items = [(k, v) for k, v in man.items() if k.startswith("ndvi_viirs/")]
    tiles = sorted({(int(v["tile"][1:3]), int(v["tile"][4:6])) for _, v in items})
    hs, vs = [t[0] for t in tiles], [t[1] for t in tiles]
    h0, v0 = min(hs), min(vs)
    nrow, ncol = (max(vs) - v0 + 1) * 1200, (max(hs) - h0 + 1) * 1200
    ssum = np.zeros((12, nrow, ncol), np.float32)
    scnt = np.zeros((12, nrow, ncol), np.uint8)
    months = set()
    for k, v in sorted(items):
        h, vv = int(v["tile"][1:3]), int(v["tile"][4:6])
        m = int(v["start"][5:7])
        y = int(v["start"][:4])
        months.add((y, m))
        a = read_ndvi_month(RAW / k)
        r, c = (vv - v0) * 1200, (h - h0) * 1200
        ok = np.isfinite(a)
        ssum[m - 1, r:r + 1200, c:c + 1200] += np.where(ok, a, 0)
        scnt[m - 1, r:r + 1200, c:c + 1200] += ok
    x_ul, y_ul = tile_origin(h0, v0)
    n_months = len(months)
    cnt = scnt.sum(0).astype(np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(cnt >= 12, ssum.sum(0) / cnt, np.nan)
        ja_c, jf_c = scnt[6] + scnt[7], scnt[0] + scnt[1]
        julaug = np.where(ja_c >= 4, (ssum[6] + ssum[7]) / ja_c, np.nan)
        janfeb = np.where(jf_c >= 4, (ssum[0] + ssum[1]) / jf_c, np.nan)
        clim = np.where(scnt >= 3, ssum / scnt, np.nan)
        with warnings.catch_warnings():  # all-NaN slices (water) are expected and stay NaN
            warnings.simplefilter("ignore", RuntimeWarning)
            amp = np.where(np.isfinite(clim).sum(0) >= 8, np.nanmax(clim, 0) - np.nanmin(clim, 0), np.nan)
    out = {"ndvi_mean": mean, "ndvi_julaug": julaug, "ndvi_janfeb": janfeb, "ndvi_amp": amp, "ndvi_valid_month_share": np.where(cnt >= 12, cnt / n_months, np.nan)}
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, x_ul=x_ul, y_ul=y_ul, months=n_months, tiles=np.array(tiles), **{k: v.astype(np.float32) for k, v in out.items()})
    return cache


def ndvi_features(ref, cache=NDVI_CACHE):
    z = np.load(cache)
    tr = Affine(TILE_M / 1200, 0, float(z["x_ul"]), 0, -TILE_M / 1200, float(z["y_ul"]))
    desc = {"ndvi_mean": "mean of valid monthly NDVI, 2013-01..2017-12", "ndvi_julaug": "mean July-August NDVI (peak season in the windows' climates)",
            "ndvi_janfeb": "mean January-February NDVI", "ndvi_amp": "seasonal amplitude: wettest-greenest minus lowest monthly climatology",
            "ndvi_valid_month_share": "share of the 60 months with a reliable observation (reliability 0-2)"}
    f, meta = {}, {}
    for k, d in desc.items():
        f[k] = aggregate(z[k], tr, SINU, ref, Resampling.average, np.nan)
        meta[k] = {"unit": "NDVI" if k != "ndvi_valid_month_share" else "fraction", "description": d, "aggregation": "1 km sinusoidal pixels area-averaged to the cell (NaN ignored)",
                   "source": "VIIRS VNP13A3 v002 (2013-2017 only; covers 345 of 667 strict events; land cover is 2021)"}
    return f, meta


# ----------------------------------------------------------------------------------------------- one window
def run_window_r2(name, bbox, cfg, out_root, plan=None):
    out = Path(out_root) / name
    ref = make_grid(bbox, float(cfg["grid"]["cell_m"]))
    inside = inside_mask(ref, bbox)
    feats, meta, info = {}, {}, {}
    d, dm, counts = distance_features(bbox, ref)
    feats.update(d)
    meta.update(dm)
    info["line_counts_in_extent"] = counts
    s, sm = soil_features(name, ref, plan)
    feats.update(s)
    meta.update(sm)
    nd, ndm = ndvi_features(ref)
    feats.update(nd)
    meta.update(ndm)
    for k in feats:
        feats[k] = np.where(inside, feats[k], np.nan).astype(np.float32)
    tif = write_multiband(out / "static_factors_r2.tif", feats, ref, {"round": 2, "config_sha256": cfg["_sha256"]})
    x, y, lon, lat = cell_centres(ref)
    tab = pd.DataFrame({"window": name, "row": np.repeat(np.arange(ref.grid.height), ref.grid.width), "col": np.tile(np.arange(ref.grid.width), ref.grid.height)})
    for k, a in feats.items():
        tab[k] = a.ravel()
    tab["_inside"] = inside.ravel()
    tab = tab[tab._inside].drop(columns="_inside")
    tab.to_parquet(out / "cells_r2.parquet", index=False)
    quality = {k: {"valid_frac_inside": float(np.isfinite(a[inside]).mean()), "min": float(np.nanmin(a[inside])) if np.isfinite(a[inside]).any() else None,
                   "max": float(np.nanmax(a[inside])) if np.isfinite(a[inside]).any() else None} for k, a in feats.items()}
    summary = {"window": name, "cell_m": ref.resolution_m, "bands": meta, "quality": quality, **info,
               "outputs": {p.name: sha256_file(p) for p in (tif, out / "cells_r2.parquet")}}
    (out / "summary_r2.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary
