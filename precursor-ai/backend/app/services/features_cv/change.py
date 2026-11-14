"""Change-detection features, behind a hard refusal guard.

`ndvi_difference`, `coherence_change` and `velocity_gradient` are only produced from DATED inputs of REAL origin on one
grid. Synthetic, unverified, undated, same-date, mixed-unit or mixed-grid inputs raise `ChangeDetectionRefused`; the
pipeline turns that into NOT_AVAILABLE. The plain arithmetic helpers are exposed for unit tests only and are not
reachable from the pipeline without passing the guard.

Choice (flagged, see FEATURE_EXTRACTION.md): `velocity_gradient` is the SPATIAL gradient of one dated real InSAR velocity
raster (it needs one real dated input); a change in velocity between two epochs is an acceleration measure and belongs to Phase 6.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from app.services.features_cv.terrain import slope_break  # same central-difference gradient magnitude
from app.services.features_cv.tiling import assert_same_grid
from app.services.features_cv.types import REAL_ORIGIN, ChangeDetectionRefused, FeatureError


@dataclass
class DatedInput:
    layer_type: str
    array: np.ndarray
    date: datetime | None
    origin: str | None
    units: str | None
    grid: dict[str, Any]
    synthetic: bool = False
    notes: list[str] = field(default_factory=list)


def _why_not(i: DatedInput, label: str) -> list[str]:
    r = []
    if i.date is None:
        r.append(f"{label}: no acquisition date")
    if i.synthetic or i.origin != REAL_ORIGIN:
        r.append(f"{label}: origin is {i.origin!r}{' (synthetic)' if i.synthetic else ''}, not {REAL_ORIGIN}")
    return r


def require_two_dated_real_inputs(a: DatedInput, b: DatedInput) -> tuple[DatedInput, DatedInput]:
    """Returns (earlier, later) or raises ChangeDetectionRefused listing EVERY reason."""
    reasons = _why_not(a, "first input") + _why_not(b, "second input")
    if a.layer_type != b.layer_type:
        reasons.append(f"layer types differ ({a.layer_type} vs {b.layer_type})")
    if a.units != b.units:
        reasons.append(f"units differ ({a.units!r} vs {b.units!r})")
    if a.date is not None and b.date is not None and a.date == b.date:
        reasons.append("both inputs have the same date")
    try:
        assert_same_grid(a.grid, b.grid)
    except FeatureError as exc:
        reasons.append(str(exc))
    if reasons:
        raise ChangeDetectionRefused("; ".join(reasons))
    return (a, b) if a.date < b.date else (b, a)  # type: ignore[operator]


def difference(earlier: np.ndarray, later: np.ndarray) -> np.ndarray:
    """later - earlier; NaN where either is missing (never treated as zero)."""
    if earlier.shape != later.shape:
        raise FeatureError("shape mismatch")
    return (later.astype(np.float64) - earlier.astype(np.float64)).astype(np.float32)


def ndvi_difference(a: DatedInput, b: DatedInput) -> tuple[np.ndarray, dict[str, Any]]:
    e, l = require_two_dated_real_inputs(a, b)
    return difference(e.array, l.array), {"earlier": e.date.isoformat(), "later": l.date.isoformat(), "units": e.units}  # type: ignore[union-attr]


def coherence_change(a: DatedInput, b: DatedInput) -> tuple[np.ndarray, dict[str, Any]]:
    return ndvi_difference(a, b)  # identical arithmetic (later - earlier); the layer type is what differs


def velocity_gradient(v: DatedInput, dx_m: np.ndarray, dy_m: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    reasons = _why_not(v, "input")
    if reasons:
        raise ChangeDetectionRefused("; ".join(reasons))
    return slope_break(v.array, dx_m, dy_m), {"date": v.date.isoformat(), "units": f"{v.units or 'unknown'} per metre"}  # type: ignore[union-attr]
