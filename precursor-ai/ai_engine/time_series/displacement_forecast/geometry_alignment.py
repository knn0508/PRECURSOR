"""Cross-geometry alignment: QA classes, interval matching and grid resampling (skill v3, Phase 1).

* OPERA ascending F16940 and descending F18904 AOI subsets lie on the SAME 30 m UTM lattice (verified: equal
  x/y pixel centres), so no resampling is applied between them; `assert_same_grid` enforces this.
* NISAR GUNW is on an 80 m lattice. OPERA is brought to it by block statistics over VALID OPERA pixels only
  (continuous) or by nearest/majority (categorical). A resampled value is not a new independent observation.
* Intervals are matched by acquisition dates; different-day values are never treated as the same displacement.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VALID, MASKED, MISSING = "valid_observation", "masked_but_finite", "missing"


def obs_class(disp: np.ndarray, recommended_mask: np.ndarray) -> np.ndarray:
    """Per-pixel class of one acquisition. Masked-but-finite values are kept as a diagnostic class only."""
    fin = np.isfinite(disp)
    ok = fin & (np.nan_to_num(recommended_mask) > 0.5)
    out = np.full(disp.shape, MISSING, dtype=object)
    out[ok] = VALID
    out[fin & ~ok] = MASKED
    return out


def valid_only(disp: np.ndarray, recommended_mask: np.ndarray) -> np.ndarray:
    """Measured value where it is a valid observation, NaN elsewhere (never fills masked values)."""
    return np.where(obs_class(disp, recommended_mask) == VALID, disp, np.nan)


def coverage_classes(asc_valid: np.ndarray, desc_valid: np.ndarray) -> np.ndarray:
    a, d = np.asarray(asc_valid, bool), np.asarray(desc_valid, bool)
    out = np.full(a.shape, "neither_valid", dtype=object)
    out[a & d] = "both_valid"; out[a & ~d] = "asc_only"; out[~a & d] = "desc_only"
    return out


def assert_same_grid(x1, y1, x2, y2, tol=1e-6):
    if len(x1) != len(x2) or len(y1) != len(y2) or np.max(np.abs(np.asarray(x1) - x2)) > tol or np.max(np.abs(np.asarray(y1) - y2)) > tol:
        raise ValueError("grids differ: explicit resampling with valid-fraction tracking is required")


def interval_from_ministack(disp_by_sec: dict, ref_by_sec: dict, t1, t2):
    """Displacement between secondary dates t1 < t2 from ONE frame's granules (values in that frame's units).

    Same ministack: d(t2) - d(t1). Across one boundary: d(t2) + d_prev(new_ref) - d(t1), where d_prev(new_ref)
    is the granule whose secondary date equals t2's reference. Returns None if not reachable (no invention).
    """
    t1, t2 = pd.Timestamp(t1).normalize(), pd.Timestamp(t2).normalize()
    if t1 not in disp_by_sec or t2 not in disp_by_sec:
        return None
    r1, r2 = ref_by_sec[t1], ref_by_sec[t2]
    if r1 == r2:
        return disp_by_sec[t2] - disp_by_sec[t1]
    if r2 in disp_by_sec and ref_by_sec[r2] == r1:
        return disp_by_sec[t2] + disp_by_sec[r2] - disp_by_sec[t1]
    if r2 == t1:
        return disp_by_sec[t2]
    return None


def match_intervals(a_dates, b_dates, tol_days: float = 1.0) -> list[tuple]:
    """Pairs of consecutive-or-not intervals (a1, a2, b1, b2) whose endpoints agree within tol_days."""
    a = sorted(pd.Timestamp(x).normalize() for x in a_dates)
    out = []
    for b1, b2 in b_dates:
        b1, b2 = pd.Timestamp(b1).normalize(), pd.Timestamp(b2).normalize()
        c1 = min(a, key=lambda t: abs((t - b1).days)); c2 = min(a, key=lambda t: abs((t - b2).days))
        if abs((c1 - b1).days) <= tol_days and abs((c2 - b2).days) <= tol_days and c2 > c1:
            out.append((c1, c2, b1, b2))
    return out


def block_to_grid(values: np.ndarray, valid: np.ndarray, src_x, src_y, dst_x, dst_y, dst_spacing: float,
                  min_valid_frac: float = 0.5) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Continuous field -> coarser grid: mean of VALID source pixels whose centres fall in each target cell.

    Returns (mean, valid_fraction, n_valid). Cells with valid_fraction < min_valid_frac are NaN.
    """
    X, Y = np.meshgrid(src_x, src_y)
    ci = np.floor((X - (dst_x[0] - dst_spacing / 2)) / dst_spacing).astype(int)
    ri = np.floor(((dst_y[0] + dst_spacing / 2) - Y) / dst_spacing).astype(int)       # north-up target
    inside = (ci >= 0) & (ci < len(dst_x)) & (ri >= 0) & (ri < len(dst_y))
    shape = (len(dst_y), len(dst_x))
    flat = np.where(inside, ri * shape[1] + ci, -1)
    v = np.asarray(valid, bool) & np.isfinite(values) & inside
    n_all = np.bincount(flat[inside], minlength=shape[0] * shape[1])
    n_ok = np.bincount(flat[v], minlength=shape[0] * shape[1])
    s = np.bincount(flat[v], weights=values[v], minlength=shape[0] * shape[1])
    frac = np.where(n_all > 0, n_ok / np.maximum(n_all, 1), 0.0)
    mean = np.where((n_ok > 0) & (frac >= min_valid_frac), s / np.maximum(n_ok, 1), np.nan)
    return mean.reshape(shape), frac.reshape(shape), n_ok.reshape(shape)


def categorical_to_grid(labels: np.ndarray, src_x, src_y, dst_x, dst_y) -> np.ndarray:
    """Categorical layer -> another grid by nearest source pixel (labels are never averaged)."""
    ci = np.clip(np.round((np.asarray(dst_x) - src_x[0]) / (src_x[1] - src_x[0])).astype(int), 0, len(src_x) - 1)
    ri = np.clip(np.round((np.asarray(dst_y) - src_y[0]) / (src_y[1] - src_y[0])).astype(int), 0, len(src_y) - 1)
    return np.asarray(labels)[np.ix_(ri, ci)]


def admissible_at(issue_time, product_first_acquisition) -> bool:
    """An external observation may enter a forecast issued at `issue_time` only if it was acquired before it."""
    return pd.Timestamp(product_first_acquisition) <= pd.Timestamp(issue_time)
