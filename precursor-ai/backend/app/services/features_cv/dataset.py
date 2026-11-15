"""Leakage-safe labelled SAMPLE DATASET (a data product, not ML): landslide-event samples plus BACKGROUND samples.

* EVENT samples come from the catalog; events with unusable coordinates, date or location accuracy are EXCLUDED and listed
  with a reason (never repaired, never guessed).
* BACKGROUND samples are unlabelled places, NOT proven stable: the catalog is incomplete and biased toward reported,
  accessible, populated places. They lie in the same grid, outside max(2 x accuracy radius, minimum buffer) of EVERY catalog
  event (metric CRS), only on valid pixels, stratified by terrain bins, with a recorded seed and ratio.
* Static features are sampled per point (nearest cell, no interpolation). Per-point DYNAMIC features are deferred to Phase 6:
  their columns are reserved and NOT_AVAILABLE; event_date and the lead-time anchors are stored so Phase 6 can fill them.
* Splits: spatial-block (whole blocks per split + a gap) and temporal (cut-off date). `check_leakage` proves the guarantees.
No column or key here is a score, probability, class or prediction.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from affine import Affine
from pyproj import Transformer
from scipy.spatial import cKDTree

from app.services.features_cv.types import (
    DATASET_SCHEMA_VERSION, FeatureError, forbidden_names)

LEAD_TIME_DAYS = (1, 3, 7, 14, 30)
DYNAMIC_KINDS = ("rainfall", "smap_soil_moisture", "insar_velocity")
DYNAMIC_REASON = "per-point dynamic features deferred to Phase 6"

CAVEATS = [
    "INVENTORY BIAS: the NASA Global Landslide Catalog is a one-time export (last event dated 2017-09-28), media/report-derived, incomplete and biased toward reported, accessible, populated places. Absence of an event proves nothing.",
    "BACKGROUND samples are unlabelled places, not proven stable ground; they must not be treated as confirmed non-landslide examples.",
    "Class balance is set by the chosen background ratio, not by nature; the real event rate is unknown.",
    "location_accuracy parsing rules are NOT_VERIFIED against a real catalog file (only the documented lookup is implemented).",
    "Per-point dynamic features (rainfall, soil moisture, InSAR velocity at lead times) are deferred to Phase 6 and are NOT_AVAILABLE.",
    "All data used so far is synthetic unless the manifest says otherwise; nothing here is real-data validated.",
]
ACCURACY_RULES = {
    "unknown / empty / 'n/a'": "radius UNKNOWN -> event EXCLUDED (reason accuracy_unknown)",
    "'exact'": "radius 0 m (the source states an exact location; its true positional error is NOT_VERIFIED); the minimum buffer still applies",
    "'<number> km' / '<number> m'": "radius in metres = number x 1000 (km) or x 1 (m)",
    "anything else": "unparseable -> event EXCLUDED (reason accuracy_unparseable)",
}
_ACC = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(km|m)\s*$", re.IGNORECASE)


@dataclass
class Accuracy:
    radius_m: float | None
    rule: str


def parse_location_accuracy(raw: Any) -> Accuracy:
    if raw is None:
        return Accuracy(None, "unknown")
    s = str(raw).strip().lower()
    if s in ("", "unknown", "n/a", "na", "none", "null"):
        return Accuracy(None, "unknown")
    if s == "exact":
        return Accuracy(0.0, "exact_stated")
    m = _ACC.match(s)
    if m:
        return Accuracy(float(m.group(1)) * (1000.0 if m.group(2).lower() == "km" else 1.0), "numeric")
    return Accuracy(None, "unparseable")


def _utc(d: Any) -> datetime | None:
    if isinstance(d, str):
        try:
            d = datetime.fromisoformat(d)
        except ValueError:
            return None
    if not isinstance(d, datetime):
        return None
    return d.replace(tzinfo=UTC) if d.tzinfo is None else d.astimezone(UTC)


@dataclass
class DatasetParams:
    background_ratio: float = 1.0  # background samples per event sample
    seed: int = 0
    min_buffer_m: float | None = None  # default: 2 grid cells
    unknown_buffer_m: float | None = None  # exclusion buffer around events with unknown accuracy; default = largest known buffer
    max_accuracy_radius_m: float | None = None  # events less precisely located than this are excluded (None = no cap)
    n_strata: int = 5  # quantile bins of slope
    block_m: float | None = None  # default: a fifth of the shorter grid side, at least 10 cells
    test_fraction: float = 0.2
    gap_m: float | None = None  # default: the largest event buffer
    temporal_cutoff: datetime | str | None = None  # default: chosen from the event-date quantile
    lead_time_days: tuple[int, ...] = LEAD_TIME_DAYS
    candidate_chunk: int = 4096


@dataclass
class DatasetResult:
    samples: pd.DataFrame
    excluded: list[dict[str, Any]]
    info: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def _pixel_xy(tf: Affine, rows: np.ndarray, cols: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return tf.c + (cols + 0.5) * tf.a, tf.f + (rows + 0.5) * tf.e


def _alloc(total: int, weights: np.ndarray) -> np.ndarray:
    """Largest-remainder allocation of `total` over strata in proportion to `weights` (deterministic)."""
    w = weights.astype(np.float64)
    if total <= 0 or w.sum() == 0:
        return np.zeros(len(w), dtype=int)
    raw = total * w / w.sum()
    base = np.floor(raw).astype(int)
    rem = total - int(base.sum())
    order = np.lexsort((np.arange(len(w)), -(raw - base)))
    base[order[:rem]] += 1
    return base


def prepare_events(events: list[dict[str, Any]], grid: dict[str, Any], valid: np.ndarray, p: DatasetParams) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """-> (positives, excluded, all_located). `all_located` = every event with usable coordinates in grid metres (their buffers
    still keep background samples away even when the event itself is excluded)."""
    tf = Affine(*grid["transform"][:6])
    tr = Transformer.from_crs(4326, grid["crs"], always_xy=True)
    pos, exc, located = [], [], []
    for e in events:
        eid = str(e.get("id", e.get("external_event_id", "")))
        lon, lat = e.get("lon"), e.get("lat")
        d = _utc(e.get("event_date"))
        base = {"event_id": eid, "lon": lon, "lat": lat, "event_date": d.isoformat() if d else None}
        ok_xy = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (lon, lat)) and -180 <= lon <= 180 and -90 <= lat <= 90
        if not ok_xy:
            exc.append({**base, "reason": "no_coordinates", "detail": "missing or invalid lon/lat"})
            continue
        x, y = tr.transform(float(lon), float(lat))
        acc = parse_location_accuracy((e.get("original_attributes") or {}).get("location_accuracy", e.get("location_accuracy")))
        rec = {**base, "x": x, "y": y, "radius_m": acc.radius_m, "accuracy_rule": acc.rule}
        located.append(rec)
        if d is None:
            exc.append({**base, "reason": "no_date", "detail": "event date missing or unparseable (lead-time anchors need it)"})
            continue
        if acc.radius_m is None:
            exc.append({**base, "reason": f"accuracy_{acc.rule}", "detail": f"location_accuracy {(e.get('original_attributes') or {}).get('location_accuracy')!r} gives no radius"})
            continue
        if p.max_accuracy_radius_m is not None and acc.radius_m > p.max_accuracy_radius_m:
            exc.append({**base, "reason": "accuracy_exceeds_max", "detail": f"radius {acc.radius_m:g} m > {p.max_accuracy_radius_m:g} m"})
            continue
        inv = ~tf
        col, row = inv.a * x + inv.b * y + inv.c, inv.d * x + inv.e * y + inv.f
        r, c = int(math.floor(row)), int(math.floor(col))
        if not (0 <= r < valid.shape[0] and 0 <= c < valid.shape[1]):
            exc.append({**base, "reason": "outside_grid", "detail": "event is outside the reference grid"})
            continue
        if not valid[r, c]:
            exc.append({**base, "reason": "on_nodata", "detail": "event lies on a missing/invalid pixel"})
            continue
        pos.append({**rec, "row": r, "col": c})
    return pos, exc, located


def check_leakage(df: pd.DataFrame, *, gap_m: float, cutoff: datetime | None) -> dict[str, Any]:
    """Proves the split guarantees from the table alone. `ok` is True only when every list in `violations` is empty."""
    v: dict[str, Any] = {"spatial_gap": [], "shared_blocks": [], "temporal": [], "background_buffer": [], "duplicate_ids": []}
    if df["sample_id"].duplicated().any():
        v["duplicate_ids"] = df.loc[df["sample_id"].duplicated(), "sample_id"].tolist()
    tr, te = df[df["split_spatial"] == "train"], df[df["split_spatial"] == "test"]
    min_d = None
    if len(tr) and len(te):
        d, _ = cKDTree(te[["x_m", "y_m"]].to_numpy()).query(tr[["x_m", "y_m"]].to_numpy(), k=1)
        min_d = float(d.min())
        if (d < gap_m).any():
            v["spatial_gap"] = tr.loc[d < gap_m, "sample_id"].tolist()
    shared = set(tr["block_id"]) & set(te["block_id"])
    v["shared_blocks"] = sorted(shared)
    if cutoff is not None:
        ev = df[df["is_event"] == 1]
        cut = pd.Timestamp(cutoff)
        dates = pd.to_datetime(ev["event_date"], utc=True)
        bad_tr = ev[(ev["split_temporal"] == "train") & (dates > cut)]
        bad_te = ev[(ev["split_temporal"] == "test") & (dates <= cut)]
        v["temporal"] = bad_tr["sample_id"].tolist() + bad_te["sample_id"].tolist()
    ev, bg = df[df["is_event"] == 1], df[df["is_event"] == 0]
    if len(ev) and len(bg):
        tree = cKDTree(bg[["x_m", "y_m"]].to_numpy())
        for _, r in ev.iterrows():
            hit = tree.query_ball_point([r["x_m"], r["y_m"]], r["buffer_m"] - 1e-6)
            v["background_buffer"] += [bg.iloc[i]["sample_id"] for i in hit]
    return {"ok": not any(v.values()), "violations": v, "min_train_test_distance_m": min_d, "gap_m": gap_m,
            "checked": {"train": int(len(tr)), "test": int(len(te))}}


def build_samples(events: list[dict[str, Any]], grid: dict[str, Any], static: dict[str, np.ndarray], strat: np.ndarray | None, valid: np.ndarray,
                  p: DatasetParams | None = None) -> DatasetResult:
    p = p or DatasetParams()
    h, w = valid.shape
    if not (p.background_ratio > 0 and math.isfinite(p.background_ratio)):
        raise FeatureError("background_ratio must be > 0")
    if not 0 < p.test_fraction < 1:
        raise FeatureError("test_fraction must be in (0, 1)")
    if p.n_strata < 1:
        raise FeatureError("n_strata must be >= 1")
    for k, a in static.items():
        if a.shape != valid.shape:
            raise FeatureError(f"static array {k!r} has a different shape; no silent resampling")
    res = float(grid["resolution_m"])
    tf = Affine(*grid["transform"][:6])
    min_buf = p.min_buffer_m if p.min_buffer_m is not None else 2 * res
    pos, excluded, located = prepare_events(events, grid, valid, p)
    if not pos:
        raise FeatureError("no usable event samples: every event was excluded (see reasons) or none were provided")
    warns: list[str] = []
    for r in located:
        r["buffer_m"] = max(2 * r["radius_m"], min_buf) if r["radius_m"] is not None else None
    known = [r["buffer_m"] for r in located if r["buffer_m"] is not None]
    unk_buf = p.unknown_buffer_m if p.unknown_buffer_m is not None else max(known + [min_buf])
    for r in located:
        if r["buffer_m"] is None:
            r["buffer_m"] = unk_buf
    for r in pos:
        r["buffer_m"] = max(2 * r["radius_m"], min_buf)
    ev_xy = np.array([[r["x"], r["y"]] for r in located])
    ev_buf = np.array([r["buffer_m"] for r in located])

    # --- strata (quantile bins of the stratification raster over VALID pixels) ---
    rng = np.random.default_rng(p.seed)
    if strat is not None and np.isfinite(strat[valid]).any():
        vals = strat[valid & np.isfinite(strat)]
        edges = np.unique(np.quantile(vals, np.linspace(0, 1, p.n_strata + 1)))
        stratum_map = np.digitize(np.where(np.isfinite(strat), strat, edges[0]), edges[1:-1]) if len(edges) > 2 else np.zeros(valid.shape, dtype=int)
        edge_list: list[float] | None = [float(e) for e in edges]
    else:
        stratum_map, edge_list = np.zeros(valid.shape, dtype=int), None
        warns.append("no terrain raster for stratification: background samples are UNSTRATIFIED (single stratum)")
    n_bg_target = int(math.ceil(p.background_ratio * len(pos)))
    strata = np.unique(stratum_map[valid])
    sizes = np.array([int(np.count_nonzero(valid & (stratum_map == s))) for s in strata])
    quota = _alloc(n_bg_target, sizes)
    bg_rows: list[tuple[int, int, int]] = []
    per_stratum = []
    for s, q, n_pix in zip(strata, quota, sizes):
        got = 0
        if q > 0:
            flat = np.flatnonzero((valid & (stratum_map == s)).ravel())
            order = rng.permutation(flat)
            for i in range(0, len(order), p.candidate_chunk):
                chunk = order[i:i + p.candidate_chunk]
                rr, cc = np.divmod(chunk, w)
                x, y = _pixel_xy(tf, rr, cc)
                d = np.hypot(x[:, None] - ev_xy[None, :, 0], y[:, None] - ev_xy[None, :, 1])
                ok = (d >= ev_buf[None, :]).all(axis=1)
                for a, b in zip(rr[ok], cc[ok]):
                    bg_rows.append((int(a), int(b), int(s)))
                    got += 1
                    if got == q:
                        break
                if got == q:
                    break
        per_stratum.append({"stratum": int(s), "valid_pixels": int(n_pix), "requested": int(q), "accepted": int(got), "shortfall": int(q - got)})
    if len(bg_rows) < n_bg_target:
        warns.append(f"only {len(bg_rows)} of {n_bg_target} requested background samples fit outside the event buffers (shortfall is reported, not filled)")

    # --- assemble the table ---
    rows = []
    for r in pos:
        rows.append({"sample_id": f"event-{r['event_id']}", "sample_type": "EVENT", "is_event": 1, "source_event_id": r["event_id"], "row": r["row"], "col": r["col"],
                     "x_m": r["x"], "y_m": r["y"], "lon": r["lon"], "lat": r["lat"], "event_date": r["event_date"], "accuracy_radius_m": r["radius_m"],
                     "buffer_m": r["buffer_m"], "terrain_stratum": int(stratum_map[r["row"], r["col"]])})
    for i, (rr, cc, s) in enumerate(bg_rows):
        x, y = _pixel_xy(tf, np.array([rr]), np.array([cc]))
        rows.append({"sample_id": f"background-{i:06d}", "sample_type": "BACKGROUND", "is_event": 0, "source_event_id": None, "row": rr, "col": cc, "x_m": float(x[0]), "y_m": float(y[0]),
                     "lon": None, "lat": None, "event_date": None, "accuracy_radius_m": None, "buffer_m": None, "terrain_stratum": s})
    df = pd.DataFrame(rows)
    if len(bg_rows):
        inv = Transformer.from_crs(grid["crs"], 4326, always_xy=True)
        m = df["is_event"] == 0
        lo, la = inv.transform(df.loc[m, "x_m"].to_numpy(), df.loc[m, "y_m"].to_numpy())
        df.loc[m, "lon"], df.loc[m, "lat"] = lo, la
    for k in sorted(static):
        df[f"static__{k}"] = static[k][df["row"].to_numpy(), df["col"].to_numpy()].astype(np.float32)
    for k in p.lead_time_days:
        ev_dates = pd.to_datetime(df["event_date"], utc=True)
        df[f"anchor_t_minus_{k}d"] = (ev_dates - timedelta(days=k)).dt.strftime("%Y-%m-%d").where(df["is_event"] == 1)
    for kind in DYNAMIC_KINDS:
        for k in p.lead_time_days:
            df[f"dyn__{kind}__t_minus_{k}d"] = np.float32(np.nan)

    # --- spatial-block split ---
    block_m = p.block_m if p.block_m is not None else max(10 * res, min(h, w) * res / 5)
    x0, y0 = tf.c, tf.f
    bx = np.floor((df["x_m"] - x0) / block_m).astype(int)
    by = np.floor((y0 - df["y_m"]) / block_m).astype(int)
    df["block_id"] = [f"{a}_{b}" for a, b in zip(bx, by)]
    blocks = sorted(df["block_id"].unique())
    gap_m = p.gap_m if p.gap_m is not None else float(max(r["buffer_m"] for r in pos))
    if len(blocks) < 2:
        warns.append("fewer than 2 spatial blocks hold samples: spatial split is impossible (all samples are train)")
        df["split_spatial"] = "train"
    else:
        n_test = min(len(blocks) - 1, max(1, round(p.test_fraction * len(blocks))))
        test_blocks = {blocks[i] for i in rng.permutation(len(blocks))[:n_test]}
        df["split_spatial"] = np.where(df["block_id"].isin(test_blocks), "test", "train")
        te = df[df["split_spatial"] == "test"]
        tr = df[df["split_spatial"] == "train"]
        if len(te) and len(tr):
            d, _ = cKDTree(te[["x_m", "y_m"]].to_numpy()).query(tr[["x_m", "y_m"]].to_numpy(), k=1)
            df.loc[tr.index[d < gap_m], "split_spatial"] = "gap"  # train samples too close to a test sample are dropped from both
    # --- temporal split ---
    ev_dt = pd.to_datetime(df.loc[df["is_event"] == 1, "event_date"], utc=True).sort_values()
    if p.temporal_cutoff is not None:
        cut, cut_by = _utc(p.temporal_cutoff), "user"
        if cut is None:
            raise FeatureError("temporal_cutoff is not a valid date")
    else:
        idx = max(0, min(len(ev_dt) - 1, int(math.floor((1 - p.test_fraction) * len(ev_dt))) - 1))
        cut, cut_by = ev_dt.iloc[idx].to_pydatetime(), "event-date quantile"
    dts = pd.to_datetime(df["event_date"], utc=True)
    df["split_temporal"] = np.where(dts > pd.Timestamp(cut), "test", "train")
    n_ev_test = int(((df["is_event"] == 1) & (df["split_temporal"] == "test")).sum())
    p_test = n_ev_test / len(pos)
    bgm = df["is_event"] == 0
    df.loc[bgm, "split_temporal"] = np.where(rng.random(int(bgm.sum())) < p_test, "test", "train")
    if n_ev_test == 0 or n_ev_test == len(pos):
        warns.append("the temporal cut-off leaves no events on one side of the split")
    bad = forbidden_names(list(df.columns))
    if bad:
        raise FeatureError(f"table columns look like scores/predictions: {bad}")
    leak = check_leakage(df, gap_m=gap_m, cutoff=cut)
    if not leak["ok"]:
        raise FeatureError(f"leakage check failed: { {k: v for k, v in leak['violations'].items() if v} }")

    def bal(col: str) -> dict[str, Any]:
        out = {}
        for s, g in df.groupby(col):
            out[str(s)] = {"events": int((g["is_event"] == 1).sum()), "background": int((g["is_event"] == 0).sum())}
        return out

    excl_counts: dict[str, int] = {}
    for e in excluded:
        excl_counts[e["reason"]] = excl_counts.get(e["reason"], 0) + 1
    info = {
        "counts": {"events_input": len(events), "events_used": len(pos), "events_excluded": len(excluded), "excluded_by_reason": excl_counts,
                   "background_requested": n_bg_target, "background_accepted": len(bg_rows), "samples": int(len(df))},
        "class_balance": {"events": len(pos), "background": len(bg_rows), "background_ratio_requested": p.background_ratio,
                          "background_ratio_achieved": (len(bg_rows) / len(pos)) if pos else None, "spatial_split": bal("split_spatial"), "temporal_split": bal("split_temporal")},
        "sampling": {"strategy": "stratified by terrain bins, proportional to valid-pixel area", "alternative_documented_not_implemented": "uniform random background over valid pixels",
                     "seed": p.seed, "stratification_edges": edge_list, "strata": per_stratum, "min_buffer_m": min_buf, "unknown_accuracy_buffer_m": unk_buf,
                     "buffer_rule": "max(2 x accuracy radius, min_buffer_m) around every located catalog event (excluded events included)"},
        "split": {"spatial": {"block_m": block_m, "gap_m": gap_m, "test_fraction": p.test_fraction, "blocks_with_samples": len(blocks),
                              "gap_samples_dropped": int((df["split_spatial"] == "gap").sum())},
                  "temporal": {"cutoff": cut.isoformat(), "cutoff_chosen_by": cut_by,
                               "background_assignment": "undated: seeded random in the events' test proportion (no temporal meaning)",
                               "note": "spatial proximity across the temporal cut-off is allowed (same region, different time)"}},
        "leakage": leak, "lead_time_anchors_days": list(p.lead_time_days),
        "static_columns": [{"column": f"static__{k}", "missing_count": int(df[f"static__{k}"].isna().sum())} for k in sorted(static)],
        "dynamic_columns": [{"column": f"dyn__{kind}__t_minus_{k}d", "status": "NOT_AVAILABLE", "reason": DYNAMIC_REASON} for kind in DYNAMIC_KINDS for k in p.lead_time_days],
        "accuracy_parsing": {"rules": ACCURACY_RULES, "status": "NOT_VERIFIED against a real catalog file"},
    }
    return DatasetResult(df, excluded, info, warns)
