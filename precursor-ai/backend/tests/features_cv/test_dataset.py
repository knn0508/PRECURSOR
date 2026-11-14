"""Labelled-sample dataset builder on SYNTHETIC stacks and SYNTHETIC events. Not real-data validation; the events here are fabricated."""
import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from app.services.environmental.dem.slope import slope_degrees
from app.services.features_cv import dataset as D
from app.services.features_cv.dataset_run import read_dataset_summary, run_dataset
from app.services.features_cv.export import to_numpy_stack, to_parquet, torch_dataset
from app.services.features_cv.pipeline import run_extraction
from app.services.features_cv.types import FORBIDDEN_NAME_TOKENS, FeatureError, NotAvailable, OptionalDependencyMissing, forbidden_names
from tests.features_cv.synth import ZONE39, lonlat, write_stack

N = 96
RES = 100.0  # 96 cells x 100 m = 9.6 km: big enough for 1 km-accuracy buffers (2 km) to leave room for background


def ev(g, row, col, eid, date="2020-06-15T00:00:00+00:00", acc="1km", **extra):
    lon, lat = lonlat(g, row, col)
    return {"id": eid, "lon": lon, "lat": lat, "event_date": date, "original_attributes": {"location_accuracy": acc}, **extra}


def valid_and_strat(g, arrays):
    s = arrays["SLOPE"]
    return np.isfinite(s), s


def events_set(g):
    """8 SYNTHETIC events spread over the 96x96 grid, with differing dates and accuracies."""
    pts = [(10, 10, "1km"), (12, 80, "500m"), (50, 50, "1km"), (80, 12, "500m"), (80, 80, "exact"), (30, 60, "1km"), (65, 30, "500m"), (20, 35, "1km")]
    return [ev(g, r, c, f"S{i}", f"20{10 + i}-06-15T00:00:00+00:00", a) for i, (r, c, a) in enumerate(pts)]


def params(**kw):
    return D.DatasetParams(**{"seed": 5, "min_buffer_m": 60.0, "block_m": 2400.0, "background_ratio": 2.0, **kw})


@pytest.fixture
def world(tmp_path):
    area, g, arrays = write_stack(tmp_path, n=N, res=RES)
    return tmp_path, area, g, arrays


# ---------------- location accuracy parsing ----------------
@pytest.mark.parametrize("raw,radius,rule", [
    ("1km", 1000.0, "numeric"), ("5 km", 5000.0, "numeric"), ("10KM", 10000.0, "numeric"), ("2.5km", 2500.0, "numeric"), ("500m", 500.0, "numeric"),
    ("exact", 0.0, "exact_stated"), ("unknown", None, "unknown"), ("", None, "unknown"), (None, None, "unknown"), ("N/A", None, "unknown"),
    ("about 3 km", None, "unparseable"), ("-1km", None, "unparseable"), ("1e3km", None, "unparseable"), (7, None, "unparseable"),
])
def test_parse_location_accuracy(raw, radius, rule):
    a = D.parse_location_accuracy(raw)
    assert a.radius_m == radius and a.rule == rule


# ---------------- exclusions ----------------
def test_events_with_unusable_fields_are_excluded_with_reasons(world):
    _, _, g, arrays = world
    valid, strat = valid_and_strat(g, arrays)
    good = ev(g, 40, 40, "good")
    far = ev(g, 40, 40, "far")
    far["lon"], far["lat"] = far["lon"] + 5.0, far["lat"]
    events = [good, far,
              ev(g, 30, 30, "unk", acc="unknown"), ev(g, 30, 31, "bad_acc", acc="a few km"), ev(g, 30, 32, "nodate", date=None),
              ev(g, 30, 33, "baddate", date="not a date"), {"id": "nocoord", "lon": None, "lat": 5.0, "event_date": "2020-01-01"},
              {"id": "nan", "lon": float("nan"), "lat": 5.0, "event_date": "2020-01-01"}, ev(g, 30, 34, "huge", acc="100km")]
    res = D.build_samples(events, g, {}, strat, valid, params(max_accuracy_radius_m=50_000.0))
    reasons = {e["event_id"]: e["reason"] for e in res.excluded}
    assert reasons == {"far": "outside_grid", "unk": "accuracy_unknown", "bad_acc": "accuracy_unparseable", "nodate": "no_date", "baddate": "no_date",
                       "nocoord": "no_coordinates", "nan": "no_coordinates", "huge": "accuracy_exceeds_max"}
    assert list(res.samples.loc[res.samples.is_event == 1, "source_event_id"]) == ["good"]
    assert res.info["counts"]["events_excluded"] == 8 and res.info["counts"]["excluded_by_reason"]["no_date"] == 2


