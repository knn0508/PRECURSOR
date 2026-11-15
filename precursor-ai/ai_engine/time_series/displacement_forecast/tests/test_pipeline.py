"""Pipeline mechanics on a labelled SYNTHETIC stack (not scientific results). Runs on CUDA when available."""
import numpy as np
import pytest
import torch

from displacement_forecast.pipeline import pick_device, run, save, synthetic_stack


@pytest.fixture(scope="module")
def res():
    return run(*synthetic_stack(), train_end="2019-06-01", val_end="2020-03-01", max_epochs=3, synthetic=True)


def test_runs_and_is_labelled_synthetic(res):
    assert res["meta"]["synthetic"] is True and "NOT A WARNING" in res["meta"]["label"]
    assert res["meta"]["device"] == pick_device()
    assert all(v > 0 for v in res["meta"]["splits"].values())


def test_forecast_quantiles_ordered_and_nan_not_zero(res):
    g = res["forecast"]
    ok = np.isfinite(g[1])
    assert ok.any() and (g[0][ok] <= g[1][ok] + 1e-5).all() and (g[1][ok] <= g[2][ok] + 1e-5).all()


def test_synthetic_run_writes_no_metrics(res, tmp_path):
    save(res, tmp_path)
    assert (tmp_path / "meta.json").exists() and not (tmp_path / "metrics.json").exists()


def test_bad_split_fails_loudly():
    with pytest.raises(ValueError, match="empty split"):
        run(*synthetic_stack(), train_end="2030-01-01", val_end="2031-01-01", max_epochs=1, synthetic=True)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA")
def test_cuda_run_matches_device(res):
    assert res["meta"]["device"] == "cuda"
