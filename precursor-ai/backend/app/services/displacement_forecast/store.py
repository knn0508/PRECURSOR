"""Reads <DATA_ROOT>/displacement_forecast/{artifacts,results}. Pure file access; raises FileNotFoundError when absent."""
import csv
import json
import math
from pathlib import Path
from typing import Any

from app.core import geo_env  # noqa: F401  (must precede rasterio: fixes PROJ_LIB)

LABEL = "RESEARCH / INFERRED / NOT A WARNING: LOS displacement-increment forecast, not a landslide probability."
IMAGES = {
    "forecast_map": "forecast_map.png", "heldout_poi": "heldout_forecast_poi.png", "opera_overview": "opera_overview.png",
    "nisar_observation": "nisar_observation.png", "verification_coverage": "verification_coverage.png",
    "verification_skill_map": "verification_skill_map.png", "verification_timeseries": "verification_timeseries.png",
}
DOCS = {"limitations_v2": "limitations_v2.md", "limitations_v3": "limitations_v3.md", "final_comparison_v3": "final_comparison_v3.md",
        "verification": "verification.md", "findings": "findings.md"}


def root(data_root: Path) -> Path:
    return Path(data_root) / "displacement_forecast"


def _json(p: Path) -> Any:
    if not p.is_file():
        raise FileNotFoundError(f"{p.name} not found in the displacement-forecast bundle")
    return json.loads(p.read_text(encoding="utf-8"))


def _clean(v: Any) -> Any:
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def status(data_root: Path) -> dict[str, Any]:
    pp = root(data_root) / "artifacts" / "provenance.json"
    prov = _json(pp) if pp.is_file() else None
    src = root(data_root) / "SOURCE.md"
    rp = root(data_root) / "artifacts" / "reproduction.json"
    return {"reproduction": _json(rp) if rp.is_file() else None, "available": prov is not None, "label": LABEL, "provenance": prov, "images": list(IMAGES), "docs": list(DOCS),
            "origin": "third-party result bundle (Farid145678/NASA_SPACE_APPS); training and metrics are the author's. Forecast reproduction here: see `reproduction`",
            "source_note": src.read_text(encoding="utf-8") if src.is_file() else None}


def metrics(data_root: Path) -> dict[str, Any]:
    r = root(data_root)
    m = _json(r / "artifacts" / "metrics.json")
    v = _json(r / "results" / "verification.json")
    keys = ("primary_model", "noise_floor", "per_pixel", "ground_truth_coverage", "by_regime")
    return _clean({"label": LABEL, "config": m["config"], "splits": m["splits"], "onset_threshold": m["onset_threshold"],
                   "best_naive_mae": m["best_naive_mae"], "dl_beats_naive": m["dl_beats_naive"],
                   "benchmark": m["summary"], "verification": {k: v[k] for k in keys}})


def forecast_grid(data_root: Path) -> dict[str, Any]:
    """q10/q50/q90 12-day LOS increment (mm) on the 30 m grid. NaN becomes null = no reliable estimate."""
    import numpy as np
    import rasterio
    from rasterio.warp import transform, transform_bounds

    p = root(data_root) / "artifacts" / "forecast.tif"
    if not p.is_file():
        raise FileNotFoundError("forecast.tif not found in the displacement-forecast bundle")
    with rasterio.open(p) as ds:
        a = ds.read().astype("float64")
        w, s, e, n = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)
        names = list(ds.descriptions)
        b = ds.bounds
        # UTM grid is rotated vs lon/lat by ~0.75 deg here (~70 m over the AOI): keep the true corners (TL, TR, BR, BL) so the map overlay is exact
        cx, cy = transform(ds.crs, "EPSG:4326", [b.left, b.right, b.right, b.left], [b.top, b.top, b.bottom, b.bottom])
        corners = [[float(x), float(y)] for x, y in zip(cx, cy)]
    prov = _json(root(data_root) / "artifacts" / "provenance.json")

    def rows(b: "np.ndarray") -> list[list[float | None]]:
        return [[round(float(x), 3) if math.isfinite(x) else None for x in row] for row in b]

    return {"label": LABEL, "issue_time": prov["issue_time"], "horizon_days": prov["horizon_days"], "unit": "mm (LOS increment)",
            "bounds": {"west": w, "south": s, "east": e, "north": n}, "corners": corners, "height": int(a.shape[1]), "width": int(a.shape[2]),
            "bands": {nm: rows(a[i]) for i, nm in enumerate(names)}, "no_estimate_share": float(np.mean(~np.isfinite(a[1])))}


def image_path(data_root: Path, name: str) -> Path:
    if name not in IMAGES:
        raise KeyError(f"unknown image {name!r}")
    p = root(data_root) / "artifacts" / IMAGES[name]
    if not p.is_file():
        raise FileNotFoundError(IMAGES[name])
    return p


def doc_text(data_root: Path, name: str) -> str:
    if name not in DOCS:
        raise KeyError(f"unknown doc {name!r}")
    p = root(data_root) / "results" / DOCS[name]
    if not p.is_file():
        raise FileNotFoundError(DOCS[name])
    return p.read_text(encoding="utf-8")


def benchmark_rows(data_root: Path) -> list[dict[str, str]]:
    p = root(data_root) / "results" / "benchmark_summary.csv"
    if not p.is_file():
        raise FileNotFoundError("benchmark_summary.csv not found")
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---- backtest (forecast vs reality) -------------------------------------------------------------------------------------------------
def _bt_dir(data_root: Path) -> Path:
    return root(data_root) / "backtest"


def _grid_corners(data_root: Path) -> list[list[float]]:
    return forecast_grid(data_root)["corners"]


def backtest_meta(data_root: Path) -> dict[str, Any]:
    return _clean(_json(_bt_dir(data_root) / "backtest.json"))


def backtest_grids(data_root: Path, issue: str) -> dict[str, Any]:
    """Forecast q10/q50/q90, actual and difference (forecast - actual) for one issue date. NaN -> null; masked pixels have no actual."""
    import numpy as np

    meta = backtest_meta(data_root)
    if issue not in meta["issue_dates"]:
        raise KeyError(f"no backtest for issue date {issue!r}")
    i = meta["issue_dates"].index(issue)
    z = np.load(_bt_dir(data_root) / "grids.npz")
    f, a = z["forecast"][i].astype("float64"), z["actual"][i].astype("float64")

    def rows(b: "np.ndarray") -> list[list[float | None]]:
        return [[round(float(x), 3) if math.isfinite(x) else None for x in row] for row in b]

    return {"label": LABEL, "issue": issue, "target": meta["target_dates"][i], "unit": "mm (LOS increment)", "corners": _grid_corners(data_root),
            "height": int(a.shape[0]), "width": int(a.shape[1]),
            "forecast": {"q10_mm": rows(f[0]), "q50_mm": rows(f[1]), "q90_mm": rows(f[2])}, "actual_mm": rows(a), "difference_mm": rows(f[1] - a),
            "metrics": meta["per_date"][i]}


def area_coverage(data_root: Path, area_geojson: dict[str, Any]) -> dict[str, Any]:
    """How much of a monitored area the bundle's data footprint covers. covered=False means NO result may be shown for the area."""
    from shapely.geometry import Polygon, shape

    fp = Polygon(_grid_corners(data_root))
    a = shape(area_geojson)
    inter = a.intersection(fp).area
    return {"covered": bool(inter > 0), "area_covered_pct": float(100 * inter / a.area) if a.area > 0 else 0.0,
            "footprint_covered_by_area_pct": float(100 * inter / fp.area)}