def test_event_on_nodata_pixel_is_excluded(tmp_path):
    area, g, arrays = write_stack(tmp_path, n=N, res=RES, nan_hole=(slice(40, 60), slice(40, 60)))
    valid, strat = np.isfinite(arrays["SLOPE"]), arrays["SLOPE"]
    res = D.build_samples([ev(g, 50, 50, "hole"), ev(g, 20, 20, "ok")], g, {}, strat, valid, params())
    assert [e["reason"] for e in res.excluded] == ["on_nodata"] and list(res.samples.loc[res.samples.is_event == 1, "source_event_id"]) == ["ok"]


def test_no_usable_events_is_an_error_not_an_empty_dataset(world):
    _, _, g, arrays = world
    valid, strat = valid_and_strat(g, arrays)
    with pytest.raises(FeatureError, match="no usable event"):
        D.build_samples([], g, {}, strat, valid, params())
    with pytest.raises(FeatureError, match="no usable event"):
        D.build_samples([ev(g, 5, 5, "x", acc="unknown")], g, {}, strat, valid, params())


# ---------------- background sampling ----------------
def build(world, **kw):
    _, _, g, arrays = world
    valid, strat = valid_and_strat(g, arrays)
    static = {"ELEVATION": arrays["ELEVATION"], "NDVI": arrays["NDVI"]}
    return D.build_samples(events_set(g), g, static, strat, valid, params(**kw)), g, arrays


def test_background_is_outside_every_event_buffer_on_valid_pixels_only(tmp_path):
    area, g, arrays = write_stack(tmp_path, n=N, res=RES, nan_hole=(slice(0, 30), slice(60, 96)))
    valid, strat = np.isfinite(arrays["SLOPE"]), arrays["SLOPE"]
    events = events_set(g)
    res = D.build_samples(events, g, {"ELEVATION": arrays["ELEVATION"]}, strat, valid, params())
    df = res.samples
    bg, pos = df[df.is_event == 0], df[df.is_event == 1]
    assert len(pos) > 0 and len(bg) > 0
    assert valid[bg.row.to_numpy(), bg.col.to_numpy()].all()  # never in nodata
    for _, e in pos.iterrows():
        d = np.hypot(bg.x_m - e.x_m, bg.y_m - e.y_m)
        assert (d >= e.buffer_m).all()  # buffer = max(2 x radius, minimum buffer)
    assert pos.set_index("source_event_id").loc["S0", "buffer_m"] == 2000.0 and pos.set_index("source_event_id").loc["S4", "buffer_m"] == 60.0  # 'exact' -> min buffer
    assert not bg.duplicated(["row", "col"]).any()
    assert res.info["leakage"]["ok"] is True


def test_excluded_events_still_repel_background_samples(world):
    _, _, g, arrays = world
    valid, strat = valid_and_strat(g, arrays)
    near = ev(g, 48, 48, "unknown_acc", acc="unknown")  # excluded (unknown radius) but must keep background away
    res = D.build_samples(events_set(g) + [near], g, {}, strat, valid, params())
    df = res.samples
    bg = df[df.is_event == 0]
    unk = [e for e in res.excluded if e["event_id"] == "unknown_acc"]
    assert unk and unk[0]["reason"] == "accuracy_unknown"
    tf_x, tf_y = 600000.0 + 48.5 * RES, 630000.0 - 48.5 * RES  # centre of pixel (48, 48)
    assert (np.hypot(bg.x_m - tf_x, bg.y_m - tf_y) >= res.info["sampling"]["unknown_accuracy_buffer_m"]).all()


def test_seed_determinism_and_different_seed_changes_samples(world):
    a, _, _ = build(world)
    b, _, _ = build(world)
    c, _, _ = build(world, seed=6)
    pd.testing.assert_frame_equal(a.samples, b.samples)
    assert not a.samples.loc[a.samples.is_event == 0, ["row", "col"]].reset_index(drop=True).equals(c.samples.loc[c.samples.is_event == 0, ["row", "col"]].reset_index(drop=True))
    assert a.info["sampling"]["seed"] == 5


