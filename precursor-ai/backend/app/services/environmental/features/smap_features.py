"""Descriptive SMAP soil-moisture features from a SmapResult. No classes, thresholds or risk language."""
from __future__ import annotations

from typing import Any

from app.services.environmental.smap.smap_processor import SmapResult


def _feat(value: Any, units: str | None, note: str | None = None) -> dict[str, Any]:
    return {"value": value, "units": units, "note": note}


def smap_features(result: SmapResult) -> dict[str, Any]:
    c = result.counts
    u = result.units
    over = "over observed days only; missing days are not counted"
    feats: dict[str, Any] = {
        "observed_days": _feat(c["observed_days"], "days"),
        "missing_days": _feat(c["missing_days"], "days"),
        "temporal_coverage_percent": _feat(result.quality.valid_percent, "%"),
    }
    for key, label in (("soil_moisture_am", "am"), ("soil_moisture_pm", "pm"), ("soil_moisture", "combined")):
        v = [d[key] for d in result.daily if d[key] is not None]
        note = over if label != "combined" else over + "; combined = AM/PM mean, only days with both overpasses"
        feats[f"mean_{label}"] = _feat(sum(v) / len(v) if v else None, u, note)
        feats[f"min_{label}"] = _feat(min(v) if v else None, u, note)
        feats[f"max_{label}"] = _feat(max(v) if v else None, u, note)
    last = next((d for d in reversed(result.daily) if d["observed"]), None)
    feats["last_observed_value_am"] = _feat(last["soil_moisture_am"] if last else None, u,
                                            f"date {last['date']}" if last else "no observed day")
    feats["last_observed_value_pm"] = _feat(last["soil_moisture_pm"] if last else None, u,
                                            f"date {last['date']}" if last else "no observed day")
    feats["last_observed_date"] = _feat(last["date"] if last else None, None)
    feats["quality_filter"] = _feat("on" if result.quality_filter else "off", None,
                                    "retrieval_qual_flag bit 0 == 0 (recommended quality)" if result.quality_filter
                                    else "cells not of recommended quality are included")
    feats["native_resolution"] = _feat(
        result.quality.native_resolution, None,
        "9 km EASE-Grid 2.0 posting from a ~36 km radiometer footprint; top ~5 cm of soil; a cell value, not local")
    return {"features": feats, "provenance": result.provenance.to_dict(), "counts": dict(c),
            "warnings": list(result.warnings)}
