"""Soil features: descriptive per property/depth statistics with units. No scores or classes."""
from __future__ import annotations

from typing import Any


def soil_features(result: Any) -> dict[str, Any]:
    """SoilResult (or any object with .layers/.warnings) -> {values: [...], warnings: [...]}. Each value keeps raw and converted units."""
    values = []
    for l in result.layers:
        c = l["converted_stats"]
        values.append({"property": l["property"], "depth_cm": [l["top_cm"], l["bottom_cm"]], "statistic": l["statistic"],
                       "mean": c["mean"], "min": c["min"], "max": c["max"], "units": l["converted_units"],
                       "raw_units": l["source_units"], "scale_factor": l["scale_factor"], "valid_percent": l["valid_percent"]})
    return {"values": values, "warnings": list(result.warnings),
            "note": "Descriptive AOI statistics of modelled SoilGrids predictions; not measurements and not a susceptibility score."}