def test_ratio_and_class_balance_are_reported(world):
    res, _, _ = build(world, background_ratio=2.0)
    cb = res.info["class_balance"]
    assert cb["events"] == 8 and cb["background_ratio_requested"] == 2.0 and cb["background"] == 16 == res.info["counts"]["background_accepted"]
    assert cb["background_ratio_achieved"] == 2.0
    half, _, _ = build(world, background_ratio=0.5)
    assert half.info["class_balance"]["background"] == 4


def test_strata_are_terrain_quantile_bins_and_quotas_follow_area(world):
    res, g, arrays = build(world, n_strata=4, background_ratio=40.0)
    st = res.info["sampling"]
    assert len(st["stratification_edges"]) == 5 and st["strategy"].startswith("stratified")
    assert sum(s["requested"] for s in st["strata"]) == 320 and all(s["accepted"] <= s["requested"] for s in st["strata"])
    sizes = [s["valid_pixels"] for s in st["strata"]]
    assert max(sizes) - min(sizes) <= 0.1 * sum(sizes)  # quantile bins hold about equal numbers of pixels
    df = res.samples
    slope = arrays["SLOPE"][df.row.to_numpy(), df.col.to_numpy()]
    edges = np.array(st["stratification_edges"])
    assert (np.digitize(slope[df.is_event == 0], edges[1:-1]) == df.terrain_stratum[df.is_event == 0].to_numpy()).all()


def test_shortfall_is_reported_not_filled(tmp_path):
    area, g, arrays = write_stack(tmp_path, n=24)
    valid, strat = np.isfinite(arrays["SLOPE"]), arrays["SLOPE"]
    events = [ev(g, 12, 12, "centre", acc="10km")]  # a 20 km buffer swallows the whole 720 m grid
    res = D.build_samples(events, g, {}, strat, valid, D.DatasetParams(seed=1, background_ratio=5.0, block_m=300.0))
    assert res.info["counts"]["background_accepted"] == 0 and res.info["counts"]["background_requested"] == 5
    assert any("shortfall" in w for w in res.warnings) and all(s["shortfall"] == s["requested"] for s in res.info["sampling"]["strata"])


def test_without_a_terrain_raster_sampling_is_unstratified_and_says_so(world):
    _, _, g, arrays = world
    valid = np.isfinite(arrays["ELEVATION"])
    res = D.build_samples(events_set(g), g, {}, None, valid, params())
    assert res.info["sampling"]["stratification_edges"] is None and any("UNSTRATIFIED" in w for w in res.warnings) and len(res.info["sampling"]["strata"]) == 1


# ---------------- static / dynamic columns ----------------
def test_static_values_are_sampled_per_point_and_missing_stays_nan(tmp_path):
    area, g, arrays = write_stack(tmp_path, n=N, res=RES)
    z = arrays["ELEVATION"].copy()
    z[10, 10] = np.nan  # an event pixel whose STATIC value is missing while the validity mask (terrain raster) says it is usable
    valid = np.ones((N, N), bool)
    res = D.build_samples([ev(g, 10, 10, "a"), ev(g, 40, 40, "b")], g, {"ELEVATION": z}, np.nan_to_num(arrays["SLOPE"]), valid, params())
    e = res.samples.set_index("source_event_id")
    assert np.isnan(e.loc["a", "static__ELEVATION"]) and e.loc["b", "static__ELEVATION"] == pytest.approx(arrays["ELEVATION"][40, 40])
    assert res.info["static_columns"][0]["missing_count"] >= 1


def test_dynamic_columns_are_reserved_not_available_and_anchors_are_stored(world):
    res, g, _ = build(world)
    df = res.samples
    dyn = [c for c in df.columns if c.startswith("dyn__")]
    assert len(dyn) == 3 * 5 and df[dyn].isna().all().all()  # no AOI-mean proxy, no zeros: every cell is missing
    assert all(d["status"] == "NOT_AVAILABLE" and d["reason"] == "per-point dynamic features deferred to Phase 6" for d in res.info["dynamic_columns"])
    ev0 = df[df.source_event_id == "S0"].iloc[0]
    assert ev0.event_date.startswith("2010-06-15") and ev0.anchor_t_minus_1d == "2010-06-14" and ev0.anchor_t_minus_30d == "2010-05-16"
    assert df[df.is_event == 0][[c for c in df.columns if c.startswith("anchor_")]].isna().all().all()  # background reference date is a Phase 6 decision
    assert res.info["lead_time_anchors_days"] == [1, 3, 7, 14, 30]


