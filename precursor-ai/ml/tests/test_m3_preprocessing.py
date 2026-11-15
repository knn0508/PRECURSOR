"""M3 checks: labelled SYNTHETIC fixtures (marked synthetic, never reported as results) and REAL-data windows.
Real-data tests skip when the M2 raw files / M3 interim products are absent."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))
from precursor_ml import m3  # noqa: E402

CFG = m3.load_config()
HAVE_RAW = (ROOT / "data/ml/raw/manifest.json").exists()
INTERIM = ROOT / "data/ml/interim/m3"
HAVE_M3 = (INTERIM / "m3_manifest.json").exists()


# ------------------------------------------------------------------ synthetic fixtures (SYNTHETIC)
def test_grid_is_metric_utm_and_snapped():
    for name, bbox in CFG["windows"].items():
        ref = m3.make_grid(bbox, 5000)
        assert ref.epsg in (32610, 32611) and ref.resolution_m == 5000
        t = ref.grid.transform
        assert t.c % 5000 == 0 and t.f % 5000 == 0 and t.a == 5000 and t.e == -5000
    assert m3.make_grid(CFG["windows"]["CA_S"], 5000).epsg == 32611  # zone from the centroid, not hard-coded
    assert m3.make_grid(CFG["windows"]["OR_WA"], 5000).epsg == 32610


def test_terrain_ramp_and_strip_seams_exact():
    # SYNTHETIC: 1 m rise per 1/3600 degree row; expected slope = atan(1 m / ~30.9 m)
    h, w = 420, 300
    mosaic = (np.arange(h, 0, -1, dtype=np.int16)[:, None] * np.ones((1, w), np.int16)).astype(np.int16)
    tr = m3.Affine(1 / 3600, 0, -118.0, 0, -1 / 3600, 34.0)
    s_small, a_small = m3.terrain_strips(mosaic, tr, band_rows=100)
    s_big, a_big = m3.terrain_strips(mosaic, tr, band_rows=1000)
    assert np.array_equal(np.nan_to_num(s_small, nan=-1), np.nan_to_num(s_big, nan=-1))  # halo makes strips identical
    assert np.array_equal(a_small, a_big)
    inner = s_big[5:-5, 5:-5]
    assert np.allclose(inner, math.degrees(math.atan(1 / 30.87)), atol=0.05)
    assert np.isnan(s_big[0]).all()  # border rows are NaN, never 0
    assert np.all(a_big[5:-5, 5:-5] == 1800)  # elevation falls southwards -> downslope aspect 180 deg (x10)


def test_nodata_stays_nan_not_zero():
    ref = m3.make_grid((-118.4, 34.0, -118.0, 34.3), 5000)
    mosaic = np.full((1500, 1500), m3.HGT_NODATA, np.int16)
    tr = m3.Affine(1 / 3600, 0, -118.5, 0, -1 / 3600, 34.5)
    out = m3.aggregate(mosaic, tr, "EPSG:4326", ref, m3.Resampling.average, m3.HGT_NODATA)
    assert np.isnan(out).all()


def test_lithology_mapping_total_on_real_vocabulary_and_detects_unmapped():
    assert set(m3.LITH_MAP.values()) <= set(m3.LITH_CLASSES)
    assert pd.Series(["Not a class"]).map(m3.LITH_MAP).isna().all()  # an unknown legend value would be reported, not guessed
    if not HAVE_RAW:
        pytest.skip("M2 geology not present")
    import pyogrio

    for st in ("CA", "OR", "WA"):
        df = pyogrio.read_dataframe(f"zip://{(m3.RAW / 'geology_state' / f'{st}.zip').as_posix()}!{st}_geol_poly.shp", read_geometry=False, columns=["GENERALIZE"])
        assert set(df.GENERALIZE.unique()) <= set(m3.LITH_MAP), sorted(set(df.GENERALIZE.unique()) - set(m3.LITH_MAP))


def _glc_row(lon, lat, acc, date="06/01/2010 12:00:00 AM"):
    return {"event_id": 1, "event_date": date, "longitude": lon, "latitude": lat, "location_accuracy": acc,
            "landslide_trigger": "rain", "landslide_category": "landslide", "event_description": "", "photo_link": "", "notes": ""}


def test_label_weights_and_radius_logic():
    bbox = (-118.4, 34.0, -117.9, 34.5)
    ref = m3.make_grid(bbox, 5000)
    glc = pd.DataFrame([_glc_row(-118.1, 34.2, "5km"), _glc_row(-118.1, 34.25, "exact"), _glc_row(-118.15, 34.3, "unknown")])
    glc["date"] = pd.to_datetime(glc.event_date, format="%m/%d/%Y %I:%M:%S %p")
    ev, cells = m3.build_events(bbox, ref, CFG, None, glc)
    assert list(ev.radius_m.fillna(-1)) == [5000, 0, -1]
    assert ev.strict_all_years.tolist() == [True, True, False]  # unknown accuracy is never "strict"
    lr = m3.label_rasters(ev, cells, ref)
    w = lr["label_weight_strict_all_years"]
    assert abs(float(w.sum()) - 2.0) < 1e-5  # every strict event distributes exactly weight 1
    assert lr["label_point_count_strict_all_years"].sum() == 2
    assert ev.n_cells_in_radius.iloc[1] == 1 and ev.n_cells_in_radius.iloc[0] > 1 and ev.label_ambiguous.iloc[0]
    assert cells[2] == []  # unknown accuracy: no cell is claimed


def test_prior_rain_excludes_event_month():
    # SYNTHETIC series: month k has value k mm at every cell; the event in month 5 must see months 4, 3, 2 only
    months = [pd.Timestamp(2010, m, 1, tz="UTC") for m in range(1, 13)]
    series = {"months": months, "precip_mm_month": np.arange(1, 13, dtype=np.float32)[:, None, None] * np.ones((12, 2, 2), np.float32),
              "lon": np.array([-118.05, -117.95]), "lat": np.array([34.25, 34.15])}
    ev = pd.DataFrame({"longitude": [-118.0], "latitude": [34.2], "date": [pd.Timestamp(2010, 5, 20)]})
    out = m3._attach_prior_rain(ev, series)
    assert out.rain_prev_1m_mm.iloc[0] == 4 and out.rain_prev_3m_mm.iloc[0] == 4 + 3 + 2
    ev2 = pd.DataFrame({"longitude": [-118.0], "latitude": [34.2], "date": [pd.Timestamp(2010, 1, 5)]})
    assert np.isnan(m3._attach_prior_rain(ev2, series).rain_prev_1m_mm.iloc[0])  # no earlier month available: NaN, not 0


# ------------------------------------------------------------------ real data
@pytest.mark.skipif(not HAVE_RAW, reason="M2 raw data not present")
def test_real_mini_window_idempotent_crs_and_nodata(tmp_path):
    bbox = (-118.4, 34.0, -117.9, 34.5)  # ~50 km window in the Los Angeles mountains, inside the approved CA_S data
    a = m3.run_window("MINI", bbox, CFG, out_root=tmp_path / "a")
    b = m3.run_window("MINI", bbox, CFG, out_root=tmp_path / "b")
    import rasterio

    assert a["outputs"]["static_factors.tif"] == b["outputs"]["static_factors.tif"]  # idempotent, byte-identical rasters
    assert a["outputs"]["labels_grid.tif"] == b["outputs"]["labels_grid.tif"]
    with rasterio.open(tmp_path / "a/MINI/static_factors.tif") as d:
        assert d.crs.to_epsg() == 32611 and d.transform.a == 5000 and d.transform.c % 5000 == 0 and d.nodata is not None and np.isnan(d.nodata)
        names = list(d.descriptions)
        z = d.read(names.index("elev_mean") + 1)
        ins = d.read(names.index("inside_aoi") + 1)
        s = d.read(names.index("slope_mean") + 1)
    assert 0 < np.nanmin(z[ins == 1]) < np.nanmax(z[ins == 1]) < 3100  # metres, plausible for the San Gabriel mountains
    assert 0 < np.nanmean(s[ins == 1]) < 45
    assert np.isnan(z[ins == 0]).all()  # outside the window: NaN, never 0
    assert a["lithology"]["unmapped_generalize_values"] == []


# ------------------------------------------------------------------ full-run products
@pytest.mark.skipif(not HAVE_M3, reason="run ml/scripts/m3_preprocess.py first")
def test_full_run_matches_census_and_physical_sanity():
    m = json.loads((INTERIM / "m3_manifest.json").read_text())
    strict_all = sum(w["events_strict_all_years"] for w in m["windows"].values())
    strict_in = sum(w["events_strict_in_period"] for w in m["windows"].values())
    assert (strict_all, strict_in) == (667, 304)  # M1 census numbers for the three windows
    cells = pd.read_parquet(INTERIM / "cells_all.parquet")
    by = cells.groupby("window").rain_map_mm.mean()
    assert by["OR_WA"] > by["CA_S"]  # Pacific Northwest wetter than southern California (orientation sanity check)
    assert cells[["slope_mean", "elev_mean"]].notna().mean().min() > 0.9
    assert (cells.lc_valid_frac.dropna() <= 1.0001).all()
    lith = [c for c in cells.columns if c.startswith("lith_") and c != "lith_cover"]
    tot = cells[lith].sum(axis=1, min_count=1).dropna()
    assert np.allclose(tot, 1.0, atol=1e-3)  # class shares of the covered area add up to 1


@pytest.mark.skipif(not HAVE_M3, reason="run ml/scripts/m3_preprocess.py first")
def test_manifest_records_inputs_config_and_missing_factors():
    m = json.loads((INTERIM / "m3_manifest.json").read_text())
    assert m["config_sha256"] == CFG["_sha256"]
    assert len(m["inputs"]["files"]) == 237 and m["code_version"]["git_commit"]
    assert "InSAR/SAR (LOS displacement, coherence, velocity, time series windows)" in m["not_available_factors"]
    raw = json.loads((m3.RAW / "manifest.json").read_text())
    assert m["inputs"]["raw_manifest_sha256"] == m3.sha256_file(m3.RAW / "manifest.json") and set(m["inputs"]["files"]) == set(raw)


@pytest.mark.skipif(not (ROOT / "data/ml/interim/m3_10km/m3_manifest.json").exists(), reason="10 km sensitivity grid not built")
def test_sensitivity_grid_10km_same_inputs_coarser_cells():
    m5 = json.loads((INTERIM / "m3_manifest.json").read_text())
    m10 = json.loads((ROOT / "data/ml/interim/m3_10km/m3_manifest.json").read_text())
    assert m10["cell_m"] == 10000 and m5["inputs"]["raw_manifest_sha256"] == m10["inputs"]["raw_manifest_sha256"]
    for n in m5["windows"]:
        a, b = m5["windows"][n], m10["windows"][n]
        assert (a["events_strict_all_years"], a["events_strict_in_period"]) == (b["events_strict_all_years"], b["events_strict_in_period"])  # same labels
        assert 3 < a["cells_inside"] / b["cells_inside"] < 5  # about 4x fewer cells
    c5, c10 = pd.read_parquet(INTERIM / "cells_all.parquet"), pd.read_parquet(ROOT / "data/ml/interim/m3_10km/cells_all.parquet")
    assert abs(c5.groupby("window").rain_map_mm.mean() - c10.groupby("window").rain_map_mm.mean()).max() < 60  # coarsening keeps the broad climate
