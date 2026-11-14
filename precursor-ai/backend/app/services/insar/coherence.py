"""Coherence validation and statistics. Coherence magnitude is dimensionless and must lie in [0, 1].

No universal "good coherence" threshold exists (it depends on land cover, wavelength, baseline and
processing). Any threshold is caller-supplied and recorded; the default is NO masking.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Allowed slack for float rounding in producer output; larger excursions are treated as invalid, not clipped.
_EPS = 1e-3


def valid_coherence_mask(coh: np.ndarray, fill_value: float | None = None) -> np.ndarray:
    """True where the value is finite, not the fill value and inside [0, 1]."""
    c = np.asarray(coh)
    ok = np.isfinite(c) & (c >= -_EPS) & (c <= 1 + _EPS)
    if fill_value is not None and np.isfinite(fill_value):
        ok &= c != fill_value
    return ok


@dataclass
class CoherenceAccumulator:
    """Online statistics so large rasters can be processed block by block."""

    count: int = 0
    total: int = 0
    invalid: int = 0
    s: float = 0.0
    lo: float = float("inf")
    hi: float = float("-inf")
    below: int = 0
    threshold: float | None = None

    def update(self, coh: np.ndarray, fill_value: float | None = None) -> np.ndarray:
        ok = valid_coherence_mask(coh, fill_value)
        vals = np.asarray(coh, dtype=np.float64)[ok]
        self.total += ok.size
        self.invalid += int(ok.size - vals.size)
        if vals.size:
            self.count += vals.size
            self.s += float(vals.sum())
            self.lo = min(self.lo, float(vals.min()))
            self.hi = max(self.hi, float(vals.max()))
            if self.threshold is not None:
                self.below += int((vals < self.threshold).sum())
        return ok

    def result(self) -> dict:
        return {
            "valid_pixels": self.count,
            "invalid_pixels": self.invalid,
            "mean": (self.s / self.count) if self.count else None,
            "min": self.lo if self.count else None,
            "max": self.hi if self.count else None,
            "threshold": self.threshold,
            "fraction_below_threshold": (self.below / self.count) if (self.count and self.threshold is not None) else None,
            "unit": "dimensionless (0-1)",
        }


def estimate_coherence(slc1: np.ndarray, slc2: np.ndarray, window: int = 5) -> np.ndarray:
    """Sample coherence magnitude |<s1 s2*>| / sqrt(<|s1|^2><|s2|^2>) over a boxcar window (box filter, numpy only).

    For co-registered complex SLCs (e.g. two GSLC grids on the same geocoded grid). The estimator is biased
    high for small windows; the window is a documented parameter, not a tuned one. Pixels with zero power -> NaN.
    """
    if slc1.shape != slc2.shape:
        raise ValueError("SLC arrays must have identical shape (co-registered)")
    if window < 1 or window % 2 == 0:
        raise ValueError("window must be a positive odd integer")
    cross = slc1 * np.conj(slc2)
    p1 = np.abs(slc1) ** 2
    p2 = np.abs(slc2) ** 2
    num = np.abs(_boxcar(cross, window))
    den = np.sqrt(_boxcar(p1, window) * _boxcar(p2, window))
    with np.errstate(divide="ignore", invalid="ignore"):
        coh = np.where(den > 0, num / den, np.nan)
    return np.clip(coh, 0.0, 1.0)


def _boxcar(a: np.ndarray, w: int) -> np.ndarray:
    """Mean over a w x w window with edge replication, via cumulative sums (O(N))."""
    pad = w // 2
    p = np.pad(a, pad, mode="edge")
    c = np.cumsum(np.cumsum(p, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    s = c[w:, w:] - c[:-w, w:] - c[w:, :-w] + c[:-w, :-w]
    return s / (w * w)
