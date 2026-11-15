"""M4 tests: each cleaning rule and each leakage check on labelled SYNTHETIC fixtures (never reported as results), plus real-data checks
on the cleaned dataset (skipped when data/ml/processed/m4 is absent)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))
from precursor_ml import m3, m4  # noqa: E402

CFG = m4.load_config()
OUT = ROOT / "data/ml/processed/m4"
HAVE = (OUT / "5km/m4_manifest.json").exists()
TODAY = pd.Timestamp("2026-11-15")


# ------------------------------------------------------------------ fixtures (SYNTHETIC)
def _ev(**kw):
    base = {"window": "W", "row": 1, "col": 1, "x_m": 1000.0, "y_m": 1000.0, "event_id": 1, "event_date": "06/01/2010 12:00:00 AM", "date": pd.Timestamp("2010-06-01"),
            "created_date": "04/01/2014 12:00:00 AM", "submitted_date": "04/01/2014 12:00:00 AM", "latitude": 34.2, "longitude": -118.1, "acc": "1km", "radius_m": 1000.0,
            "landslide_trigger": "rain", "landslide_category": "landslide", "usable_base": True}
    base.update(kw)
    return base


def _cells(ocean=False):
    return pd.DataFrame({"window": ["W"], "row": [1], "col": [1], "lc_valid_frac": [0.0 if ocean else 1.0], "elev_max": [-3.0 if ocean else 500.0], "dem_cover": [1.0]})


def _clean(rows, ocean=False):
    return m4.clean_labels(pd.DataFrame(rows), _cells(ocean), CFG, TODAY)


def test_date_problems_flagged_and_excluded():
    out = _clean([_ev(event_id=1, date=pd.NaT, event_date=""), _ev(event_id=2, date=pd.Timestamp("2030-01-01"), event_date="01/01/2030 12:00:00 AM"),
                  _ev(event_id=3, date=pd.Timestamp("1970-01-01"), event_date="01/01/1970 12:00:00 AM"), _ev(event_id=4, event_date="13/05/2010 12:00:00 AM"),
                  _ev(event_id=5, date=pd.Timestamp("2015-01-01"), event_date="01/01/2015 12:00:00 AM"), _ev(event_id=6, x_m=90000.0)])
    f = out.set_index("event_id")
    assert f.at[1, "flag_date_missing"] and f.at[2, "flag_date_future"] and f.at[3, "flag_date_implausible"] and f.at[4, "flag_date_dayfirst_suspect"]
    assert f.at[5, "flag_date_after_report"]  # event dated after the report that describes it (created 2014)
    assert not f.loc[[1, 2, 3, 4, 5], "clean_usable_base"].any() and f.at[6, "clean_usable_base"]


def test_coordinates_and_ocean():
    out = _clean([_ev(event_id=1, latitude=0.0, longitude=0.0), _ev(event_id=2, latitude=95.0)]).set_index("event_id")
    assert out.at[1, "flag_coords_invalid"] and out.at[2, "flag_coords_invalid"] and not out.clean_usable_base.any()
    ocean = _clean([_ev(event_id=1)], ocean=True)
    assert ocean.flag_in_ocean_cell.iloc[0] and not ocean.clean_usable_base.iloc[0]


def test_duplicates_exact_and_near_keep_lowest_id():
    out = _clean([_ev(event_id=10), _ev(event_id=11),  # exact: same coordinates, same day
                  _ev(event_id=12, x_m=1500.0, latitude=34.2004, longitude=-118.1004),  # near: 500 m away, same day
                  _ev(event_id=13, x_m=9000.0, latitude=34.3, longitude=-118.2),  # 8 km away: distinct
                  _ev(event_id=14, date=pd.Timestamp("2010-06-02"), event_date="06/02/2010 12:00:00 AM")]).set_index("event_id")  # other day
    assert out.at[11, "duplicate_of"] == 10 and out.at[11, "dup_type"] == "exact"
    assert out.at[12, "duplicate_of"] == 10 and out.at[12, "dup_type"] == "near"
    assert pd.isna(out.at[10, "duplicate_of"]) and pd.isna(out.at[13, "duplicate_of"]) and pd.isna(out.at[14, "duplicate_of"])
    assert out.loc[[10, 13, 14], "clean_usable_base"].all() and not out.loc[[11, 12], "clean_usable_base"].any()


def test_accuracy_type_trigger_rules_and_reversibility():
    rows = [_ev(event_id=1, acc="unknown", radius_m=np.nan), _ev(event_id=2, acc="10km", radius_m=10000.0, x_m=50000.0), _ev(event_id=3, landslide_trigger="earthquake", x_m=90000.0),
            _ev(event_id=4, landslide_category="snow_avalanche", x_m=130000.0), _ev(event_id=5, x_m=170000.0)]
    inp = pd.DataFrame(rows)
    out = m4.clean_labels(inp, _cells(), CFG, TODAY).set_index("event_id")
    assert out.at[1, "excl_accuracy_unknown"] and not out.at[1, "clean_strict_all_years"]
    assert out.at[2, "excl_accuracy_above_strict"] and out.at[2, "clean_usable_base"] and not out.at[2, "clean_strict_all_years"]  # kept as relaxed, not strict
    assert "trigger:earthquake" in out.at[3, "exclusion_reasons"] and not out.at[3, "clean_usable_base"]
    assert "category:snow_avalanche" in out.at[4, "exclusion_reasons"] and not out.at[4, "clean_usable_base"]
    assert out.at[5, "clean_strict_all_years"] and out.at[5, "exclusion_reasons"] == ""
    assert len(out) == len(inp)  # nothing deleted: every row stays with its reasons (reversible)
    for c in inp.columns:  # original values untouched
        assert out.reset_index()[c].astype(str).tolist() == inp[c].astype(str).tolist() or c in ("row", "col")


def test_cell_exclusion_is_outcome_blind_and_objective():
    cells = pd.DataFrame({"window": "W", "row": [0, 1, 2, 3], "col": 0, "lc_valid_frac": [1.0, 0.0, 1.0, 0.0], "lc_water": [0.0, np.nan, 0.8, np.nan],
                          "dem_cover": [1.0, 1.0, 1.0, 0.2], "soil_cover": [1.0, 0.0, 0.5, 0.0]})
    ex = m4.cell_exclusion(cells)
    assert ex.excluded.tolist() == [False, True, True, True]
    assert "water_ocean" in ex.exclusion_reason[1] and "water_ocean" in ex.exclusion_reason[2] and "no_elevation" in ex.exclusion_reason[3]
    cells2 = cells.assign(label_point_count_strict_all_years=[5, 0, 9, 0], any_event_nearby=True)  # labels present: result must not change
    assert m4.cell_exclusion(cells2).equals(ex)
    shuffled = cells2.assign(label_point_count_strict_all_years=[0, 7, 0, 7])
    assert m4.cell_exclusion(shuffled).equals(ex)


def test_background_outside_buffer_stratified_seeded():
    n = 20
    cells = pd.DataFrame({"window": "W", "row": np.repeat(np.arange(n), n), "col": np.tile(np.arange(n), n)})
    cells["x_m"], cells["y_m"] = cells.col * 5000.0 + 2500, cells.row * 5000.0 + 2500
    cells["slope_mean"] = np.linspace(0, 30, len(cells))
    cells["excluded"] = False
    cells.loc[:19, "excluded"] = True  # first row of cells excluded
    ev = pd.DataFrame({"window": "W", "x_m": [50000.0], "y_m": [50000.0], "radius_m": [5000.0], "usable_for_buffer": [True]})
    a = m4.sample_background(cells, ev, 5000.0, CFG, {"W": 10}, 7)
    b = m4.sample_background(cells, ev, 5000.0, CFG, {"W": 10}, 7)
    c = m4.sample_background(cells, ev, 5000.0, CFG, {"W": 10}, 8)
    assert a.equals(b) and not a.selected.equals(c.selected)  # seeded and reproducible
    half = 2500.0
    dx, dy = np.maximum(np.abs(a.x_m - 50000.0) - half, 0), np.maximum(np.abs(a.y_m - 50000.0) - half, 0)
    assert (np.hypot(dx, dy) > 10000.0).all()  # whole cell outside 2 x 5 km
    assert not a.merge(cells[cells.excluded][["row", "col"]], on=["row", "col"]).shape[0]  # excluded cells never sampled
    assert a.selected.sum() == 50 and set(a[a.selected].stratum) == set(range(CFG["background"]["n_strata"]))  # ratio 5 x 10 events, every terrain stratum used
    q = a[a.selected].groupby("stratum").size()
    assert q.max() - q.min() <= 12  # quotas follow the candidate share per stratum


def test_background_reports_shortfall():
    cells = pd.DataFrame({"window": "W", "row": [0, 0, 1], "col": [0, 1, 0], "x_m": [2500.0, 7500.0, 2500.0], "y_m": [2500.0, 2500.0, 7500.0], "slope_mean": [1.0, 2.0, 3.0], "excluded": False})
    ev = pd.DataFrame({"window": "W", "x_m": [-100000.0], "y_m": [-100000.0], "radius_m": [0.0], "usable_for_buffer": [True]})  # far away: all 3 cells are candidates
    r = m4.sample_background(cells, ev, 5000.0, CFG, {"W": 100}, 1)
    assert r.shortfall.iloc[0] > 0 and len(r) <= 3  # asked for far more than available: reported, never padded


# ------------------------------------------------------------------ leakage checks (pass and fail cases)
def _split_df():
    return pd.DataFrame({"window": "W", "x_m": [0.0, 1000.0, 50000.0, 60000.0], "y_m": 0.0, "split": ["train", "train", "test", "test"]})


def test_leak_spatial_proximity_pass_and_fail():
    ok = m4.check_spatial_proximity(_split_df(), "split", 20000)
    assert ok["pass"] and ok["min_train_test_distance_m"] == 49000
    bad = _split_df().assign(x_m=[0.0, 1000.0, 5000.0, 60000.0])  # a test point 4 km from a train point
    assert not m4.check_spatial_proximity(bad, "split", 20000)["pass"]


def test_leak_temporal_order_pass_and_fail():
    d = pd.DataFrame({"date": pd.to_datetime(["2010-01-01", "2011-01-01", "2013-01-01"]), "s": ["train", "train", "test"]})
    assert m4.check_temporal_order(d, "s", pd.Timestamp("2012-01-01"))["pass"]
    d.loc[2, "date"] = pd.Timestamp("2011-06-01")  # test event before the cutoff
    d.loc[1, "date"] = pd.Timestamp("2013-06-01")  # train event after the cutoff
    assert not m4.check_temporal_order(d, "s", pd.Timestamp("2012-01-01"))["pass"]


def test_leak_future_information_detects_late_data():
    r = m4.check_future_information(["terrain", "ndvi", "land_cover"], pd.Timestamp("2016-12-31"))
    assert r["status"] == "WARN" and {g["group"] for g in r["groups_with_data_after_cutoff"]} == {"ndvi", "land_cover"}
    assert m4.check_future_information(["terrain"], pd.Timestamp("2016-12-31"))["status"] == "PASS"
    assert m4.check_future_information(["ndvi"], pd.Timestamp("2018-01-01"))["status"] == "PASS"


def test_leak_duplicates_and_prior_rain():
    d = pd.DataFrame({"window": "W", "row": [0, 0], "col": [1, 1]})
    assert not m4.check_duplicates(d, ["window", "row", "col"])["pass"] and m4.check_duplicates(d.iloc[:1], ["window", "row", "col"])["pass"]
    ev = pd.DataFrame({"date": pd.to_datetime(["2000-01-01", "2005-01-01"]), "rain_prev_1m_mm": [np.nan, 10.0]})
    assert m4.check_prior_rain_strictly_before(ev)["pass"]
    assert not m4.check_prior_rain_strictly_before(ev.assign(rain_prev_1m_mm=[5.0, 10.0]))["pass"]  # a value before the record would be invented


def test_leak_target_derived_feature_detected():
    rng = np.random.default_rng(0)
    n = 400
    y = (rng.random(n) < 0.2).astype(float)
    cells = pd.DataFrame({"slope_mean": rng.normal(size=n), "ndvi_mean": rng.normal(size=n), "label_point_count": y})
    assert m4.check_target_derived(cells, ["label_point_count"], "label_point_count")["pass"]
    leaky = cells.assign(slope_mean=y * 10 + rng.normal(scale=0.1, size=n))  # a feature that encodes the target
    r = m4.check_target_derived(leaky, ["label_point_count"], "label_point_count")
    assert not r["pass"] and r["max_single_feature_auc"] > 0.9
    named = cells.rename(columns={"slope_mean": "elev_mean"}).assign(**{"dist_label_point_count": y})
    assert m4.check_target_derived(named.assign(label_point_count=y), ["dist_label_point_count"], "label_point_count")["feature_label_name_overlap"] == ["dist_label_point_count"]


def test_provisional_split_respects_gap_and_cutoff():
    rng = np.random.default_rng(3)
    ev = pd.DataFrame({"window": "W", "x_m": rng.uniform(0, 300000, 200), "y_m": rng.uniform(0, 300000, 200), "date": pd.to_datetime("2010-01-01") + pd.to_timedelta(rng.integers(0, 3000, 200), unit="D")})
    e, cutoff = m4.provisional_split(ev, CFG, 5)
    assert m4.check_spatial_proximity(e[e.split_spatial != "gap"], "split_spatial", CFG["audit"]["gap_m"])["pass"]
    assert m4.check_temporal_order(e, "split_temporal", cutoff)["pass"]


# ------------------------------------------------------------------ NDVI QC and policy
def test_ndvi_qc_detects_disagreement():
    man = {k: v for k, v in json.loads((m3.RAW / "manifest_round2.json").read_text()).items() if k.startswith("ndvi_viirs/")} if (m3.RAW / "manifest_round2.json").exists() else None
    if not man:
        pytest.skip("round 2 data not present")
    one = {k: man[k] for k in list(man)[:3]}
    assert m4.ndvi_georef_qc(one).ok.all()
    assert not m4.ndvi_georef_qc(one, tol_deg=1e-6).ok.any()  # the constant ~0.01 degree East-edge convention offset is visible when the tolerance is tightened
    wrong_month = {k: {**v, "start": "1999-01-01T00:00:00Z"} for k, v in one.items()}
    assert not m4.ndvi_georef_qc(wrong_month).ok.any()


def test_missing_policy_covers_every_real_feature_group():
    p = ROOT / "data/ml/interim/m3/cells_all_full.parquet"
    if not p.exists():
        pytest.skip("M3 products not present")
    feats = m4.feature_columns(pd.read_parquet(p))
    assert len(feats) == 72 and all(m4.group_of(f) in m4.POLICY for f in feats) and "labels" in m4.POLICY
    assert all(m4.range_for(f) is not None for f in feats)


# ------------------------------------------------------------------ real cleaned dataset
@pytest.mark.skipif(not HAVE, reason="run ml/scripts/m4_clean.py first")
def test_cleaned_dataset_is_reversible_hashed_and_consistent():
    for grid, ncells in (("5km", 10276), ("10km", 2571)):
        d = OUT / grid
        man = json.loads((d / "m4_manifest.json").read_text())
        log = json.loads((d / "cleaning_log.json").read_text())
        cells, ev = pd.read_parquet(d / "cells_clean.parquet"), pd.read_parquet(d / "events_clean.parquet")
        assert len(cells) == ncells and len(ev) == log["rows_events_in"] == 1215  # all rows kept (flags only)
        assert int(cells.excluded.sum()) == log["cells_excluded"] == len(pd.read_parquet(d / "excluded_cells.parquet"))
        assert int(ev.clean_strict_all_years.sum()) == log["events_clean_strict_all_years"] == 647 and log["events_before_cleaning_strict_all_years"] == 667
        for name, h in man["outputs_sha256"].items():
            assert m3.sha256_file(d / name) == h, name
        assert man["inputs"]["cells_all_full.parquet"] == m3.sha256_file((m3.INTERIM if grid == "5km" else m3.INTERIM.parent / "m3_10km") / "cells_all_full.parquet")  # M3 inputs untouched
        assert ev[ev.clean_strict_all_years].exclusion_reasons.isin(["", "cell_outside_study_mask"]).all()  # only the informational mask note
        removed = ev[ev.strict_all_years & ~ev.clean_strict_all_years]
        assert removed.exclusion_reasons.str.len().gt(0).all()  # every removed strict event has a recorded reason
        bg = pd.read_parquet(d / "background_candidates.parquet")
        assert not bg.merge(cells[cells.excluded][["window", "row", "col"]], on=["window", "row", "col"]).shape[0]
        res = json.loads((d / "leakage_audit.json").read_text())["results"]
        warn = [r for r in res if r.get("status") == "WARN"]
        assert len(warn) == 1 and {g["group"] for g in warn[0]["groups_with_data_after_cutoff"]} == {"land_cover", "ndvi", "rainfall_climatology", "soil"}  # a new future-dated group must fail here
        assert all(r["pass"] for r in res if "pass" in r)


@pytest.mark.skipif(not HAVE, reason="run ml/scripts/m4_clean.py first")
def test_cleaning_is_idempotent_and_outcome_blind_on_real_data(tmp_path):
    a = m4.run_grid(m3.INTERIM, tmp_path / "a", 5000, CFG)
    b = m4.run_grid(m3.INTERIM, tmp_path / "b", 5000, CFG)
    ha = json.loads((tmp_path / "a/m4_manifest.json").read_text())["outputs_sha256"]
    hb = json.loads((tmp_path / "b/m4_manifest.json").read_text())["outputs_sha256"]
    assert ha == hb == json.loads((OUT / "5km/m4_manifest.json").read_text())["outputs_sha256"] and a["cells_excluded"] == b["cells_excluded"]
    # the exclusion uses features only: recomputing it from the label-free table gives the stored decision
    cells = pd.read_parquet(m3.INTERIM / "cells_all_full.parquet")
    ex = m4.cell_exclusion(cells.drop(columns=[c for c in cells.columns if c.startswith("label_")]))
    stored = pd.read_parquet(OUT / "5km/cells_clean.parquet")
    assert ex.excluded.tolist() == stored.excluded.tolist()


# ------------------------------------------------------------------ fixes from the code review
def test_near_duplicates_do_not_chain():
    # A-B 800 m, B-C 800 m: C is 1,600 m from A and must NOT be merged into A (single linkage would do it)
    out = _clean([_ev(event_id=1, x_m=0.0), _ev(event_id=2, x_m=800.0), _ev(event_id=3, x_m=1600.0)]).set_index("event_id")
    assert pd.isna(out.at[1, "duplicate_of"]) and out.at[2, "duplicate_of"] == 1
    assert pd.isna(out.at[3, "duplicate_of"]) and out.at[3, "clean_usable_base"]  # 800 m from B, but B is itself a duplicate, so C is kept (1,600 m from A)


def test_rejected_row_cannot_remove_valid_duplicates():
    # id 1 has the lowest id but is rejected (earthquake); the valid events 2 and 3 are real duplicates of each other, 2 stays
    out = _clean([_ev(event_id=1, landslide_trigger="earthquake"), _ev(event_id=2), _ev(event_id=3)]).set_index("event_id")
    assert pd.isna(out.at[1, "duplicate_of"]) and pd.isna(out.at[2, "duplicate_of"]) and out.at[3, "duplicate_of"] == 2
    assert out.at[2, "clean_usable_base"] and not out.at[3, "clean_usable_base"]


def test_future_date_rule_uses_config_as_of_not_wall_clock():
    assert CFG["as_of_date"] == "2026-11-15"
    out = m4.clean_labels(pd.DataFrame([_ev(event_id=1, date=pd.Timestamp("2026-11-16"), event_date="11/16/2026 12:00:00 AM")]), _cells(), CFG)  # no `today` argument
    assert out.flag_date_future.iloc[0]


def test_prior_rain_check_covers_every_rain_prev_column():
    ev = pd.DataFrame({"date": pd.to_datetime(["2000-01-01"]), "rain_prev_1m_mm": [np.nan], "rain_prev_3m_mm": [12.0]})
    assert not m4.check_prior_rain_strictly_before(ev)["pass"]  # a value in the 3-month column before the record must fail


def test_target_derived_scans_columns_without_known_prefix():
    rng = np.random.default_rng(1)
    n = 400
    y = (rng.random(n) < 0.2).astype(float)
    cells = pd.DataFrame({"slope_mean": rng.normal(size=n), "mystery_column": y * 5 + rng.normal(scale=0.05, size=n), "label_point_count": y})
    r = m4.check_target_derived(cells, ["label_point_count"], "label_point_count")
    assert not r["pass"] and r["max_single_feature_auc"] > 0.9  # found although the name has no feature prefix


def test_background_flags_candidates_inside_imprecise_circles():
    n = 20
    cells = pd.DataFrame({"window": "W", "row": np.repeat(np.arange(n), n), "col": np.tile(np.arange(n), n)})
    cells["x_m"], cells["y_m"] = cells.col * 5000.0 + 2500, cells.row * 5000.0 + 2500
    cells["slope_mean"] = np.linspace(0, 30, len(cells))
    cells["excluded"] = False
    ev = pd.DataFrame({"window": "W", "x_m": [20000.0, 80000.0], "y_m": [20000.0, 80000.0], "radius_m": [1000.0, 25000.0], "usable_for_buffer": [True, False]})  # the 25 km event does not shield
    bg = m4.sample_background(cells, ev, 5000.0, CFG, {"W": 10}, 3)
    assert "background_in_imprecise_circle" in bg
    d = np.hypot(np.maximum(np.abs(bg.x_m - 80000.0) - 2500, 0), np.maximum(np.abs(bg.y_m - 80000.0) - 2500, 0))
    assert (bg.background_in_imprecise_circle == (d <= 25000.0)).all() and bg.background_in_imprecise_circle.any()  # flagged exactly when the cell touches the 25 km circle
    assert not bg.background_in_imprecise_circle.all()


def test_unknown_trigger_sensitivity_set_is_separate_and_flagged():
    out = _clean([_ev(event_id=1, landslide_trigger="unknown"), _ev(event_id=2, x_m=50000.0), _ev(event_id=3, landslide_trigger="earthquake", x_m=90000.0)]).set_index("event_id")
    assert out.at[1, "unknown_trigger"] and not out.at[1, "clean_strict_all_years"] and out.at[1, "clean_strict_all_years_sens"]  # excluded from the primary, in the sensitivity set
    assert out.at[2, "clean_strict_all_years"] and out.at[2, "clean_strict_all_years_sens"]  # primary events stay in the sensitivity set
    assert not out.at[3, "clean_strict_all_years_sens"]  # other non-rain triggers stay excluded in both


def test_unknown_trigger_duplicates_use_the_same_greedy_rule_in_the_sensitivity_set_only():
    out = _clean([_ev(event_id=1, landslide_trigger="unknown"), _ev(event_id=2)]).set_index("event_id")  # same place and day, lowest id is an unknown-trigger event
    assert pd.isna(out.at[2, "duplicate_of"]) and out.at[2, "clean_strict_all_years"]  # primary: the unknown row never competes
    assert out.at[2, "duplicate_of_sens"] == 1 and not out.at[2, "clean_strict_all_years_sens"]  # sensitivity: lowest id kept, same rule


def test_primary_background_buffers_and_literal_record_on_real_data():
    if not HAVE:
        pytest.skip("run ml/scripts/m4_clean.py first")
    assert CFG["background"]["buffer_events_max_radius_m"] == 10000 and CFG["background"]["imprecise_radius_m"] == 10000  # user decision 2026-11-15
    log = json.loads((OUT / "5km/cleaning_log.json").read_text())
    assert log["background_candidates"] == 4772 and log["background_candidates_by_window"] == {"CA_N": 2209, "CA_S": 1386, "OR_WA": 1177}
    assert log["background_literal_rule"]["candidates"] == 1319 < log["background_candidates"]  # the literal every-event rule is kept for the record
    assert (OUT / "5km/background_candidates_literal_rule.parquet").exists() and not (OUT / "5km/background_candidates_variant_buffer_le10km.parquet").exists()
    cells = pd.read_parquet(OUT / "5km/cells_clean.parquet")
    ev = pd.read_parquet(OUT / "5km/events_clean.parquet")
    bg = pd.read_parquet(OUT / "5km/background_candidates.parquet")
    assert int(bg.background_in_imprecise_circle.sum()) == log["background_flagged_imprecise_circle"] == 1444
    for w, g in bg.groupby("window"):
        e = ev[(ev.window == w) & ev.usable_for_buffer]
        assert e.radius_m.fillna(5000.0).le(10000).all()  # only events up to 10 km accuracy shield
        buf = np.maximum(2 * e.radius_m.fillna(5000.0).values, 5000.0)
        for x, y in zip(g.x_m.values[:40], g.y_m.values[:40]):
            d = np.hypot(np.maximum(np.abs(x - e.x_m.values) - 2500, 0), np.maximum(np.abs(y - e.y_m.values) - 2500, 0))
            assert (d > buf).all()
    assert not bg.merge(cells[cells.excluded][["window", "row", "col"]], on=["window", "row", "col"]).shape[0]
    sens = log["unknown_trigger_sensitivity_set"]
    assert sens["strict_all_years"] == 976 and sens["of_which_unknown_trigger"] == 329 and sens["primary_events_not_in_sensitivity_set"] == 0
    assert (cells.label_point_count_sens_all >= cells.label_point_count_clean_all).all()  # the sensitivity layer only adds events