# ---------------- splits and leakage ----------------
def test_spatial_split_whole_blocks_and_gap(world):
    res, g, _ = build(world, block_m=2400.0, test_fraction=0.3)
    df, sp = res.samples, res.info["split"]["spatial"]
    train, test = df[df.split_spatial == "train"], df[df.split_spatial == "test"]
    assert len(train) and len(test) and not (set(train.block_id) & set(test.block_id))
    assert sp["gap_m"] == 2000.0 and sp["block_m"] == 2400.0
    d = np.hypot(train.x_m.to_numpy()[:, None] - test.x_m.to_numpy()[None, :], train.y_m.to_numpy()[:, None] - test.y_m.to_numpy()[None, :])
    assert d.min() >= sp["gap_m"]  # no train/test pair closer than the gap
    assert res.info["leakage"]["ok"] and res.info["leakage"]["min_train_test_distance_m"] >= sp["gap_m"]
    assert sp["gap_samples_dropped"] == int((df.split_spatial == "gap").sum())
    assert set(df.split_spatial) <= {"train", "test", "gap"}


def test_custom_gap_and_block_are_respected(world):
    res, _, _ = build(world, gap_m=100.0, block_m=1200.0)
    assert res.info["split"]["spatial"]["gap_m"] == 100.0 and res.info["leakage"]["gap_m"] == 100.0


def test_temporal_split_cutoff_user_and_quantile(world):
    res, _, _ = build(world, temporal_cutoff="2013-12-31T00:00:00+00:00")
    ev_ = res.samples[res.samples.is_event == 1]
    dates = pd.to_datetime(ev_.event_date, utc=True)
    cut = pd.Timestamp("2013-12-31", tz="UTC")
    assert (ev_.split_temporal[dates <= cut] == "train").all() and (ev_.split_temporal[dates > cut] == "test").all()
    assert res.info["split"]["temporal"]["cutoff_chosen_by"] == "user"
    q, _, _ = build(world)
    assert q.info["split"]["temporal"]["cutoff_chosen_by"] == "event-date quantile"
    qe = q.samples[q.samples.is_event == 1]
    assert (qe.split_temporal == "test").sum() == 2 and (qe.split_temporal == "train").sum() == 6  # 8 events, test_fraction 0.2 -> latest 2
    assert "undated" in q.info["split"]["temporal"]["background_assignment"]


def test_degenerate_temporal_cutoff_warns(world):
    res, _, _ = build(world, temporal_cutoff="2100-01-01")
    assert any("no events on one side" in w for w in res.warnings)
    with pytest.raises(FeatureError, match="temporal_cutoff"):
        build(world, temporal_cutoff="garbage")


