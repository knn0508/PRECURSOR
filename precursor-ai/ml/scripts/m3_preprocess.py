"""M3 preprocessing: one command for the whole stage (idempotent, deterministic).

    ml/.venv/Scripts/python ml/scripts/m3_preprocess.py            # all windows (one subprocess each, bounds memory) + finalize
    ml/.venv/Scripts/python ml/scripts/m3_preprocess.py --window CA_S
    ml/.venv/Scripts/python ml/scripts/m3_preprocess.py --finalize # manifest + combined tables only
    ml/.venv/Scripts/python ml/scripts/m3_preprocess.py --cell-m 10000  # sensitivity grid -> data/ml/interim/m3_10km/ (primary stays 5 km)

Reads data/ml/raw (verified in M2), writes data/ml/interim/m3/. No downloads, no modelling.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))
from precursor_ml import m3  # noqa: E402


def sensitivity(cfg):
    """How label ambiguity (accuracy circle touching more than one cell) depends on the cell size. Cheap: no rasters."""
    glc = m3.load_glc()
    rows = []
    for cell in (1000, 2500, 5000, 10000, 20000):
        for name, bbox in cfg["windows"].items():
            ref = m3.make_grid(bbox, cell)
            ev, _ = m3.build_events(bbox, ref, cfg, None, glc)
            st = ev[ev.strict_all_years]
            rows.append({"cell_m": cell, "window": name, "events_strict_all_years": int(len(st)),
                         "share_ambiguous": round(float(st.label_ambiguous.mean()), 3) if len(st) else None,
                         "mean_cells_in_radius": round(float(st.n_cells_in_radius.mean()), 2) if len(st) else None,
                         "distinct_point_cells": int(st[["row", "col"]].drop_duplicates().shape[0]), "cells_total": int(ref.grid.width * ref.grid.height)})
    return rows


def finalize(cfg, out):
    import pandas as pd

    summaries = {n: json.loads((out / n / "summary.json").read_text()) for n in cfg["windows"]}
    ev = pd.concat([pd.read_parquet(out / n / "events.parquet").assign(window=n) for n in cfg["windows"]], ignore_index=True)
    ev.to_parquet(out / "events_all.parquet", index=False)
    cells = pd.concat([pd.read_parquet(out / n / "cells.parquet") for n in cfg["windows"]], ignore_index=True)
    cells.to_parquet(out / "cells_all.parquet", index=False)
    raw_manifest = json.loads((m3.RAW / "manifest.json").read_text())
    census = {k: m3.sha256_file(m3.RAW / "census" / k) for k in ("glc.csv", "nasa_coolr_new_events.zip")}
    coolr = None
    try:
        import geopandas as gpd
        from shapely.geometry import box

        g = gpd.read_file(m3.ROOT / "data/ml/interim/census/nasa_coolr_new_events/nasa_coolr_new_events.gdb", layer="nasa_coolr_events_new_point")
        coolr = {n: int(g.within(box(*b)).sum()) for n, b in cfg["windows"].items()}
    except Exception as exc:  # report, do not hide
        coolr = f"not computed: {type(exc).__name__}"
    mapping = {"classes": m3.LITH_CLASSES, "generalize_to_class": m3.LITH_MAP,
               "unmapped_by_window": {n: s["lithology"]["unmapped_generalize_values"] for n, s in summaries.items()},
               "note": "Only the shared field GENERALIZE is used. ORIG_LABEL/SGMC_LABEL unit codes are state specific and are not mapped."}
    (out / "lithology_mapping.json").write_text(json.dumps(mapping, indent=1))
    sens = sensitivity(cfg)
    (out / "grid_sensitivity.json").write_text(json.dumps(sens, indent=1))
    manifest = {
        "stage": "M3", "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "code_version": m3.code_version(),
        "config_sha256": cfg["_sha256"], "config": {k: v for k, v in cfg.items() if not k.startswith("_")}, "cell_m": cfg["grid"]["cell_m"],
        "seed": "none (deterministic; no randomness in M3)",
        "software": {"python": platform.python_version(), **{p: __import__(p).__version__ for p in ("numpy", "pandas", "rasterio", "geopandas", "pyproj", "shapely")}},
        "inputs": {"raw_manifest_sha256": m3.sha256_file(m3.RAW / "manifest.json"), "files": {k: {"sha256": v["sha256"], "size_bytes": v["size_bytes"]} for k, v in raw_manifest.items()}, "census_labels": census},
        "windows": {n: {"bbox_wsen": s["bbox_wsen"], "epsg": s["grid"]["epsg"], "grid": [s["grid"]["width"], s["grid"]["height"]], "cells_inside": s["cells_inside"], "outputs_sha256": s["outputs"],
                        "events_strict_all_years": s["events_strict_all_years"], "events_strict_in_period": s["events_strict_in_period"]} for n, s in summaries.items()},
        "combined_outputs_sha256": {p.name: m3.sha256_file(p) for p in (out / "events_all.parquet", out / "cells_all.parquet", out / "lithology_mapping.json")},
        "coolr_new_events_inside_windows": coolr,
        "not_available_factors": {
            "soil (SoilGrids)": "not approved/downloaded", "NDVI": "not approved/downloaded", "distance to rivers/faults/roads": "not approved/downloaded",
            "SMAP soil moisture": "not approved/downloaded", "daily IMERG accumulations 1/3/7/14/30 d and antecedent indices": "only monthly IMERG approved (design C item)",
            "InSAR/SAR (LOS displacement, coherence, velocity, time series windows)": "no SAR files approved or downloaded; NISAR not used for training",
            "curvature, TWI, flow accumulation": "not computed: not justified at a 5 km analysis cell (M5/M6 may revisit)"},
    }
    (out / "m3_manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    print("finalized", out / "m3_manifest.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window")
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--cell-m", type=int, help="override grid.cell_m (config change only); writes to data/ml/interim/m3_<km>km")
    a = ap.parse_args()
    cfg = m3.load_config()
    out = m3.INTERIM
    if a.cell_m and a.cell_m != cfg["grid"]["cell_m"]:
        cfg["grid"]["cell_m"] = a.cell_m
        out = m3.INTERIM.parent / f"m3_{a.cell_m // 1000}km"
    extra = ["--cell-m", str(a.cell_m)] if a.cell_m else []
    if a.window:
        t = time.time()
        s = m3.run_window(a.window, cfg["windows"][a.window], cfg, out_root=out)
        print(a.window, "done in", round(time.time() - t, 1), "s; cells inside", s["cells_inside"], "strict events", s["events_strict_all_years"])
        return 0
    if not a.finalize:
        for n in cfg["windows"]:
            r = subprocess.run([sys.executable, __file__, "--window", n, *extra])
            if r.returncode:
                print("window failed:", n)
                return r.returncode
    finalize(cfg, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
