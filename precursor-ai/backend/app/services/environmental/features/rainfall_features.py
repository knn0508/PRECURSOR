"""Descriptive rainfall features from a RainfallResult. No thresholds, no risk language, no scores."""
from __future__ import annotations

from typing import Any

from app.services.environmental.rainfall.precipitation_processor import RainfallResult


def _feat(value: Any, units: str | None, note: str | None = None) -> dict[str, Any]:
    return {"value": value, "units": units, "note": note}


def rainfall_features(result: RainfallResult) -> dict[str, Any]:
    c = result.counts
    vals = [d["precip_mm_day"] for d in result.daily if d["observed"]]
    feats: dict[str, Any] = {
        "observed_days": _feat(c["observed_days"], "days"),
        "missing_days": _feat(c["missing_days"], "days"),
        "temporal_coverage_percent": _feat(result.quality.valid_percent, "%"),
        "total_mm_over_observed_days": _feat(round(sum(vals), 6) if vals else None, "mm",
                                              "sum over OBSERVED days only; missing days are not counted as zero"),
        "max_daily_mm": _feat(max(vals) if vals else None, "mm/day"),
    }
    for w in result.windows:
        key = f"sum_{w}d_mm"
        last = next((r for r in reversed(result.rolling) if r.get(key) is not None), None)
        feats[f"last_complete_{w}d_sum"] = _feat(
            last[key] if last else None, "mm",
            f"window ending {last['date']}" if last else "no fully observed window")
    feats["monthly_totals_complete_months"] = _feat(
        {m["month"]: m["sum_mm"] for m in result.monthly if m["complete"]}, "mm",
        "only calendar months with every day observed")
    return {"features": feats, "provenance": result.provenance_accumulations.to_dict(),
            "warnings": list(result.warnings)}
