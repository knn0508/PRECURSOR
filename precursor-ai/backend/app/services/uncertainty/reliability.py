"""Reliability conditions: when an output must be suppressed. Rules in docs/scientific/UNCERTAINTY_AND_RELIABILITY.md."""
from datetime import datetime
from typing import Any

from app.schemas.uncertainty import SuppressionReason


def suppression_reasons(*, valid_region_bbox: tuple[float, float, float, float] | None, valid_time: dict[str, Any] | None,
                        point: tuple[float, float] | None, when: datetime | None, valid_fraction: float | None,
                        min_valid_fraction: float, synthetic_inputs: bool) -> list[SuppressionReason]:
    """`valid_region_bbox` = (west, south, east, north); `point` = (lon, lat). `min_valid_fraction` is caller policy (no default)."""
    r: list[SuppressionReason] = []
    if synthetic_inputs:
        r.append(SuppressionReason(code="SYNTHETIC_INPUTS", message="inputs are synthetic"))
    if valid_region_bbox is not None and point is not None:
        w, s, e, n = valid_region_bbox
        if not (w <= point[0] <= e and s <= point[1] <= n):
            r.append(SuppressionReason(code="OUTSIDE_VALID_REGION", message="location is outside the model's valid region"))
    if valid_time is not None and when is not None:
        start = datetime.fromisoformat(str(valid_time["start"]).replace("Z", "+00:00"))
        end = valid_time.get("end")
        end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00")) if end else None
        if when < start or (end_dt is not None and when > end_dt):
            r.append(SuppressionReason(code="OUTSIDE_VALID_TIME", message="time is outside the model's valid time"))
    if valid_fraction is None or valid_fraction < min_valid_fraction:
        r.append(SuppressionReason(code="INSUFFICIENT_COVERAGE", message="valid input coverage is unknown or below the required fraction"))
    return r
