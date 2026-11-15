"""Prioritised, idempotent AOI-subset ingestion of a second OPERA DISP-S1 frame (skill v3, Phase 1).

Why prioritised: on the measured link (~85 kB/s per stream) a full frame takes hours, and the
default chronological order delivers the scientifically important windows last. Granules are
grouped into priority windows. A window is downloaded completely, plus the ministack reference
granules it needs, before the next window starts. Finished subsets are never downloaded again
(`opera.fetch_subsets` skips existing files), so a re-run resumes.

Nothing here alters values. Each subset keeps the original displacement, recommended_mask,
temporal_coherence, connected components and the source attributes (`opera.read_subset`).

Usage (dry run lists what would be fetched, with expected transfer volume):
    python -m displacement_forecast.cross_track_ingest --frame 18904 --dry-run
    python -m displacement_forecast.cross_track_ingest --frame 18904 --workers 6
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3] / "data" / "displacement_forecast"
# Measured on 2026-11-15: one F18904 AOI subset = 8.06 MB of HTTP range reads (file 390 MB).
MEASURED_MB_PER_SUBSET = 8.06

# (name, start, end, thin): thin=False keeps every acquisition (6-day S1A+S1C cadence) for exact date matching
PRIORITY_WINDOWS = [
    ("overlap_nisar_2025_2026", "2025-11-01", "2026-03-31", False),
    ("event_2024", "2024-01-01", "2024-12-31", True),
    ("val_2023", "2023-01-01", "2023-12-31", True),
    ("backfill", "2016-01-01", "2022-12-31", True),
    ("backfill_2025", "2025-01-01", "2025-10-31", True),
]


def frame_manifest(frame: str | int, manifest_path: Path = ROOT / "data/manifest.csv") -> pd.DataFrame:
    m = pd.read_csv(manifest_path)
    m = m[(m.collection == "OPERA_L3_DISP-S1_V1") & (m.frame.astype(str) == str(frame))]
    m = m.drop_duplicates("granule_id").copy()
    m["reference_dt"] = pd.to_datetime(m.reference_dt)
    m["secondary_dt"] = pd.to_datetime(m.secondary_dt)
    return m.sort_values("secondary_dt").reset_index(drop=True)


def reference_closure(sel: pd.DataFrame, full: pd.DataFrame, recursive: bool = False) -> pd.DataFrame:
    """Add the granules whose secondary date is a reference date used by `sel` (and recursively theirs).

    Within one ministack, interval displacement = d(sec2) - d(sec1) needs no extra file. Chaining across
    a ministack boundary needs the granule that ends at the new reference date (one level). A full
    cumulative series from the first reference needs the recursive closure (recursive=True).
    """
    need = set(sel.reference_dt.dt.normalize())
    out = sel.copy()
    first_ref = full.reference_dt.min().normalize()
    while True:
        have = set(out.secondary_dt.dt.normalize())
        missing = {r for r in need if r not in have and r != first_ref}
        if not missing:
            return out.drop_duplicates("granule_id").sort_values("secondary_dt").reset_index(drop=True)
        add = full[full.secondary_dt.dt.normalize().isin(missing)]
        unreachable = missing - set(add.secondary_dt.dt.normalize())
        if unreachable:    # report, never invent
            raise ValueError(f"reference dates not available in catalog: {sorted(unreachable)}")
        out = pd.concat([out, add]).drop_duplicates("granule_id")
        if recursive:
            need |= set(add.reference_dt.dt.normalize())


def plan(frame: str | int, windows=PRIORITY_WINDOWS, out_dir: Path | None = None) -> pd.DataFrame:
    """Ordered download plan: one row per granule with its priority window and on-disk status."""
    from .opera import thin_to_cadence
    full = frame_manifest(frame)
    out_dir = out_dir or ROOT / "data/raw" / f"opera_F{frame}"
    rows, seen = [], set()
    for prio, (name, a, b, thin) in enumerate(windows):
        w = full[(full.secondary_dt >= a) & (full.secondary_dt <= pd.Timestamp(b) + pd.Timedelta(days=1))]
        if thin and len(w):
            w = thin_to_cadence(w)
        w = reference_closure(w, full) if len(w) else w
        for r in w.itertuples():
            if r.granule_id in seen:
                continue
            seen.add(r.granule_id)
            rows.append({"priority": prio, "window": name, "granule_id": r.granule_id, "url": r.url,
                         "reference_dt": r.reference_dt, "secondary_dt": r.secondary_dt,
                         "on_disk": (out_dir / f"{r.granule_id}.nc").exists(),
                         "expected_transfer_mb": MEASURED_MB_PER_SUBSET})
    return pd.DataFrame(rows)


def run(frame, workers=6, passes=3, max_priority=None, log=print):
    from .discovery import AOI
    from .opera import fetch_subsets
    from .remote import RangeFS
    aoi = AOI("portuguese_bend_rpv", -118.380, 33.725, -118.320, 33.765)
    out_dir = ROOT / "data/raw" / f"opera_F{frame}"
    P = plan(frame, out_dir=out_dir)
    for prio, grp in P.groupby("priority", sort=True):
        if max_priority is not None and prio > max_priority:
            break
        for p in range(passes):
            todo = grp[~grp.granule_id.map(lambda g: (out_dir / f"{g}.nc").exists())]
            if todo.empty:
                break
            fetch_subsets(todo, aoi, out_dir, RangeFS(), workers=workers, progress=False)
            done = grp.granule_id.map(lambda g: (out_dir / f"{g}.nc").exists()).sum()
            log(f"[{pd.Timestamp.now():%H:%M:%S}] window {grp.window.iloc[0]} pass {p + 1}: {done}/{len(grp)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--max-priority", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    P = plan(a.frame)
    s = P.groupby(["priority", "window"]).agg(n=("granule_id", "size"), on_disk=("on_disk", "sum"),
                                               first=("secondary_dt", "min"), last=("secondary_dt", "max"),
                                               mb=("expected_transfer_mb", "sum"))
    print(s.to_string())
    if a.dry_run:
        out = ROOT / "results_v3" / f"download_plan_F{a.frame}.csv"
        P.to_csv(out, index=False)
        print(f"dry run: {len(P)} granules, {(~P.on_disk).sum()} to fetch, "
              f"~{P.expected_transfer_mb[~P.on_disk].sum():.0f} MB -> {out}")
    else:
        run(a.frame, a.workers, a.passes, a.max_priority, log=lambda s: print(s, flush=True))
