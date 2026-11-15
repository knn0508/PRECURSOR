"""Selection and calibration helpers that cannot see test outcomes (skill v2)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def select_on_validation(rows: pd.DataFrame, val_col: str) -> dict:
    """Pick the row with the lowest validation metric. Test columns are never read."""
    return rows.loc[rows[val_col].idxmin()].to_dict()


def conformal_groups(pred_abs: np.ndarray, moving: np.ndarray, edges) -> np.ndarray:
    """Inference-time group id from forecast-time quantities only (|predicted increment| bin x moving class)."""
    return moving.astype(int) * (len(edges) + 1) + np.digitize(pred_abs, edges)


def split_conformal(pred_val, y_val, pred_test, groups_val=None, groups_test=None, coverage=0.8):
    """Symmetric absolute-residual split conformal, optionally per group (Mondrian). Returns half-widths."""
    E = np.abs(y_val - pred_val)
    hw = np.zeros(len(pred_test)); counts = {}
    keys = np.unique(groups_val) if groups_val is not None else [None]
    for k in keys:
        mv = (groups_val == k) if groups_val is not None else np.ones(len(E), bool)
        mt = (groups_test == k) if groups_test is not None else np.ones(len(pred_test), bool)
        n = int(mv.sum()); counts[str(k)] = n
        if n == 0:
            continue
        hw[mt] = np.quantile(E[mv], min(1.0, np.ceil((n + 1) * coverage) / n))
    return hw, counts
