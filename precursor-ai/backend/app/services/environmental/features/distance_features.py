"""Distance features: min/mean/max Euclidean distance (metres) to the nearest user-provided feature, per kind."""
from __future__ import annotations

from typing import Any


def distance_features(results: list[Any]) -> dict[str, Any]:
    f: dict[str, Any] = {}
    warns: list[str] = []
    for r in results:
        for k in ("min", "mean", "max"):
            f[f"distance_{r.kind}_{k}_m"] = {"value": r.stats[f"{k}_m"], "unit": "metre",
                                             "note": f"{k} over AOI pixel centres to nearest {r.kind} feature ({r.stats['n_features']} features, {r.stats['crs']})"}
        warns.extend(f"{r.kind}: {w}" for w in r.warnings)
    return {"features": f, "warnings": warns}