def test_leakage_checker_detects_each_kind_of_violation(world):
    res, _, _ = build(world)
    ok = res.samples.copy()
    gap, cut = 2000.0, datetime(2013, 12, 31, tzinfo=UTC)
    assert D.check_leakage(ok, gap_m=gap, cutoff=pd.Timestamp(res.info["split"]["temporal"]["cutoff"]).to_pydatetime())["ok"]
    # 1. a train sample moved next to a test sample
    bad = ok.copy()
    t = bad[bad.split_spatial == "test"].iloc[0]
    i = bad[bad.split_spatial == "train"].index[0]
    bad.loc[i, ["x_m", "y_m"]] = [t.x_m + 10, t.y_m]
    r = D.check_leakage(bad, gap_m=gap, cutoff=None)
    assert not r["ok"] and bad.loc[i, "sample_id"] in r["violations"]["spatial_gap"]
    # 2. a block shared between splits
    bad = ok.copy()
    bad.loc[bad[bad.split_spatial == "train"].index[0], "block_id"] = t.block_id
    assert D.check_leakage(bad, gap_m=0.0, cutoff=None)["violations"]["shared_blocks"] == [t.block_id]
    # 3. a train event after the cut-off / a test event before it
    bad = ok.copy()
    e = bad[bad.is_event == 1].index[0]
    bad.loc[e, ["event_date", "split_temporal"]] = ["2099-01-01T00:00:00+00:00", "train"]
    assert bad.loc[e, "sample_id"] in D.check_leakage(bad, gap_m=0.0, cutoff=cut)["violations"]["temporal"]
    bad.loc[e, ["event_date", "split_temporal"]] = ["1990-01-01T00:00:00+00:00", "test"]
    assert bad.loc[e, "sample_id"] in D.check_leakage(bad, gap_m=0.0, cutoff=cut)["violations"]["temporal"]
    # 4. a background sample inside an event buffer
    bad = ok.copy()
    ev0 = bad[bad.is_event == 1].iloc[0]
    j = bad[bad.is_event == 0].index[0]
    bad.loc[j, ["x_m", "y_m"]] = [ev0.x_m + 5, ev0.y_m]
    assert bad.loc[j, "sample_id"] in D.check_leakage(bad, gap_m=0.0, cutoff=None)["violations"]["background_buffer"]
    # 5. duplicated ids
    bad = pd.concat([ok, ok.iloc[:1]])
    assert D.check_leakage(bad, gap_m=0.0, cutoff=None)["violations"]["duplicate_ids"]


def test_single_block_dataset_cannot_be_split_spatially_and_says_so(world):
    res, _, _ = build(world, block_m=1e7)
    assert (res.samples.split_spatial == "train").all() and any("fewer than 2 spatial blocks" in w for w in res.warnings)


def test_parameter_validation(world):
    _, _, g, arrays = world
    valid, strat = valid_and_strat(g, arrays)
    for kw in ({"background_ratio": 0}, {"background_ratio": float("inf")}, {"test_fraction": 0}, {"test_fraction": 1}, {"n_strata": 0}):
        with pytest.raises(FeatureError):
            D.build_samples(events_set(g), g, {}, strat, valid, params(**kw))
    with pytest.raises(FeatureError, match="different shape"):
        D.build_samples(events_set(g), g, {"X": np.zeros((3, 3))}, strat, valid, params())


# ---------------- the dataset on disk (service) ----------------
def test_run_dataset_writes_files_manifest_and_summary(world):
    root, area, g, arrays = world
    run_extraction(root, area)
    events = events_set(g)
    m = run_dataset(root, area, events, params(), events_origin="SYNTHETIC_FIXTURE")
    d = root / "processed" / "datasets" / str(area)
    assert {p.name for p in d.iterdir()} == {"samples.parquet", "excluded.json", "manifest.json"}
    df = pd.read_parquet(d / "samples.parquet")
    assert len(df) == m["counts"]["samples"] and "static__local_relief_w5" in df.columns and "static__ELEVATION" in df.columns
    assert "static__INSAR_VELOCITY" not in df.columns and any(n["layer"] == "INSAR_VELOCITY" for n in m["not_sampled_layers"])
    assert not any(c.startswith("static__glcm") for c in df.columns) and any("block-grid" in n["reason"] for n in m["not_sampled_layers"])
    assert m["contains_synthetic_data"] is True and m["real_data_validation"] == "NOT_PERFORMED" and m["seed"] == 5
    assert m["source"]["phase4_manifest_sha256"] and m["source"]["features_manifest_sha256"] and m["source"]["events_origin"] == "SYNTHETIC_FIXTURE"
    assert m["dataset_schema_version"] and m["code_version"] and m["parameters"]["stratification_source"] == "SLOPE layer"
    assert any("INVENTORY BIAS" in c for c in m["caveats"]) and any("not proven stable" in c for c in m["caveats"])
    assert m["accuracy_parsing"]["status"].startswith("NOT_VERIFIED")
    assert json.loads((d / "excluded.json").read_text()) == []
    s = read_dataset_summary(root, area)
    assert s["counts"]["events_used"] == 8 and s["leakage"]["ok"] is True and "files" not in s


def test_run_dataset_without_feature_manifest_and_with_derived_slope(tmp_path):
    area, g, _ = write_stack(tmp_path, n=N, res=RES, slope_layer=False)
    m = run_dataset(tmp_path, area, events_set(g), params())
    assert m["source"]["features_manifest_sha256"] is None and m["parameters"]["stratification_source"].startswith("slope derived")
    assert m["contains_synthetic_data"] is True  # the stack is synthetic even though the events origin is UNKNOWN


