"""M5: provisional SPATIAL HOLD-OUT, sealed before any exploration (user decision 2026-11-15). ML track, ADR-0009.

Spatial blocks of `block_m` metres in each window's UTM grid; about `frac` of the non-excluded cells (and their events) form the held-out part; a buffer gap of
`gap_m` metres separates train from held-out; cells and events inside the gap belong to neither. The split is defined by GEOMETRY (blocks), so the same blocks
apply to the 5 km and the 10 km grid and to every event set (primary, unknown-trigger sensitivity, relaxed). Block choice uses cell counts; the event share is only CHECKED against bounds (12-30%) to avoid a hold-out with a handful of events: the first draw was
accepted in every window, so no label-informed rejection occurred (see `tries` in the manifest). Distances: events (points) are separated from held-out blocks by
`gap_m`; for CELLS the gap is measured from the cell CENTRE to the block rectangle, so cell FOOTPRINTS can be closer (about gap - 0.7 x cell edge for train cells and a
further half cell for held-out cells at the block edge): M6 must re-derive the cell gap from footprints when it finalises the splits.
The held-out part is never opened, plotted or summarised during M5: EDA code reads data only through `precursor_ml.m5_data.load_train`.
M6 finalises the splits starting from this sealed hold-out.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from precursor_ml import m3
from precursor_ml.m3 import ROOT, sha256_file

SPLITS = ROOT / "data/ml/splits"
SEAL_DIR = SPLITS / "m5_provisional_holdout_v1"
PARAMS = {"seed": 20261116, "block_m": 50_000, "gap_m": 10_000, "target_cell_fraction": 0.20, "event_share_bounds": [0.12, 0.30], "max_tries": 500}


def block_ids(x, y, block_m):
    return np.floor(np.asarray(x) / block_m).astype(int), np.floor(np.asarray(y) / block_m).astype(int)


def _rect_distance(x, y, blocks, block_m):
    """Distance from points to the union of the given block rectangles (0 inside)."""
    d = np.full(len(x), np.inf)
    for bx, by in blocks:
        dx = np.maximum.reduce([bx * block_m - x, np.zeros(len(x)), x - (bx + 1) * block_m])
        dy = np.maximum.reduce([by * block_m - y, np.zeros(len(x)), y - (by + 1) * block_m])
        d = np.minimum(d, np.hypot(dx, dy))
    return d


def assign(df: pd.DataFrame, heldout: dict, block_m: float, gap_m: float) -> pd.Series:
    """'train' / 'heldout' / 'gap' for every row (columns window, x_m, y_m) from the held-out blocks of each window."""
    out = pd.Series("train", index=df.index, dtype=object)
    for w, g in df.groupby("window"):
        blocks = heldout.get(w, [])
        if not blocks:
            continue
        d = _rect_distance(g.x_m.values.astype(float), g.y_m.values.astype(float), blocks, block_m)
        out.loc[g.index] = np.where(d == 0, "heldout", np.where(d < gap_m, "gap", "train"))
    return out


def choose_heldout(cells5: pd.DataFrame, events: pd.DataFrame, params: dict = PARAMS) -> tuple[dict, dict]:
    """Seeded random block order per window, accumulate until the cell fraction is reached, accept if the event share is inside the bounds."""
    B = params["block_m"]
    rng = np.random.default_rng(params["seed"])
    chosen, info = {}, {}
    lo, hi = params["event_share_bounds"]
    for w, g in cells5[~cells5.excluded].groupby("window"):
        bx, by = block_ids(g.x_m, g.y_m, B)
        blk = pd.DataFrame({"bx": bx, "by": by})
        counts = blk.groupby(["bx", "by"]).size()
        keys = list(counts.index)
        ev = events[(events.window == w) & events.clean_strict_all_years]
        ex, ey = block_ids(ev.x_m, ev.y_m, B)
        evc = pd.Series(list(zip(ex, ey))).value_counts()
        total_cells, total_ev = int(counts.sum()), int(len(ev))
        ok = False
        for attempt in range(1, params["max_tries"] + 1):
            order = rng.permutation(len(keys))
            sel, cells_in = [], 0
            for i in order:
                sel.append(keys[i])
                cells_in += int(counts.iloc[i])
                if cells_in >= params["target_cell_fraction"] * total_cells:
                    break
            ev_in = int(sum(evc.get(k, 0) for k in sel))
            share = ev_in / total_ev if total_ev else 0.0
            if lo <= share <= hi:
                ok = True
                break
        if not ok:
            raise RuntimeError(f"no acceptable hold-out found for {w} in {params['max_tries']} tries")
        chosen[w] = [(int(a), int(b)) for a, b in sel]
        info[w] = {"blocks_total": len(keys), "blocks_heldout": len(sel), "tries": attempt, "nonexcluded_cells": total_cells, "cell_fraction": round(cells_in / total_cells, 4),
                   "event_share_check": round(share, 4)}
    return chosen, info


def seal(cells5_path: Path, cells10_path: Path, events_path: Path, out_dir: Path = SEAL_DIR, params: dict = PARAMS, supersedes: dict | None = None) -> dict:
    if (out_dir / "split_manifest.json").exists():
        raise FileExistsError(f"a seal already exists in {out_dir}; it is never overwritten (supersede it explicitly and record the pin)")
    out_dir.mkdir(parents=True, exist_ok=True)
    c5, c10, ev = pd.read_parquet(cells5_path), pd.read_parquet(cells10_path), pd.read_parquet(events_path)
    held, info = choose_heldout(c5, ev, params)
    B, G = params["block_m"], params["gap_m"]
    files = {}
    for tag, c in (("5km", c5), ("10km", c10)):
        sp = c[["window", "row", "col", "x_m", "y_m", "excluded"]].copy()
        sp["split"] = assign(sp, held, B, G)
        sp[["window", "row", "col", "split"]].to_parquet(out_dir / f"cell_split_{tag}.parquet", index=False)
        files[f"cell_split_{tag}.parquet"] = sha256_file(out_dir / f"cell_split_{tag}.parquet")
        info[f"cells_{tag}"] = sp.groupby(["window", "split"]).size().unstack(fill_value=0).to_dict("index")
    es = ev[["window", "event_id", "x_m", "y_m"]].copy()
    es["split"] = assign(es, held, B, G)
    es[["window", "event_id", "split"]].to_parquet(out_dir / "event_split.parquet", index=False)
    files["event_split.parquet"] = sha256_file(out_dir / "event_split.parquet")
    prim = ev[ev.clean_strict_all_years].merge(es[["event_id", "window", "split"]], on=["event_id", "window"])
    info["primary_clean_strict_events_by_split"] = prim.split.value_counts().to_dict()  # counts only
    man = {"stage": "M5-seal", "name": "m5_provisional_holdout_v1", "sealed_utc": datetime.now(timezone.utc).isoformat(), "params": params, "heldout_blocks": {w: held[w] for w in held},
           "blocks_info": info, "inputs": {"cells5": sha256_file(cells5_path), "cells10": sha256_file(cells10_path), "events": sha256_file(events_path)}, "files_sha256": files,
           "supersedes": supersedes,
           "rule": "EDA reads only split == 'train' through precursor_ml.m5_data.load_train; the held-out part is not opened, plotted or summarised in M5; M6 finalises the splits from it"}
    man["seal_sha256"] = hashlib.sha256(json.dumps({"params": params, "heldout_blocks": man["heldout_blocks"], "files": files}, sort_keys=True).encode()).hexdigest()
    (out_dir / "split_manifest.json").write_text(json.dumps(man, indent=1, default=str))
    return man
