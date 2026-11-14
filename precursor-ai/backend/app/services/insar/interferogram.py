"""Wrapped interferogram from two CO-REGISTERED complex SLCs (e.g. two GSLC rasters on the same grid).

Phase here is WRAPPED to (-pi, pi]. It is not displacement: unwrapping needs an established external tool
(e.g. SNAPHU, ISCE, SNAP), which is not part of this repository's environment. This module is implemented
and unit-tested but intentionally NOT wired into the pipeline for real products (see docs/scientific/INSAR_METHODOLOGY.md).
"""
from __future__ import annotations

import numpy as np


def wrapped_interferogram(slc_ref: np.ndarray, slc_sec: np.ndarray) -> np.ndarray:
    """Complex interferogram s_ref * conj(s_sec)."""
    if slc_ref.shape != slc_sec.shape:
        raise ValueError("SLC arrays must have identical shape (co-registered)")
    if not (np.iscomplexobj(slc_ref) and np.iscomplexobj(slc_sec)):
        raise ValueError("inputs must be complex-valued SLCs")
    return slc_ref * np.conj(slc_sec)


def wrapped_phase(ifg: np.ndarray) -> np.ndarray:
    """Wrapped phase in radians; zero-amplitude pixels -> NaN (no phase information)."""
    ph = np.angle(ifg).astype(np.float64)
    ph[np.abs(ifg) == 0] = np.nan
    return ph


def wrap(phase: np.ndarray) -> np.ndarray:
    """Wrap any phase to (-pi, pi]."""
    return np.pi - np.mod(np.pi - np.asarray(phase, dtype=np.float64), 2 * np.pi)
