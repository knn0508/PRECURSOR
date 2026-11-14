"""Land-cover features: class distribution only. No risk labels, no weights."""
from __future__ import annotations

from typing import Any


def land_cover_features(result: Any) -> dict[str, Any]:
    return {"values": {"class_distribution_percent": {c["class_id"]: c["percent"] for c in result.classes},
                       "class_names": {c["class_id"]: c["name"] for c in result.classes},
                       "unknown_class_percent": {u["class_id"]: u["percent"] for u in result.unknown_classes},
                       "observation_year": result.year, "dataset_version": result.version,
                       "valid_coverage_percent": result.quality.valid_percent},
            "units": "percent of valid AOI pixels", "warnings": list(result.warnings)}
