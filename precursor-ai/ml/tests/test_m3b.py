"""M3b checks: SYNTHETIC geometry fixtures (labelled synthetic) and REAL-data products. Real-data tests skip when files are absent."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pyproj import Transformer
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))
from precursor_ml import m3, m3b  # noqa: E402

CFG = m3.load_config()
R2 = ROOT / "data/ml/raw/manifest_round2.json"
OUT = ROOT / "data/ml/interim/m3"
HAVE_R2 = R2.exists() and (OUT / "m3b_manifest.json").exists()


# ------------------------------------------------------------------ synthetic
def test_distance_stats_known_geometry():
    ref = m3.make_grid((-118.4, 34.0, -117.9, 34.5), 5000)
    g = ref.grid
    x_line = g.transform.c + 3.0 * 5000  # a vertical line on the boundary between cell columns 2 and 3
    line = LineString([(x_line, g.transform.f + 10000), (x_line, g.transform.f - g.height * 5000 - 10000)])
    mean, mn, n = m3b.distance_stats([line], ref)
    assert n == 1 and mean.shape == (g.height, g.width)
    assert abs(mean[5, 0] - 12500) < 300 and abs(mn[5, 0] - 10000) < 300  # column 0 spans 10..15 km from the line (mean 12.5 km, min 10 km)
    assert mn[5, 2] < 300 and mn[5, 3] < 300  # cells touching the line
    assert np.all(mean >= mn)
    none = m3b.distance_stats([], ref)
    assert np.isnan(none[0]).all() and none[2] == 0  # no line: NaN, never a made-up distance


def test_sinusoidal_tile_corner_matches_viirs_metadata():
    x, y = m3b.tile_origin(8, 5)
    lon, lat = Transformer.from_crs(m3b.SINU, 4326, always_xy=True).transform(x, y)
    assert abs(lon - (-130.540726)) < 1e-4 and abs(lat - 40.0) < 1e-6  # WestBoundingCoord / NorthBoundingCoord of tile h08v05 in the real file


def test_fault_and_river_rules_are_fixed_constants():
    assert m3b.MAJOR_UPLAND_SKM == 1000.0
    assert "late Quaternary" in m3b.YOUNG and "undifferentiated Quaternary" not in m3b.YOUNG


# ------------------------------------------------------------------ real data
@pytest.mark.skipif(not R2.exists(), reason="round 2 data not present")
def test_real_ndvi_granule_masks_water_and_fill():
    p = next((ROOT / "data/ml/raw/ndvi_viirs").glob("VNP13A3.A2013182.h08v05.*.h5"))
    a = m3b.read_ndvi_month(p)
    assert a.shape == (1200, 1200) and np.nanmin(a) >= -1 and np.nanmax(a) <= 1
    assert np.isnan(a).mean() > 0.1  # water/fill/low-reliability pixels are NaN, not 0 or -1.5


@pytest.mark.skipif(not R2.exists(), reason="round 2 data not present")
def test_round2_manifest_complete_and_hashes_match():
    import hashlib

    man = json.loads(R2.read_text())
    assert sum(k.startswith("ndvi_viirs/") for k in man) == 240
    assert sum(k.startswith("soilgrids/") and k.endswith(".tif") for k in man) == 528
    assert "hydrorivers/HydroRIVERS_v10_na_shp.zip" in man and "faults/Qfaults_GIS.zip" in man
    for key, m in man.items():
        p = m3.RAW / key
        assert p.exists() and p.stat().st_size == m["size_bytes"], key
        assert m["licence"] and m["retrieved_utc"] and "?" not in m["url"]
        assert m["size_bytes"] <= 1.10 * m["expected_size"] and m["size_bytes"] >= 0.90 * m["expected_size"], key  # user limit: +-10%
    # full re-hash of the two vector zips (cheap); the other files are hashed by the manifest builder at download time
    for key in ("hydrorivers/HydroRIVERS_v10_na_shp.zip", "faults/Qfaults_GIS.zip"):
        h = hashlib.sha256((m3.RAW / key).read_bytes()).hexdigest()
        assert h == man[key]["sha256"]


@pytest.mark.skipif(not HAVE_R2, reason="run ml/scripts/m3b_process.py first")
def test_round2_factors_plausible_and_aligned_to_m3_grid():
    full = pd.read_parquet(OUT / "cells_all_full.parquet")
    base = pd.read_parquet(OUT / "cells_all.parquet")
    assert len(full) == len(base) == 10276  # same cells as M3, merge is one-to-one
    d = [c for c in full.columns if c.startswith("dist_")]
    assert len(d) == 8 and (full[d].dropna() >= 0).all().all()
    for p in ("clay", "sand", "silt", "cfvo"):
        v = full[f"soil_{p}_0_30"].dropna()
        assert len(v) > 0.5 * len(full) and v.between(0, 100).all()
    assert "soil_bdod_0_30" not in full.columns  # bulk density was not acquired (HTTP 404 tiles): MISSING_FACTOR, not invented
    nd = full.ndvi_mean.dropna()
    assert len(nd) > 0.5 * len(full) and nd.between(0, 1).mean() > 0.99
    by = full.groupby("window").ndvi_mean.mean()
    assert by["OR_WA"] > by["CA_S"]  # forested Pacific North-West greener than southern California
    assert full.groupby("window").soil_clay_0_30.count().min() > 500


@pytest.mark.skipif(not HAVE_R2, reason="run ml/scripts/m3b_process.py first")
def test_round2_run_is_idempotent(tmp_path):
    cfg = m3.load_config()
    a = m3b.run_window_r2("CA_N", cfg["windows"]["CA_N"], cfg, tmp_path / "a")
    b = m3b.run_window_r2("CA_N", cfg["windows"]["CA_N"], cfg, tmp_path / "b")
    assert a["outputs"] == b["outputs"]  # byte-identical raster and table
    ref = json.loads((OUT / "m3b_manifest.json").read_text())["windows"]["CA_N"]["outputs_sha256"]
    assert a["outputs"] == ref  # equals the stored full run


@pytest.mark.skipif(not (ROOT / "data/ml/interim/m3_10km/m3b_manifest.json").exists(), reason="10 km round 2 not built")
def test_round2_10km_grid_consistent():
    m5 = json.loads((OUT / "m3b_manifest.json").read_text())
    m10 = json.loads((ROOT / "data/ml/interim/m3_10km/m3b_manifest.json").read_text())
    assert m10["cell_m"] == 10000 and m5["inputs"]["manifest_round2_sha256"] == m10["inputs"]["manifest_round2_sha256"]
    f5 = pd.read_parquet(OUT / "cells_all_full.parquet")
    f10 = pd.read_parquet(ROOT / "data/ml/interim/m3_10km/cells_all_full.parquet")
    assert abs(f5.groupby("window").ndvi_mean.mean() - f10.groupby("window").ndvi_mean.mean()).max() < 0.05  # coarsening keeps the broad pattern
    assert abs(f5.groupby("window").soil_clay_0_30.mean() - f10.groupby("window").soil_clay_0_30.mean()).max() < 3
