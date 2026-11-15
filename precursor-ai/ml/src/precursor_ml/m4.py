"""M4 data cleaning and quality control (ML track, ADR-0009). No modelling, no tuning, raw/M3 inputs are never modified.

Every rule produces FLAGS or an EXCLUSION REASON on a row that is kept (reversible); nothing is deleted. Rules are outcome-blind where the
user required it: the cell-exclusion criteria never see labels. See ml/reports/M4_cleaning.md.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from precursor_ml import m3, m3b  # noqa: F401  (backend path hook / geo_env first)
from precursor_ml.m3 import ROOT, sha256_file  # noqa: E402

CONFIG = ROOT / "ml/configs/m4_cleaning.yaml"
PROCESSED = ROOT / "data/ml/processed"


def load_config(path: Path = CONFIG) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg["_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return cfg


# ------------------------------------------------------------------------------------------------ NDVI georeferencing QC
def _tile_bounds_lonlat(h: int, v: int, n: int = 200):
    """Lon/lat extent of MODIS sinusoidal tile (h, v) from the grid arithmetic (edges densified)."""
    from pyproj import Transformer

    x0, y0 = m3b.tile_origin(h, v)
    t = np.linspace(0, m3b.TILE_M, n)
    xs = np.concatenate([x0 + t, np.full(n, x0 + m3b.TILE_M), x0 + t, np.full(n, x0)])
    ys = np.concatenate([np.full(n, y0), y0 - t, np.full(n, y0 - m3b.TILE_M), y0 - t])
    lon, lat = Transformer.from_crs(m3b.SINU, 4326, always_xy=True).transform(xs, ys)
    return float(np.min(lon)), float(np.max(lon)), float(np.max(lat)), float(np.min(lat))  # W, E, N, S


def ndvi_georef_qc(manifest: dict, raw: Path = m3.RAW, tol_deg: float = 0.02) -> pd.DataFrame:
    """Compare, for every NDVI granule, the tile in the file NAME, the tile numbers and bounding coordinates in the file's OWN tags,
    the arithmetic bounds of that tile, and the acquisition month in the tags against the manifest. No download.
    Tolerance 0.02 degrees (about 2 km, two 1 km pixels): the file's East bound differs from the outer-edge arithmetic by a constant ~0.01
    degrees (an edge/centre convention), while a mis-placed tile would be off by whole tiles (about 10 degrees)."""
    import rasterio
    import warnings

    rows = []
    for key, v in sorted(manifest.items()):
        if not key.startswith("ndvi_viirs/"):
            continue
        p = raw / key
        parts = Path(key).name.split(".")
        name_h, name_v = int(parts[2][1:3]), int(parts[2][4:6])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with rasterio.open(p) as d:
                t = d.tags()
        tag_h, tag_v = int(t["HORIZONTALTILENUMBER"]), int(t["VERTICALTILENUMBER"])
        w, e, n, s = _tile_bounds_lonlat(name_h, name_v)
        tw, te, tn, ts = (float(t[k]) for k in ("WestBoundingCoord", "EastBoundingCoord", "NorthBoundingCoord", "SouthBoundingCoord"))
        diffs = [abs(w - tw), abs(e - te), abs(n - tn), abs(s - ts)]
        month_ok = str(t.get("StartTime", ""))[:7] == v["start"][:7]
        ok = (tag_h, tag_v) == (name_h, name_v) and max(diffs) <= tol_deg and month_ok
        rows.append({"file": key, "tile_name": f"h{name_h:02d}v{name_v:02d}", "tile_tags": f"h{tag_h:02d}v{tag_v:02d}", "diff_west": diffs[0], "diff_east": diffs[1], "diff_north": diffs[2], "diff_south": diffs[3], "max_bbox_diff_deg": max(diffs),
                     "month_ok": month_ok, "ok": bool(ok)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ label cleaning
def _components(x, y, thr):
    """Single-linkage clusters of points closer than `thr` (small groups only)."""
    n = len(x)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(n):
        for j in range(i + 1, n):
            if math.hypot(x[i] - x[j], y[i] - y[j]) <= thr:
                parent[find(i)] = find(j)
    return [find(i) for i in range(n)]


def _dedupe(e: pd.DataFrame, other: pd.Series, L: dict):
    """GREEDY in ascending event_id: an event is kept only if it is farther than near_duplicate_m from every already-kept event of the same window and
    calendar day; otherwise it is a duplicate of the kept event within range (no chaining). Only rows free of any OTHER hard flag take part, so a rejected
    row can never remove a valid event. Returns (duplicate_of, dup_type) aligned to `e`."""
    dup_of = pd.Series(pd.NA, index=e.index, dtype=object)
    dup_type = pd.Series(pd.NA, index=e.index, dtype=object)
    day = e.date.dt.normalize()
    pool = e[e.date.notna() & ~other]
    for (_, _), g in pool.groupby(["window", day[pool.index]]):
        if len(g) < 2:
            continue
        kept = []
        for i in sorted(g.index, key=lambda k: (int(e.at[k, "event_id"]), k)):
            near = next((k for k in kept if math.hypot(e.at[i, "x_m"] - e.at[k, "x_m"], e.at[i, "y_m"] - e.at[k, "y_m"]) <= L["near_duplicate_m"]), None)
            if near is None:
                kept.append(i)
                continue
            exact = (abs(e.at[i, "latitude"] - e.at[near, "latitude"]) <= L["exact_duplicate_deg"]) and (abs(e.at[i, "longitude"] - e.at[near, "longitude"]) <= L["exact_duplicate_deg"])
            dup_of.at[i] = int(e.at[near, "event_id"])
            dup_type.at[i] = "exact" if exact else "near"
    return dup_of, dup_type


def clean_labels(ev: pd.DataFrame, cells: pd.DataFrame, cfg: dict, today: pd.Timestamp | None = None) -> pd.DataFrame:
    """Row-level label cleaning on the M3 event table. Returns ALL rows with flags, reasons and the clean sets."""
    L = cfg["labels"]
    today = today if today is not None else pd.Timestamp(cfg["as_of_date"])  # fixed in the config: runs are reproducible
    e = ev.copy().reset_index(drop=True)
    # --- date problems
    e["flag_date_missing"] = e.date.isna()
    e["flag_date_future"] = e.date > today
    e["flag_date_implausible"] = e.date.dt.year < L["min_year"]
    raw_date = e.event_date.astype(str).str.split(" ").str[0]
    first = pd.to_numeric(raw_date.str.split("/").str[0], errors="coerce")
    e["flag_date_dayfirst_suspect"] = first > 12  # a 'month' field above 12 would mean DD/MM order
    for col in ("created_date", "submitted_date"):
        rd = pd.to_datetime(e.get(col), format="%m/%d/%Y %I:%M:%S %p", errors="coerce") if col in e else pd.Series(pd.NaT, index=e.index)
        e[f"_{col}"] = rd
    rep = e[["_created_date", "_submitted_date"]].min(axis=1)
    e["flag_date_after_report"] = e.date.dt.normalize() > rep.dt.normalize()
    e["info_date_ambiguous_ddmm"] = (pd.to_numeric(raw_date.str.split("/").str[1], errors="coerce") <= 12)  # information only
    # --- coordinates
    e["flag_coords_invalid"] = (~e.latitude.between(-90, 90)) | (~e.longitude.between(-180, 180)) | e.latitude.isna() | e.longitude.isna() | ((e.latitude == 0) & (e.longitude == 0))
    key = ["window", "row", "col"]
    ce = cells[key + ["lc_valid_frac", "elev_max", "dem_cover"]].rename(columns={"lc_valid_frac": "_lcv", "elev_max": "_emax", "dem_cover": "_demc"})
    n_before = len(e)
    e = e.merge(ce, on=key, how="left", validate="many_to_one")
    assert len(e) == n_before
    e["flag_cell_missing"] = e._emax.isna() & e._lcv.isna()  # the event's cell is outside the study mask (no features exist there)
    e["flag_in_ocean_cell"] = (e._lcv.fillna(1) < 0.1) & (e._emax.fillna(1) <= 0)  # no land-cover data and no land elevation: open sea
    # --- duplicates (same window, same calendar day): see _dedupe. PRIMARY set: rain-type triggers only.
    # SENSITIVITY set (user decision 2026-11-15): unknown-trigger events included under the same rules, flagged `unknown_trigger`; never mixed into the primary set.
    rain_ok = e.landslide_trigger.isin(L["rain_triggers"])
    unknown_trig = e.landslide_trigger.eq("unknown")
    cat_bad = e.landslide_category.fillna("unknown").isin(L["bad_categories"])
    other_base = (e.flag_date_missing | e.flag_date_future | e.flag_date_implausible | e.flag_date_dayfirst_suspect | e.flag_date_after_report | e.flag_coords_invalid | e.flag_in_ocean_cell | cat_bad)
    e["duplicate_of"], e["dup_type"] = _dedupe(e, other_base | ~rain_ok, L)
    e["duplicate_of_sens"], e["dup_type_sens"] = _dedupe(e, other_base | ~(rain_ok | unknown_trig), L)
    e["flag_duplicate_sens"] = e.duplicate_of_sens.notna()
    e["unknown_trigger"] = unknown_trig
    e["flag_duplicate"] = e.duplicate_of.notna()
    # --- accuracy, type, trigger
    e["excl_accuracy_unknown"] = e.acc.eq("unknown") | e.radius_m.isna()
    e["excl_accuracy_above_strict"] = (~e.excl_accuracy_unknown) & (~e.acc.isin(L["strict_accuracy"]))
    e["excl_trigger"] = ~e.landslide_trigger.isin(L["rain_triggers"])
    e["excl_category"] = e.landslide_category.fillna("unknown").isin(L["bad_categories"])
    hard = ["flag_date_missing", "flag_date_future", "flag_date_implausible", "flag_date_dayfirst_suspect", "flag_date_after_report", "flag_coords_invalid", "flag_in_ocean_cell", "flag_duplicate",
            "excl_trigger", "excl_category"]
    reasons = []
    for _, r in e.iterrows():
        rs = [c for c in hard if bool(r[c])]
        if r.excl_trigger:
            rs = [x for x in rs if x != "excl_trigger"] + [f"trigger:{r.landslide_trigger}"]
        if r.excl_category:
            rs = [x for x in rs if x != "excl_category"] + [f"category:{r.landslide_category}"]
        if r.excl_accuracy_unknown:
            rs.append("accuracy_unknown")
        elif r.excl_accuracy_above_strict:
            rs.append(f"accuracy_above_strict:{r.acc}")
        if r.flag_cell_missing:
            rs.append("cell_outside_study_mask")
        reasons.append(";".join(rs))
    e["exclusion_reasons"] = reasons
    e["clean_usable_base"] = ~e[hard].any(axis=1)
    e["clean_strict_all_years"] = e.clean_usable_base & ~e.excl_accuracy_unknown & ~e.excl_accuracy_above_strict
    in_lo, in_hi = (pd.Timestamp(x) for x in m3.load_config()["labels"]["in_period"])  # same source as M3
    e["clean_strict_in_period"] = e.clean_strict_all_years & e.date.between(in_lo, in_hi)
    # sensitivity set (unknown triggers included, flagged `unknown_trigger`); same date/coordinate/category/accuracy rules
    e["excl_trigger_sens"] = ~(rain_ok | unknown_trig)
    hard_s = [c for c in hard if c not in ("flag_duplicate", "excl_trigger")] + ["flag_duplicate_sens", "excl_trigger_sens"]
    e["clean_usable_base_sens"] = ~e[hard_s].any(axis=1)
    e["clean_strict_all_years_sens"] = e.clean_usable_base_sens & ~e.excl_accuracy_unknown & ~e.excl_accuracy_above_strict
    e["clean_strict_in_period_sens"] = e.clean_strict_all_years_sens & e.date.between(in_lo, in_hi)
    return e.drop(columns=[c for c in e.columns if c.startswith("_")])


def clean_label_layers(ev_clean: pd.DataFrame, cell_m: float, windows: dict) -> pd.DataFrame:
    """Soft label layers of the CLEAN event sets: point count and accuracy-circle weight per cell (M3 logic, removed events no longer count)."""
    cfg3 = m3.load_config()
    cfg3["grid"]["cell_m"] = cell_m
    glc = m3.load_glc()
    parts = []
    for name, bbox in windows.items():
        ref = m3.make_grid(bbox, cell_m)
        ew, cl = m3.build_events(bbox, ref, cfg3, None, glc)
        sub = ev_clean[ev_clean.window == name].set_index("event_id")
        assert set(ew.event_id) == set(sub.index), f"event sets differ in {name}"  # M3 rebuild vs cleaned table
        ew["strict_all_years"] = ew.event_id.map(sub.clean_strict_all_years).fillna(False).astype(bool).values
        ew["strict_in_period"] = ew.event_id.map(sub.clean_strict_in_period).fillna(False).astype(bool).values
        lr = m3.label_rasters(ew, cl, ref)
        ew["strict_all_years"] = ew.event_id.map(sub.clean_strict_all_years_sens).fillna(False).astype(bool).values  # sensitivity set (unknown triggers included)
        ew["strict_in_period"] = ew.event_id.map(sub.clean_strict_in_period_sens).fillna(False).astype(bool).values
        ls = m3.label_rasters(ew, cl, ref)
        h, w = ref.grid.height, ref.grid.width
        df = pd.DataFrame({"window": name, "row": np.repeat(np.arange(h), w), "col": np.tile(np.arange(w), h),
                           "label_point_count_clean_all": lr["label_point_count_strict_all_years"].ravel(), "label_weight_clean_all": lr["label_weight_strict_all_years"].ravel(),
                           "label_point_count_clean_in_period": lr["label_point_count_strict_in_period"].ravel(), "label_weight_clean_in_period": lr["label_weight_strict_in_period"].ravel(),
                           "label_point_count_sens_all": ls["label_point_count_strict_all_years"].ravel(), "label_weight_sens_all": ls["label_weight_strict_all_years"].ravel(),
                           "label_point_count_sens_in_period": ls["label_point_count_strict_in_period"].ravel(), "label_weight_sens_in_period": ls["label_weight_strict_in_period"].ravel()})
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


# ------------------------------------------------------------------------------------------------ cell exclusion (outcome-blind)
def cell_exclusion(cells: pd.DataFrame, water_max=0.5, dem_cover_min=0.5, soil_cover_min=0.1, lc_valid_min=0.1) -> pd.DataFrame:
    """Objective criteria from feature coverage only. The function never receives label columns (a test enforces independence)."""
    c = cells
    ocean = 1.0 - c.lc_valid_frac
    water_frac = (ocean + c.lc_valid_frac * c.lc_water.fillna(0)).clip(0, 1)
    out = pd.DataFrame({"window": c.window, "row": c["row"], "col": c["col"]})
    out["water_ocean_frac"] = water_frac.values
    out["x_water_ocean"] = (water_frac > water_max).values
    out["x_no_elevation"] = (c.dem_cover.fillna(0) < dem_cover_min).values
    out["x_no_soil_no_landcover"] = ((c.soil_cover.fillna(0) < soil_cover_min) & (c.lc_valid_frac.fillna(0) < lc_valid_min)).values
    rc = [k for k in out.columns if k.startswith("x_")]
    out["excluded"] = out[rc].any(axis=1)
    out["exclusion_reason"] = out[rc].apply(lambda r: ";".join(k[2:] for k in rc if r[k]), axis=1)
    return out


# ------------------------------------------------------------------------------------------------ feature QC and missing data
RANGES = {  # feature prefix/name -> (lo, hi); physical or definitional
    "elev_": (-100, 6000), "relief": (0, 6000), "dem_cover": (0, 1), "slope_frac": (0, 1), "slope_": (0, 90), "aspect_sin": (-1, 1), "aspect_cos": (-1, 1), "aspect_resultant": (0, 1),
    "lc_": (0, 1), "lith_": (0, 1), "rain_seasonality": (0, 1.84), "rain_interannual": (0, 5), "rain_": (0, 10000), "dist_": (0, 1e6),
    "soil_cover": (0, 1), "soil_": (0, 100), "ndvi_valid": (0, 1), "ndvi_amp": (0, 2), "ndvi_": (-1, 1),
}
GROUP = [("elev_", "terrain"), ("relief", "terrain"), ("dem_cover", "terrain"), ("slope_", "terrain"), ("aspect_", "terrain"), ("lc_", "land_cover"), ("lith_", "lithology"),
         ("rain_", "rainfall_climatology"), ("dist_", "distance"), ("soil_", "soil"), ("ndvi_", "ndvi")]
POLICY = {
    "terrain": "complete; aspect NaN only where all 30 m cells are flat: keep NaN (model-native); for a logistic baseline use train-only median + missing indicator",
    "land_cover": "NaN only where the cell has no WorldCover data (ocean, mostly excluded cells): keep NaN, never fill with 0 (0 would mean 'no such class'); baselines: train-only median + indicator `lc_valid_frac`",
    "lithology": "NaN where no state geologic map covers the cell (open sea, Mexico): keep NaN; baselines: train-only median + indicator `lith_cover`",
    "rainfall_climatology": "complete: no action",
    "distance": "complete; distances over open sea are not meaningful: those cells are excluded by the water/ocean rule",
    "soil": "NaN over water and urban areas: keep NaN (model-native); baselines: train-only median + indicator `soil_cover`; bulk density is MISSING_FACTOR",
    "ndvi": "NaN where fewer than 12 reliable months: keep NaN (model-native); baselines: train-only median + indicator `ndvi_valid_month_share`",
    "event_prior_rain": "NaN for events before the IMERG record (before 2001-07): keep NaN; never impute",
    "labels": "NEVER imputed",
}


def feature_columns(cells: pd.DataFrame):
    return [c for c in cells.columns if any(c.startswith(p) for p, _ in GROUP)]


def group_of(col: str) -> str:
    return next(g for p, g in GROUP if col.startswith(p))


def range_for(col: str):
    return next(v for k, v in RANGES.items() if col.startswith(k))


def feature_qc(cells: pd.DataFrame, robust_z: float = 6.0) -> dict:
    feats = feature_columns(cells)
    out = {}
    for f in feats:
        s = cells[f]
        lo, hi = range_for(f)
        v = s.dropna()
        med = float(v.median()) if len(v) else np.nan
        mad = float((v - med).abs().median()) if len(v) else np.nan
        z = (v - med).abs() / (1.4826 * mad) if mad and mad > 0 else pd.Series(0.0, index=v.index)
        out[f] = {"group": group_of(f), "n": int(len(s)), "missing": int(s.isna().sum()), "missing_frac": float(s.isna().mean()),
                  "range_allowed": [lo, hi], "range_violations": int(((v < lo) | (v > hi)).sum()), "fill_like_values": int((v <= -9000).sum()),
                  "outliers_robust_z": int((z > robust_z).sum()), "min": float(v.min()) if len(v) else None, "max": float(v.max()) if len(v) else None}
    comp = {}
    lc = [c for c in cells.columns if c.startswith("lc_") and c != "lc_valid_frac"]
    li = [c for c in cells.columns if c.startswith("lith_") and c != "lith_cover"]
    tex = cells[["soil_clay_0_30", "soil_sand_0_30", "soil_silt_0_30"]].dropna()
    comp["landcover_share_sum_max_dev"] = float((cells[lc].sum(axis=1, min_count=1).dropna() - 1).abs().max())
    comp["lithology_share_sum_max_dev"] = float((cells[li].sum(axis=1, min_count=1).dropna() - 1).abs().max())
    s = tex.sum(axis=1)
    comp["texture_sum_clay_sand_silt"] = {"min": float(s.min()), "median": float(s.median()), "max": float(s.max()), "share_within_97_103": float(s.between(97, 103).mean())}
    return {"features": out, "composition_checks": comp}


def missing_table(cells: pd.DataFrame, excluded: pd.Series) -> pd.DataFrame:
    feats = feature_columns(cells)
    rows = []
    for w, g in cells.groupby("window"):
        gk = g[~excluded.loc[g.index]]
        for f in feats:
            rows.append({"window": w, "feature": f, "group": group_of(f), "missing_all_cells": float(g[f].isna().mean()), "missing_kept_cells": float(gk[f].isna().mean()) if len(gk) else np.nan,
                         "n_all": int(len(g)), "n_kept": int(len(gk))})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ background sampling
def sample_background(cells: pd.DataFrame, events: pd.DataFrame, cell_m: float, cfg: dict, n_events_by_window: dict, seed: int) -> pd.DataFrame:
    """Candidate background cells: not excluded, the whole cell farther than max(2 x radius, min_buffer) from every buffer event (same window),
    terrain-stratified by slope quantiles, seeded ranking. `selected` marks the primary draw (ratio x clean strict events per window)."""
    B = cfg["background"]
    half = cell_m / 2
    rng = np.random.default_rng(seed)
    out = []
    for w, g in cells.groupby("window"):
        g = g[~g.excluded].copy()
        ev = events[(events.window == w) & events.usable_for_buffer]
        r = ev.radius_m.fillna(B["unknown_accuracy_radius_m"]).values
        buf = np.maximum(2 * r, B["min_buffer_cells"] * cell_m)
        ok = np.ones(len(g), bool)
        for ex, ey, b in zip(ev.x_m.values, ev.y_m.values, buf):
            dx = np.maximum(np.abs(g.x_m.values - ex) - half, 0)
            dy = np.maximum(np.abs(g.y_m.values - ey) - half, 0)
            ok &= np.hypot(dx, dy) > b
        g = g[ok & g[B["stratify_by"]].notna().values].copy()
        if g.empty:
            continue
        # contamination risk: the candidate cell touches the accuracy circle of an event whose accuracy is worse than `imprecise_radius_m`
        imp = events[(events.window == w) & (events.radius_m > B.get("imprecise_radius_m", 10000))]
        flag = np.zeros(len(g), bool)
        for ex, ey, rr in zip(imp.x_m.values, imp.y_m.values, imp.radius_m.values):
            dx = np.maximum(np.abs(g.x_m.values - ex) - half, 0)
            dy = np.maximum(np.abs(g.y_m.values - ey) - half, 0)
            flag |= np.hypot(dx, dy) <= rr
        g["background_in_imprecise_circle"] = flag
        q = np.quantile(g[B["stratify_by"]], np.linspace(0, 1, B["n_strata"] + 1))
        g["stratum"] = np.clip(np.searchsorted(q, g[B["stratify_by"]].values, side="right") - 1, 0, B["n_strata"] - 1)
        g["rank"] = -1
        for s in range(B["n_strata"]):
            idx = g.index[g.stratum == s]
            g.loc[idx, "rank"] = rng.permutation(len(idx))
        want = int(B["ratio"] * n_events_by_window.get(w, 0))
        counts = g.groupby("stratum").size()
        quota = (counts / counts.sum() * want)
        base = np.floor(quota).astype(int)
        rem = want - int(base.sum())
        for s in (quota - base).sort_values(ascending=False).index[:rem]:
            base[s] += 1
        g["selected"] = False
        short = {}
        for s, qn in base.items():
            idx = g.index[g.stratum == s]
            take = min(int(qn), len(idx))
            if take < qn:
                short[int(s)] = int(qn - take)
            g.loc[g[g.stratum == s].nsmallest(take, "rank").index, "selected"] = True
        g["shortfall"] = sum(short.values())
        out.append(g[["window", "row", "col", "x_m", "y_m", "stratum", "rank", "selected", B["stratify_by"], "shortfall", "background_in_imprecise_circle"]])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ------------------------------------------------------------------------------------------------ leakage audit
FEATURE_DATA_END = {  # last date of the data behind each feature group (None = static / not date-dependent)
    "terrain": ("2000-02-22", "NASADEM / SRTM acquisition, static"), "land_cover": ("2021-12-31", "ESA WorldCover 2021"), "lithology": (None, "geologic map, vintage NOT_VERIFIED, static"),
    "rainfall_climatology": ("2017-12-31", "IMERG monthly climatology 2002-2017"), "distance": (None, "HydroRIVERS / Qfaults, static features (dates NOT_VERIFIED)"),
    "soil": ("2020-03-31", "SoilGrids 2.0 modelled snapshot (data stream date NOT_VERIFIED)"), "ndvi": ("2017-12-31", "VIIRS NDVI 2013-2017"),
}


def check_spatial_proximity(df: pd.DataFrame, split_col: str, gap_m: float, x="x_m", y="y_m", window="window") -> dict:
    """Minimum distance between any TRAIN and any TEST point in the same window must be at least gap_m."""
    worst = np.inf
    for _, g in df.groupby(window):
        a, b = g[g[split_col] == "train"], g[g[split_col] == "test"]
        if a.empty or b.empty:
            continue
        d = np.hypot(a[x].values[:, None] - b[x].values[None, :], a[y].values[:, None] - b[y].values[None, :])
        worst = min(worst, float(d.min()))
    return {"check": "spatial_proximity", "min_train_test_distance_m": None if worst == np.inf else worst, "gap_m": gap_m, "pass": bool(worst >= gap_m)}


def check_temporal_order(ev: pd.DataFrame, split_col: str, cutoff: pd.Timestamp, date="date") -> dict:
    tr, te = ev[ev[split_col] == "train"][date], ev[ev[split_col] == "test"][date]
    ok = bool((tr.empty or tr.dt.normalize().max() <= cutoff) and (te.empty or te.dt.normalize().min() > cutoff))
    return {"check": "temporal_order", "cutoff": str(cutoff.date()), "latest_train": None if tr.empty else str(tr.max()), "earliest_test": None if te.empty else str(te.min()), "pass": ok}


def check_future_information(groups_used: list[str], cutoff: pd.Timestamp) -> dict:
    flagged = []
    for g in groups_used:
        end, note = FEATURE_DATA_END[g]
        if end is not None and pd.Timestamp(end) > cutoff:
            flagged.append({"group": g, "data_end": end, "note": note})
    return {"check": "future_information", "cutoff": str(cutoff.date()), "groups_with_data_after_cutoff": flagged,
            "status": "WARN" if flagged else "PASS",
            "note": "these are static site descriptors built from data that extend beyond the cutoff; they are acceptable only as static descriptors and must be declared in M6/M7 (not silently used in a temporal hold-out claim)"}


def check_prior_rain_strictly_before(ev: pd.DataFrame) -> dict:
    """Every event-relative rainfall feature (`rain_prev_*`: monthly rainfall of the months strictly before the event month) must be NaN for events before the record."""
    early = ev[ev.date < pd.Timestamp("2001-07-01")]
    cols = [c for c in ev.columns if c.startswith("rain_prev_")]
    ok = bool(cols) and all(early[c].isna().all() for c in cols)
    return {"check": "prior_rain_before_event_month", "columns": cols, "events_before_record": int(len(early)), "pass": ok}


def check_duplicates(df: pd.DataFrame, keys: list[str]) -> dict:
    d = int(df.duplicated(keys).sum())
    return {"check": "duplicate_rows", "keys": keys, "duplicates": d, "pass": d == 0}


KEY_COLS = {"window", "row", "col", "x_m", "y_m", "lon", "lat", "excluded", "stratum", "rank", "selected", "water_ocean_frac"}


def check_target_derived(cells: pd.DataFrame, label_cols: list[str], target: str, auc_fail: float = 0.9) -> dict:
    """Scan EVERY numeric column that is not a key or a label column (not only the prefixed feature set), so a leaking column cannot hide."""
    num = [c for c in cells.columns if pd.api.types.is_numeric_dtype(cells[c]) and pd.api.types.is_bool_dtype(cells[c]) is False and c not in KEY_COLS and not c.startswith("label_") and c != target
           and not c.startswith("x_")]
    overlap = sorted(set(num) & set(label_cols))
    y = (cells[target] > 0).astype(int)
    worst, worst_col = 0.0, None
    if 0 < y.sum() < len(y):
        for f in num:
            s_ = cells[f]
            ok = s_.notna()
            if ok.sum() < 20 or y[ok].nunique() < 2:
                continue
            r = s_[ok].rank()
            n1, n0 = int(y[ok].sum()), int((1 - y[ok]).sum())
            auc = (r[y[ok] == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
            a_ = abs(auc - 0.5) + 0.5
            if a_ > worst:
                worst, worst_col = a_, f
    return {"check": "target_derived_features", "columns_scanned": len(num), "feature_label_name_overlap": overlap, "max_single_feature_auc": round(float(worst), 3), "auc_fail_threshold": auc_fail,
            "pass": bool((not overlap) and worst < auc_fail),
            "note": "audit only: the AUC is a leakage alarm (a near-perfect single column would signal a target-derived column); it is not used for any selection"}


def provisional_split(ev: pd.DataFrame, cfg: dict, seed: int):
    """AUDIT-ONLY split (spatial blocks + gap, plus a temporal cutoff) used to exercise the checks. The real splits belong to M6."""
    A = cfg["audit"]
    rng = np.random.default_rng(seed)
    e = ev.copy()
    blk = A["block_km"] * 1000
    e["block"] = (e.window + "_" + (e.x_m // blk).astype(int).astype(str) + "_" + (e.y_m // blk).astype(int).astype(str))
    blocks = sorted(e.block.unique())
    test_blocks = set(rng.choice(blocks, size=max(1, int(round(A["test_fraction"] * len(blocks)))), replace=False))
    e["split_spatial"] = np.where(e.block.isin(test_blocks), "test", "train")
    te = e[e.split_spatial == "test"]
    for w, g in e[e.split_spatial == "train"].groupby("window"):
        t = te[te.window == w]
        if t.empty:
            continue
        d = np.hypot(g.x_m.values[:, None] - t.x_m.values[None, :], g.y_m.values[:, None] - t.y_m.values[None, :]).min(axis=1)
        e.loc[g.index[d < A["gap_m"]], "split_spatial"] = "gap"
    cutoff = e.date.quantile(A["temporal_quantile"])
    cutoff = pd.Timestamp(cutoff).normalize()
    e["split_temporal"] = np.where(e.date.dt.normalize() <= cutoff, "train", "test")  # whole days: no event shares the cutoff day across splits
    return e, cutoff


# ------------------------------------------------------------------------------------------------ with/without exclusion sensitivity
def exclusion_sensitivity(cells: pd.DataFrame, events: pd.DataFrame, cfg: dict, key_features: list[str]) -> dict:
    """Descriptive comparison with and without the exclusion; thresholds from the config. No model, no label-based decision."""
    from scipy.stats import ks_2samp

    out = {}
    for thr in cfg["exclusion"]["sensitivity_water_thresholds"]:
        ex = cell_exclusion(cells, water_max=thr, dem_cover_min=cfg["exclusion"]["dem_cover_min"], soil_cover_min=cfg["exclusion"]["soil_cover_min"], lc_valid_min=cfg["exclusion"]["lc_valid_min"])
        keep = ~ex.excluded.values
        ev_in = events.drop(columns=[c for c in ("excluded",) if c in events.columns]).merge(ex[["window", "row", "col", "excluded"]], on=["window", "row", "col"], how="left")
        ev_in["excluded"] = ev_in.excluded.fillna(ev_in.flag_cell_missing)  # outside the window mask counts as excluded (no features there)
        strict = ev_in[ev_in.clean_strict_all_years]
        pos = cells.label_point_count_clean_all.fillna(0) > 0
        ks = {}
        for f in key_features:
            a, b = cells[f].dropna(), cells.loc[keep, f].dropna()
            ks[f] = round(float(ks_2samp(a, b).statistic), 3) if len(a) and len(b) else None
        out[str(thr)] = {"cells_total": int(len(cells)), "cells_kept": int(keep.sum()), "cells_excluded": int((~keep).sum()),
                         "strict_events_total": int(len(strict)), "strict_events_in_excluded_cells": int(strict.excluded.fillna(False).sum()),
                         "point_cells_total": int(pos.sum()), "point_cells_in_excluded_cells": int((pos & ~keep).sum()),
                         "point_cell_rate_all": round(float(pos.mean()), 4), "point_cell_rate_kept": round(float(pos[keep].mean()), 4),
                         "ks_statistic_all_vs_kept": ks}
    return out


# ------------------------------------------------------------------------------------------------ orchestration
def run_grid(grid_dir: Path, out_dir: Path, cell_m: float, cfg: dict, today: pd.Timestamp | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = pd.read_parquet(grid_dir / "cells_all_full.parquet")
    ev0 = pd.read_parquet(grid_dir / "events_all.parquet")
    seed = int(cfg["seed"])
    ev = clean_labels(ev0, cells, cfg, today)
    lab_cols = [c for c in cells.columns if c.startswith("label_")]
    cell_feat = cells.drop(columns=lab_cols)  # exclusion and QC see FEATURES only
    ex = cell_exclusion(cell_feat, cfg["exclusion"]["water_ocean_frac_max"], cfg["exclusion"]["dem_cover_min"], cfg["exclusion"]["soil_cover_min"], cfg["exclusion"]["lc_valid_min"])
    cc = cells.merge(ex, on=["window", "row", "col"], how="left", validate="one_to_one")
    ev = ev.merge(ex[["window", "row", "col", "excluded", "exclusion_reason"]].rename(columns={"excluded": "in_excluded_cell", "exclusion_reason": "cell_exclusion_reason"}), on=["window", "row", "col"], how="left")
    outside = ev.flag_cell_missing  # event cell centre lies outside the window polygon: no features exist there (objective: geometry only)
    ev["in_excluded_cell"] = ev.in_excluded_cell.fillna(False).astype(bool) | outside
    ev.loc[outside, "cell_exclusion_reason"] = "outside_window_mask"
    cap = cfg["background"].get("buffer_events_max_radius_m")  # null = EVERY located event shields its surroundings (user rule); a number is a recorded variant
    ev["usable_for_buffer"] = ~ev.flag_coords_invalid & (ev.radius_m.fillna(cfg["background"]["unknown_accuracy_radius_m"]).le(cap) if cap else True)
    cfg3 = m3.load_config()
    layers = clean_label_layers(ev, cell_m, cfg3["windows"])
    cc = cc.merge(layers, on=["window", "row", "col"], how="left", validate="one_to_one")
    assert cc.label_point_count_clean_all.notna().all(), "label layers do not cover every cell (grid mismatch)"
    lab_cols = [c for c in cc.columns if c.startswith("label_")]
    n_strict = ev[ev.clean_strict_all_years].groupby("window").size().to_dict()
    bg = sample_background(cc, ev, cell_m, cfg, n_strict, seed)
    # recorded LITERAL rule (for the record): EVERY located event shields 2 x its radius (blanks most of OR_WA)
    ev_v = ev.assign(usable_for_buffer=~ev.flag_coords_invalid)
    bg_v = sample_background(cc, ev_v, cell_m, cfg, n_strict, seed)
    qc = feature_qc(cell_feat, cfg["outliers"]["robust_z"])
    miss = missing_table(cell_feat, ex.excluded)
    sens = exclusion_sensitivity(cc, ev, cfg, ["slope_mean", "elev_mean", "rain_map_mm", "ndvi_mean", "soil_clay_0_30", "lc_tree_cover"])
    # leakage audit on the clean strict events and the cell table
    se, cutoff = provisional_split(ev[ev.clean_strict_all_years].reset_index(drop=True), cfg, seed)
    audit = [check_spatial_proximity(se[se.split_spatial != "gap"], "split_spatial", cfg["audit"]["gap_m"]),
             check_temporal_order(se, "split_temporal", cutoff),
             check_future_information(sorted({group_of(f) for f in feature_columns(cell_feat)}), cutoff),
             check_prior_rain_strictly_before(ev[ev.clean_strict_all_years]),
             check_duplicates(cc, ["window", "row", "col"]), check_duplicates(ev[ev.clean_strict_all_years], ["window", "event_id"]),
             check_target_derived(cc, lab_cols, "label_point_count_clean_all", cfg["audit"]["auc_fail"])]
    # write
    cc.to_parquet(out_dir / "cells_clean.parquet", index=False)
    ev.to_parquet(out_dir / "events_clean.parquet", index=False)
    ex[ex.excluded].to_parquet(out_dir / "excluded_cells.parquet", index=False)
    ev[~ev.clean_strict_all_years][["window", "event_id", "date", "acc", "landslide_trigger", "landslide_category", "exclusion_reasons", "in_excluded_cell"]].to_parquet(out_dir / "excluded_events.parquet", index=False)
    bg.to_parquet(out_dir / "background_candidates.parquet", index=False)
    bg_v.to_parquet(out_dir / "background_candidates_literal_rule.parquet", index=False)
    stale = out_dir / "background_candidates_variant_buffer_le10km.parquet"
    if stale.exists():
        stale.unlink()  # superseded name from m4-v1
    miss.to_parquet(out_dir / "missing_by_feature_region.parquet", index=False)
    (out_dir / "feature_qc.json").write_text(json.dumps(qc, indent=1))
    (out_dir / "exclusion_sensitivity.json").write_text(json.dumps(sens, indent=1))
    (out_dir / "leakage_audit.json").write_text(json.dumps({"provisional_split": "AUDIT ONLY, not the M6 split", "cutoff": str(cutoff.date()), "results": audit}, indent=1, default=str))
    (out_dir / "missing_policy.json").write_text(json.dumps({"policy_by_group": POLICY, "per_feature_group": {f: group_of(f) for f in feature_columns(cell_feat)}}, indent=1))
    steps = {}
    for col in ("flag_date_missing", "flag_date_future", "flag_date_implausible", "flag_date_dayfirst_suspect", "flag_date_after_report", "flag_coords_invalid", "flag_in_ocean_cell", "flag_cell_missing",
                "flag_duplicate", "excl_trigger", "excl_category", "excl_accuracy_unknown", "excl_accuracy_above_strict"):
        steps[col] = int(ev[col].sum())
    key_f = ["ndvi_mean", "soil_clay_0_30", "lc_tree_cover", "lith_IGN_VOLCANIC", "aspect_sin_mean", "slope_mean"]
    sev = ev[ev.clean_strict_all_years].merge(cc[["window", "row", "col"] + key_f], on=["window", "row", "col"], how="left")
    nan_events = {f: int(sev[f].isna().sum()) for f in key_f}
    steps["dup_exact"] = int((ev.dup_type == "exact").sum())
    steps["dup_near"] = int((ev.dup_type == "near").sum())
    log = {
        "rows_events_in": int(len(ev0)), "rows_events_out": int(len(ev)), "rows_cells_in": int(len(cells)), "rows_cells_out": int(len(cc)), "rule_counts": steps,
        "events_clean_usable_base": int(ev.clean_usable_base.sum()), "events_clean_strict_all_years": int(ev.clean_strict_all_years.sum()), "events_clean_strict_in_period": int(ev.clean_strict_in_period.sum()),
        "events_before_cleaning_strict_all_years": int(ev0.strict_all_years.sum()), "events_before_cleaning_strict_in_period": int(ev0.strict_in_period.sum()),
        "excluded_strict_events_by_reason": ev[ev.strict_all_years & ~ev.clean_strict_all_years].exclusion_reasons.value_counts().to_dict(),
        "clean_strict_events_in_excluded_cells": int((ev.clean_strict_all_years & ev.in_excluded_cell).sum()),
        "clean_strict_events_in_excluded_cells_by_reason": ev[ev.clean_strict_all_years & ev.in_excluded_cell].cell_exclusion_reason.value_counts().to_dict(),
        "clean_strict_events_with_nan_feature": nan_events,
        "cells_excluded": int(ex.excluded.sum()), "cells_excluded_by_reason": ex[ex.excluded].exclusion_reason.value_counts().to_dict(),
        "cells_excluded_by_window": ex[ex.excluded].groupby("window").size().to_dict(), "cells_by_window": cells.groupby("window").size().to_dict(),
        "background_candidates": int(len(bg)), "background_selected": int(bg.selected.sum()) if len(bg) else 0, "background_ratio": cfg["background"]["ratio"],
        "background_shortfall_by_window": bg.groupby("window").shortfall.first().to_dict() if len(bg) else {},
        "background_candidates_by_window": bg.groupby("window").size().to_dict() if len(bg) else {},
        "background_flagged_imprecise_circle": int(bg.background_in_imprecise_circle.sum()) if len(bg) else 0,
        "background_flagged_imprecise_circle_by_window": bg.groupby("window").background_in_imprecise_circle.sum().astype(int).to_dict() if len(bg) else {},
        "background_literal_rule": {"candidates": int(len(bg_v)), "selected": int(bg_v.selected.sum()) if len(bg_v) else 0,
                                             "candidates_by_window": bg_v.groupby("window").size().to_dict() if len(bg_v) else {},
                                             "shortfall_by_window": bg_v.groupby("window").shortfall.first().to_dict() if len(bg_v) else {}},
        "unknown_trigger_sensitivity_set": {"strict_all_years": int(ev.clean_strict_all_years_sens.sum()), "strict_in_period": int(ev.clean_strict_in_period_sens.sum()),
                                            "of_which_unknown_trigger": int((ev.clean_strict_all_years_sens & ev.unknown_trigger).sum()),
                                            "primary_events_not_in_sensitivity_set": int((ev.clean_strict_all_years & ~ev.clean_strict_all_years_sens).sum()),
                                            "point_cells": int((cc.label_point_count_sens_all > 0).sum()), "weight_sum": float(cc.label_weight_sens_all.sum())},
        "events_by_cleaned_strict_window": n_strict, "clean_point_cells": int((cc.label_point_count_clean_all > 0).sum()), "clean_weight_sum": float(cc.label_weight_clean_all.sum()), "leakage_audit": {a["check"]: a.get("pass", a.get("status")) for a in audit}}
    (out_dir / "cleaning_log.json").write_text(json.dumps(log, indent=1, default=str))
    outs = {p.name: sha256_file(p) for p in sorted(out_dir.glob("*")) if p.name != "m4_manifest.json"}
    manifest = {"stage": "M4", "dataset_version": "m4-v2", "built_utc": datetime.now(timezone.utc).isoformat(), "code_version": m3.code_version(), "config_sha256": cfg["_sha256"], "seed": seed,
                "cell_m": cell_m, "inputs": {"cells_all_full.parquet": sha256_file(grid_dir / "cells_all_full.parquet"), "events_all.parquet": sha256_file(grid_dir / "events_all.parquet")},
                "outputs_sha256": outs, "caveats": CAVEATS}
    (out_dir / "m4_manifest.json").write_text(json.dumps(manifest, indent=1))
    return log


CAVEATS = [
    "NDVI 2013-2017 covers 345 of 667 strict events; land cover is 2021; soil and the other site descriptors are static products",
    "the 667 strict events fall on 321 dates, 185 in 2017 alone (temporal structure to be examined in M5 before any temporal hold-out)",
    "background cells are PSEUDO-ABSENCES: places without a catalog record, not proven stable ground; only events with accuracy up to 10 km shield their surroundings (user decision), candidates inside the circle of a less precise event are flagged `background_in_imprecise_circle`",
    "the unknown-trigger events (371 rows) are excluded from the primary set; a separate sensitivity set includes them (columns *_sens*, flag `unknown_trigger`)",
    "inventory bias: the GLC is news-derived and biased to reported, accessible places",
    "the positive-cell rule is NOT defined here (M6); soft label weights from M3 are kept",
]
