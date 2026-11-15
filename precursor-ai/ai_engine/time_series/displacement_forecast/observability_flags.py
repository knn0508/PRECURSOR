"""Observability and abstention flags for forecast outputs (skill v2, Step 5).

At an issue date, a pixel is
  observed_valid               finite and recommended_mask = 1  -> a forecast may be issued
  masked_but_finite_unreliable finite but masked                 -> abstain: "sensor limitation"
  missing                      no value                          -> abstain: "no observation"
A forecast is also withheld when the causal trend has too few past valid observations.
Masked-but-finite values are never turned into labels or inputs.
"""
from __future__ import annotations

import numpy as np

OBS, MASKED, MISSING = "observed_valid", "masked_but_finite_unreliable", "missing"


def issue_state(disp_t: np.ndarray, recmask_t: np.ndarray) -> np.ndarray:
    out = np.full(disp_t.shape, MISSING, dtype=object)
    fin = np.isfinite(disp_t)
    out[fin & (recmask_t > 0.5)] = OBS
    out[fin & ~(recmask_t > 0.5)] = MASKED
    return out


def abstain_reason(state: np.ndarray, n_hist: np.ndarray, min_hist: int) -> np.ndarray:
    r = np.full(state.shape, "", dtype=object)
    r[state == MASKED] = "sensor limitation (masked: CC=0 / low coherence)"
    r[state == MISSING] = "no observation"
    r[(state == OBS) & (n_hist < min_hist)] = "insufficient history"
    return r
