"""NDVI features: descriptive statistics over valid AOI pixels. No vegetation-health classes or thresholds."""
from __future__ import annotations

from typing import Any


def vegetation_features(result: Any) -> dict[str, Any]:
    s = result.stats
    f = {f"ndvi_{k}": {"value": s[k], "unit": "NDVI (dimensionless)", "note": "over valid AOI pixels"} for k in ("mean", "min", "max", "std")}
    f["ndvi_valid_coverage"] = {"value": s["valid_percent"], "unit": "percent of AOI pixels", "note": "pixels with a valid NDVI value"}
    f["ndvi_out_of_range_count"] = {"value": s["n_out_of_range"], "unit": "source pixels", "note": "outside [-1, 1]; treated as invalid, not clipped"}
    f["ndvi_observation"] = {"value": "; ".join(sorted(set(result.observation.values()))), "unit": "date/period",
                             "note": "from file tags or name; UNKNOWN when absent"}
    return {"features": f, "warnings": list(result.warnings)}