def test_run_dataset_errors(tmp_path, world):
    root, area, g, _ = world
    with pytest.raises(FeatureError, match="events_origin"):
        run_dataset(root, area, events_set(g), params(), events_origin="REAL")
    import uuid

    with pytest.raises(NotAvailable):
        run_dataset(root, uuid.uuid4(), events_set(g), params())
    with pytest.raises(NotAvailable):
        read_dataset_summary(root, uuid.uuid4())
    a2, g2, _ = write_stack(root, n=N, res=RES, ndvi=False, insar=False)
    mp = root / "processed" / "environmental" / str(a2) / "features" / "manifest.json"
    m = json.loads(mp.read_text())
    mp.write_text(json.dumps({**m, "entries": [e for e in m["entries"] if e["layer_type"] == "NDVI"]}))
    with pytest.raises(NotAvailable):
        run_dataset(root, a2, events_set(g2), params())


def test_two_utm_zones_produce_valid_datasets(tmp_path):
    for z in (ZONE39,):
        area, g, arrays = write_stack(tmp_path, n=N, res=RES, **z)
        m = run_dataset(tmp_path, area, events_set(g), params())
        assert m["leakage"]["ok"] and m["grid"]["crs"] == "EPSG:32639" and m["counts"]["events_used"] == 8
        df = pd.read_parquet(tmp_path / "processed" / "datasets" / str(area) / "samples.parquet")
        assert df.x_m.between(z["x0"], z["x0"] + N * RES).all() and df.y_m.between(z["y0"] - N * RES, z["y0"]).all()
        assert df.lon.between(51, 53).all() and df.lat.between(39, 42).all()  # lon/lat of background rows were reprojected back


def test_slope_helper_matches_the_stack_slope(world):
    _, _, g, arrays = world
    from affine import Affine

    again = slope_degrees(arrays["ELEVATION"], g["crs"], Affine(*g["transform"]))
    assert np.allclose(again, arrays["SLOPE"], equal_nan=True)


# ---------------- exporters ----------------
def test_exporters(world, tmp_path):
    res, _, arrays = build(world)
    p = to_parquet(res.samples, tmp_path / "x" / "s.parquet")
    back = pd.read_parquet(p)
    assert list(back.columns) == list(res.samples.columns) and len(back) == len(res.samples)
    with pytest.raises(FeatureError, match="scores"):
        to_parquet(pd.DataFrame({"landslide_probability": [0.1]}), tmp_path / "bad.parquet")
    npz = to_numpy_stack({"a": arrays["ELEVATION"], "b": arrays["NDVI"]}, tmp_path / "s.npz")
    z = np.load(npz)
    assert list(z["names"]) == ["a", "b"] and z["data"].shape == (2, N, N) and z["data"].dtype == np.float32
    with pytest.raises(FeatureError, match="different shapes"):
        to_numpy_stack({"a": np.zeros((2, 2)), "b": np.zeros((3, 3))}, tmp_path / "x.npz")
    with pytest.raises(FeatureError):
        to_numpy_stack({}, tmp_path / "x.npz")


def test_torch_dataset_interface_is_optional_and_never_installed(world):
    res, _, _ = build(world)
    with pytest.raises(OptionalDependencyMissing, match="not installed"):
        torch_dataset(res.samples, ["static__ELEVATION"])


# ---------------- ML boundary ----------------
def walk_names(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield str(k)
            yield from walk_names(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk_names(v)


def test_no_score_like_field_names_anywhere_in_dataset_outputs(world):
    root, area, g, _ = world
    run_extraction(root, area)
    m = run_dataset(root, area, events_set(g), params(), events_origin="SYNTHETIC_FIXTURE")
    df = pd.read_parquet(root / "processed" / "datasets" / str(area) / "samples.parquet")
    names = list(walk_names(m)) + list(df.columns)
    assert forbidden_names(names) == [], forbidden_names(names)
    assert {"is_event", "sample_type"} <= set(df.columns) and set(df.sample_type) == {"EVENT", "BACKGROUND"}
    assert all(t not in c.lower() for c in df.columns for t in FORBIDDEN_NAME_TOKENS)
