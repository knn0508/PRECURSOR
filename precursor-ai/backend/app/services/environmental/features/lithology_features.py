"""Lithology features: class distribution only (descriptive). No hardness/erodibility/risk labels."""
from __future__ import annotations

from typing import Any


def lithology_features(result: Any) -> dict[str, Any]:
    f: dict[str, Any] = {"lithology_valid_coverage": {"value": result.quality.valid_percent, "unit": "percent of AOI pixels",
                                                      "note": "share of AOI pixels with a class id"}}
    for c in result.classes:
        f[f"lithology_class_{c['class_id']}_percent"] = {"value": c["percent"], "unit": "percent of valid AOI pixels",
                                                         "note": f"user legend name: {c['name']}"}
    for u in result.unknown_classes:
        f[f"lithology_unlisted_class_{u['class_id']}_percent"] = {"value": u["percent"], "unit": "percent of valid AOI pixels",
                                                                   "note": "class id absent from the user legend"}
    return {"features": f, "warnings": list(result.warnings)}
