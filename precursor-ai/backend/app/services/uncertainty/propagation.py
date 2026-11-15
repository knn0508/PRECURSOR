"""Uncertainty interfaces and the one analytic propagation with a cited formula.

Formula (distributed-scatterer Cramer-Rao lower bound on interferometric phase standard deviation; Rodriguez and Martin
1992, Just and Bamler 1994; see docs/scientific/UNCERTAINTY_AND_RELIABILITY.md):

    sigma_phi = (1 / sqrt(2 N)) * sqrt(1 - gamma^2) / gamma        [rad],   N independent looks, coherence gamma in (0, 1]
    sigma_d   = (lambda / (4 pi)) * sigma_phi                      [m]      LOS displacement (matches phase_to_displacement.py)

This is a LOWER BOUND for the phase noise of one interferogram. It excludes atmosphere, unwrapping errors, orbit and
reference-point errors, so it is NOT a total uncertainty and must be labelled as such. `n_looks` is caller-supplied (the
effective number of independent looks is not recorded by the products read so far).
"""
import math
from typing import Protocol, runtime_checkable

import numpy as np

from app.services.insar.phase_to_displacement import validate_wavelength

BOUND_LABEL = "Cramer-Rao lower bound for phase noise only; excludes atmosphere, unwrapping, orbit and reference errors"


@runtime_checkable
class UncertaintySource(Protocol):
    name: str

    def sigma(self) -> np.ndarray: ...  # 1-sigma, same units as the quantity it describes


@runtime_checkable
class Propagator(Protocol):
    def propagate(self, source: UncertaintySource) -> np.ndarray: ...


def phase_std_rad(coherence: np.ndarray, n_looks: float) -> np.ndarray:
    if not (math.isfinite(n_looks) and n_looks >= 1):
        raise ValueError("n_looks must be >= 1")
    g = np.asarray(coherence, dtype=np.float64)
    out = np.full(g.shape, np.nan)
    ok = np.isfinite(g) & (g > 0) & (g <= 1)  # gamma = 0 has unbounded variance: stays NaN (not estimated)
    out[ok] = np.sqrt(1.0 - g[ok] ** 2) / g[ok] / math.sqrt(2.0 * n_looks)
    return out


def los_displacement_std_m(coherence: np.ndarray, n_looks: float, wavelength_m: float) -> np.ndarray:
    return validate_wavelength(wavelength_m) / (4.0 * math.pi) * phase_std_rad(coherence, n_looks)
