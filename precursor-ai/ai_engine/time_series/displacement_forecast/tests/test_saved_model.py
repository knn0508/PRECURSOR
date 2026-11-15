"""Real saved weights + real processed stack (no retraining). Skipped until static_terrain.npz exists (needs the approved DEM read)."""
import pytest

from displacement_forecast import saved_model as S

pytestmark = pytest.mark.skipif(not (S.BUNDLE / "processed" / "static_terrain.npz").exists(), reason="static_terrain.npz not built")


def test_reproduces_authors_forecast():
    r = S.verify()
    assert r["nan_pattern_equal"] and r["pixels_compared"] == 20184
    assert r["max_abs_diff_mm"] < 0.01   # author reports 0.0; GPU float noise is ~1e-3


def test_forecast_quantiles_ordered():
    import numpy as np
    g = S.forecast_last()["grid"]
    ok = np.isfinite(g[1])
    assert (g[0][ok] <= g[1][ok] + 1e-4).all() and (g[1][ok] <= g[2][ok] + 1e-4).all()
