"""Confidence-aware validity masks and A/B/C quality classes (skill Step 2).

A_observed_reliable    finite chained value AND accepted by the chosen mask configuration -> labels and inputs
B_observed_uncertain   finite chained value rejected by that configuration -> sensitivity analysis only, never a label
C_invalid_unobserved   no finite chained value -> excluded everywhere

Configurations use only layers present in our subsets (no phase_similarity / water_mask). Thresholds are
explicit arguments and are recorded in results/run_config.yaml.
"""
from __future__ import annotations

import numpy as np

A, B, C = 0, 1, 2
CLASS_NAMES = {A: "A_observed_reliable", B: "B_observed_uncertain", C: "C_invalid_or_unobserved"}


def mask_configs(cube: dict, finite: np.ndarray, conservative_tc=(0.7, 0.8), adaptive_tc=(0.5, 0.4)) -> dict:
    """Candidate validity masks [T, H, W] (bool). The original product mask is always included."""
    rec = cube["recommended_mask"] > 0.5
    tc = np.nan_to_num(cube["temporal_coherence"], nan=0.0)
    cc_ok = cube["connected_component_labels"] > 0
    out = {"original": rec & finite}
    for t in conservative_tc:
        out[f"conservative_tc{t}"] = rec & finite & (tc >= t)
    for t in adaptive_tc:
        out[f"adaptive_cc_tc{t}"] = finite & cc_ok & (tc >= t)       # relaxes the (unseen) similarity rule, keeps CC > 0
    return out


def qa_classes(valid_cfg: np.ndarray, finite: np.ndarray) -> np.ndarray:
    cls = np.full(valid_cfg.shape, C, np.int8)
    cls[finite & ~valid_cfg] = B
    cls[finite & valid_cfg] = A
    return cls
