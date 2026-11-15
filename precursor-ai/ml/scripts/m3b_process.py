"""M3b: round 2 factors (rivers, faults, soil, NDVI) on the M3 grids. One command, idempotent, deterministic, no downloads.

    ml/.venv/Scripts/python ml/scripts/m3b_process.py                  # 5 km primary grid: NDVI cache + 3 windows (subprocess each) + finalize
    ml/.venv/Scripts/python ml/scripts/m3b_process.py --cell-m 10000   # 10 km sensitivity grid
Requires M3 products for the same grid (m3_preprocess.py) and the verified round 2 files (m2b_acquire.py).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))
from precursor_ml import m3, m3b  # noqa: E402


def out_root(cfg, cell):
    return m3.INTERIM if cell == 5000 else m3.INTERIM.parent / f"m3_{cell // 1000}km"


def finalize(cfg, out):
    import pandas as pd

    base = pd.read_parquet(out / "cells_all.parquet")
    r2 = pd.concat([pd.read_parquet(out / n / "cells_r2.parquet") for n in cfg["windows"]], ignore_index=True)
    full = base.merge(r2, on=["window", "row", "col"], how="left", validate="one_to_one")
    assert len(full) == len(base)
    full.to_parquet(out / "cells_all_full.parquet", index=False)
    ev = pd.read_parquet(out / "events_all.parquet")
    s = ev[ev.strict_all_years]
    ndvi_overlap = int(s.date.between("2013-01-01", "2017-12-31 23:59:59").sum())
    summaries = {n: json.loads((out / n / "summary_r2.json").read_text()) for n in cfg["windows"]}
    r2m = json.loads((m3.RAW / "manifest_round2.json").read_text())
    manifest = {
        "stage": "M3b", "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "code_version": m3.code_version(), "cell_m": cfg["grid"]["cell_m"],
        "config_sha256": cfg["_sha256"], "seed": "none (deterministic)",
        "inputs": {"manifest_round2_sha256": m3.sha256_file(m3.RAW / "manifest_round2.json"),
                   "files": {k: {"sha256": v["sha256"], "size_bytes": v["size_bytes"]} for k, v in r2m.items()},
                   "m3_manifest_sha256": m3.sha256_file(out / "m3_manifest.json")},
        "rules": {"river_major_upland_skm_ge": m3b.MAJOR_UPLAND_SKM, "fault_young_ages": sorted(m3b.YOUNG), "distance_pixel_m": 250, "distance_margin_m": 50000,
                  "ndvi_reliability": "0-2", "ndvi_months": "2013-01..2017-12", "ndvi_min_valid_months": 12, "soil_depth_weights_cm": m3b.DEPTHS,
                  "faults_offshore_layer_used": False},
        "windows": {n: {"outputs_sha256": s_["outputs"], "line_counts_in_extent": s_["line_counts_in_extent"]} for n, s_ in summaries.items()},
        "combined_outputs_sha256": {"cells_all_full.parquet": m3.sha256_file(out / "cells_all_full.parquet")},
        "caveats": {
            "ndvi_period": f"VIIRS NDVI covers 2013-2017; {ndvi_overlap} of {len(s)} strict events fall in that period (the rest precede it); land cover is 2021",
            "bdod": "bulk density NOT acquired: 19 of 44 tiles return HTTP 404 for all three depths (MISSING_FACTOR until the user decides)",
            "soil": "SoilGrids is modelled; 250 m; uncertain in mountains/forests", "faults": "mapped traces are incomplete; offshore layer not used",
            "rivers": "HydroRIVERS about 500 m positional accuracy", "roads": "not approved: no road factor"},
    }
    (out / "m3b_manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    print("finalized", out / "m3b_manifest.json", "ndvi overlap", ndvi_overlap, "of", len(s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window")
    ap.add_argument("--cell-m", type=int, default=5000)
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--build-ndvi", action="store_true")
    a = ap.parse_args()
    cfg = m3.load_config()
    cfg["grid"]["cell_m"] = a.cell_m
    out = out_root(cfg, a.cell_m)
    if a.build_ndvi or not m3b.NDVI_CACHE.exists():
        t = time.time()
        m3b.build_ndvi_climatology()
        print("ndvi climatology built in", round(time.time() - t, 1), "s")
        if a.build_ndvi:
            return 0
    if a.window:
        t = time.time()
        s = m3b.run_window_r2(a.window, cfg["windows"][a.window], cfg, out)
        print(a.window, "r2 done in", round(time.time() - t, 1), "s;", len(s["bands"]), "bands")
        return 0
    if not a.finalize:
        for n in cfg["windows"]:
            r = subprocess.run([sys.executable, __file__, "--window", n, "--cell-m", str(a.cell_m)])
            if r.returncode:
                return r.returncode
    finalize(cfg, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
