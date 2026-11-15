"""Backtest guards on the real saved model + real stack (skipped until static_terrain.npz exists)."""
import json

import numpy as np
import pandas as pd
import pytest
import torch

from displacement_forecast import backtest as B
from displacement_forecast import models as M
from displacement_forecast.saved_model import BUNDLE, load_scaler

pytestmark = pytest.mark.skipif(not (BUNDLE / "processed" / "static_terrain.npz").exists(), reason="static_terrain.npz not built")


def test_forecast_uses_nothing_after_the_issue_date():
    st, times, static, rain = B._load(BUNDLE)
    cum, valid, coh = st.cum_mm.values.copy(), st.valid.values.copy(), st.coherence.values.copy()
    sc, fidx, _ = load_scaler(BUNDLE / "artifacts" / "scaler.npz")
    net = M.build("lstm_tcn", 6, len(fidx), 6, False, 64, 0.1)
    net.load_state_dict(torch.load(BUNDLE / "artifacts" / "model.pt", map_location="cpu"))
    k = int(np.where(times == pd.Timestamp("2026-01-22"))[0][0])
    g1, _ = B.forecast_at(cum, valid, coh, times, static, rain, k, sc, fidx, net, "cpu")
    rng = np.random.default_rng(0)
    cum[k + 1:] = rng.normal(0, 500, cum[k + 1:].shape)      # destroy the future
    valid[k + 1:] = ~valid[k + 1:]
    coh[k + 1:] = 0.0
    g2, _ = B.forecast_at(cum, valid, coh, times, static, rain, k, sc, fidx, net, "cpu")
    assert np.array_equal(np.isfinite(g1), np.isfinite(g2)) and np.nanmax(np.abs(g1 - g2)) == 0.0


def test_saved_backtest_is_consistent_and_honest():
    p = BUNDLE / "backtest" / "backtest.json"
    if not p.exists():
        pytest.skip("backtest not run")
    m = json.loads(p.read_text())
    assert "NOT A WARNING" in m["label"] and "exploratory" in m["kind"] and m["pooled"]["n_pixels"] == sum(d["pixels_scored"] for d in m["per_date"])
    g = np.load(BUNDLE / "backtest" / "grids.npz")
    assert g["forecast"].shape[0] == len(m["issue_dates"]) == g["actual"].shape[0]
    assert all(d["horizon_days"] == 12.0 for d in m["per_date"]) and all(t > i for i, t in zip(m["issue_dates"], m["target_dates"]))
    assert m["issue_dates"][0] >= "2025-12-29" and m["target_dates"][-1] <= m["latest_data_date"]


def test_metrics_zero_forecast_equals_zero_baseline():
    y = np.array([1.0, -2.0, 3.0]); z = np.zeros(3)
    r = B._metrics(y, z, z - 1, z + 1, z, np.array([1.0, 2.0, 3.0]))
    assert r["MAE_model_mm"] == r["MAE_zero_mm"] and r["skill_vs_zero_pct"] == 0.0
