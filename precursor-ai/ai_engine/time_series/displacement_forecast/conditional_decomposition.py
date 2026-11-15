"""Assumption-labelled decomposition of two LOS observations (skill v3, Phase 2).

Two LOS geometries give at most two independent constraints on u = [E, N, U]. Every estimate here therefore
carries an explicit third constraint and a label:
  conditional_EU_estimate     assumes u_N = 0                       (Option A)
  slope_constrained_estimate  assumes u parallel to DEM downslope   (Option B; one unknown, one dof left)
Neither is a measurement. Bias under violated assumptions is computed, not hidden.
"""
from __future__ import annotations

import numpy as np

COND_MAX = 10.0          # refuse decomposition beyond this 2x2 condition number (pre-specified)


def eu_zero_north(d: np.ndarray, L: np.ndarray, sigma: np.ndarray | None = None) -> dict:
    """Solve [E, U] from k=2 LOS values with u_N := 0.

    d: (2, ...) LOS mm; L: (2, 3) or (2, 3, ...) unit vectors; sigma: (2, ...) 1-sigma LOS errors (mm).
    Returns E, U, their 1-sigma, the condition number and status per pixel.
    """
    d = np.asarray(d, float)
    L = np.asarray(L, float)
    if L.ndim == 2:
        L = L.reshape(2, 3, *([1] * (d.ndim - 1))) * np.ones((1, 1) + d.shape[1:])
    a11, a12, a21, a22 = L[0, 0], L[0, 2], L[1, 0], L[1, 2]       # columns E and U
    det = a11 * a22 - a12 * a21
    E = (a22 * d[0] - a12 * d[1]) / det
    U = (-a21 * d[0] + a11 * d[1]) / det
    s1, s2 = (np.ones_like(d) if sigma is None else np.asarray(sigma, float))
    # inverse rows: E = (a22 d0 - a12 d1)/det, U = (-a21 d0 + a11 d1)/det (independent errors)
    sE = np.sqrt((a22 * s1) ** 2 + (a12 * s2) ** 2) / np.abs(det)
    sU = np.sqrt((a21 * s1) ** 2 + (a11 * s2) ** 2) / np.abs(det)
    M = np.stack([np.stack([a11, a12]), np.stack([a21, a22])])
    sv = np.linalg.svd(np.moveaxis(M, (0, 1), (-2, -1)), compute_uv=False)
    cond = sv[..., 0] / sv[..., 1]
    ok = np.isfinite(d).all(0) & (cond < COND_MAX)
    return {"label": "conditional_EU_estimate", "assumption": "ZERO_NORTH",
            "E": np.where(ok, E, np.nan), "U": np.where(ok, U, np.nan),
            "sigma_E": np.where(ok, sE, np.nan), "sigma_U": np.where(ok, sU, np.nan),
            "cond": cond, "status": np.where(ok, "inferred", "not_comparable")}


def north_leakage(L: np.ndarray) -> np.ndarray:
    """dE/du_N and dU/du_N: bias in the zero-north E/U solution per mm of true north motion.

    True d = L u. The solver inverts the E/U columns only, so bias = A_EU^-1 A_N u_N.
    """
    L = np.asarray(L, float)
    A = L[:, [0, 2]]
    return np.linalg.solve(A, L[:, 1])


def downslope_unit(aspect_rad: np.ndarray, slope_deg: np.ndarray) -> np.ndarray:
    """ENU unit vector pointing down the DEM slope. aspect: downslope azimuth clockwise from north."""
    b = np.radians(slope_deg)
    return np.stack([np.sin(aspect_rad) * np.cos(b), np.cos(aspect_rad) * np.cos(b), -np.sin(b)])


def slope_constrained(d: np.ndarray, L: np.ndarray, s_hat: np.ndarray, sigma: np.ndarray,
                      min_sensitivity: float = 0.2) -> dict:
    """Weighted LS magnitude m of motion along s_hat from k LOS values: d_i = m (l_i . s_hat) + e_i.

    With k = 2 there is one redundant observation: the weighted residual chi2 (1 dof) tests the
    slope-parallel hypothesis. Pixels where every |l . s| < min_sensitivity are not comparable
    (motion along s is nearly invisible to all geometries).
    d, sigma: (k, ...); L: (k, 3, ...) or (k, 3); s_hat: (3, ...)
    """
    d = np.asarray(d, float); sigma = np.asarray(sigma, float)
    L = np.asarray(L, float)
    if L.ndim == 2:
        L = L.reshape(L.shape[0], 3, *([1] * (d.ndim - 1)))
    g = np.sum(L * s_hat[None], axis=1)                                # (k, ...)
    w = 1.0 / sigma ** 2
    m = np.nansum(w * g * d, 0) / np.nansum(w * g * g, 0)
    sm = 1.0 / np.sqrt(np.nansum(w * g * g, 0))
    chi2 = np.nansum(w * (d - m * g) ** 2, 0)
    ok = np.isfinite(d).all(0) & (np.max(np.abs(g), 0) >= min_sensitivity)
    return {"label": "slope_constrained_estimate", "assumption": "SLOPE_CONSTRAINED",
            "magnitude": np.where(ok, m, np.nan), "sigma": np.where(ok, sm, np.nan),
            "chi2_1dof": np.where(ok, chi2, np.nan), "sensitivity": g,
            "status": np.where(ok, "inferred", "not_comparable")}
