"""SMAP stage tests. ALL inputs are SYNTHETIC fixtures written by smap.synthetic (labelled); passing them is not real-data validation.

Grid: 20 x 24 cells, centres lat 5.95 (row 0) .. 4.05 and lon 116.05 .. 118.35 at 0.1 degree. AOI BOX = [116.5,117.5] x [4.5,5.5]
contains exactly rows 5..14 and columns 5..14 (100 cell centres). Default AM field = 0.10 + 0.001*(19-row) + 0.0001*col, PM = 0.20 + same.
Oracle AM mean = 0.10 + 0.001*9.5 + 0.0001*9.5 = 0.11045 (PM 0.21045, combined 0.16045).
"""
import json
from datetime import date

import numpy as np
import pytest
from shapely.geometry import box

from app.services.environmental.features.smap_features import smap_features
from app.services.environmental.smap import reader as rd
from app.services.environmental.smap import synthetic as syn
from app.services.environmental.smap.smap_processor import SmapFile, process_smap
from app.services.environmental.types import DataOrigin, EnvError, LayerStatus, NotAvailable

AOI = box(116.5, 4.5, 117.5, 5.5)
D0 = date(2024, 1, 1)
AM, PM, BOTH = 0.11045, 0.21045, 0.16045


def _day(tmp_path, n, name=None, **kw):
    d = date(2024, 1, n)
    return SmapFile(d, syn.write_synthetic_smap(tmp_path / (name or f"SMAP_L3_SM_P_E_202401{n:02d}_synthetic.h5"), d, **kw))


def _run(files, start=D0, end=date(2024, 1, 3), **kw):
    return process_smap(files, AOI, start, end, **kw)


def test_aoi_statistic_oracle(tmp_path):
    r = _run([_day(tmp_path, 1)], end=D0)
    d = r.daily[0]
    assert d["soil_moisture_am"] == pytest.approx(AM, abs=1e-6)
    assert d["soil_moisture_pm"] == pytest.approx(PM, abs=1e-6)
    assert d["soil_moisture"] == pytest.approx(BOTH, abs=1e-6)
    s = [x for x in r.aoi_stats if x["overpass"] == "am"][0]
    assert (s["n_cells"], s["n_valid"], s["method"]) == (100, 100, "cell_centres_in_aoi")
    assert s["min"] == pytest.approx(0.10 + 0.001 * 5 + 0.0005, abs=1e-6)  # row 14, col 5
    assert s["max"] == pytest.approx(0.10 + 0.001 * 14 + 0.0014, abs=1e-6)  # row 5, col 14
    assert r.provenance.origin == DataOrigin.SYNTHETIC_FIXTURE and r.provenance.units == "cm3/cm3"


def test_centre_in_polygon_excludes_cells_overlapping_only_at_edge(tmp_path):
    aoi = box(116.5, 4.5, 117.46, 5.5)  # col 14 centre 117.45 still inside; col 15 (117.55) outside
    d = syn.write_synthetic_smap(tmp_path / "a.h5", D0)
    st = rd.read_daily_aoi(d, aoi, D0).overpasses["am"]
    assert st.n_cells == 100
    aoi2 = box(116.5, 4.5, 117.44, 5.5)  # col 14 centre 117.45 now outside
    assert rd.read_daily_aoi(d, aoi2, D0).overpasses["am"].n_cells == 90


def test_tiny_aoi_uses_centroid_cell_with_warning(tmp_path):
    tiny = box(117.06, 4.96, 117.09, 4.99)  # inside cell row 10, col 10 (centre 117.05, 4.95), no centre inside
    f = _day(tmp_path, 1)
    r = process_smap([f], tiny, D0, D0)
    assert r.daily[0]["soil_moisture_am"] == pytest.approx(0.10 + 0.009 + 0.001, abs=1e-6)
    assert r.aoi_stats[0]["method"] == "centroid_cell" and r.aoi_stats[0]["n_cells"] == 1
    assert any("smaller than a SMAP cell" in w for w in r.warnings)


def test_outside_grid_not_available(tmp_path):
    with pytest.raises(NotAvailable):
        process_smap([_day(tmp_path, 1)], box(100, 0, 101, 1), D0, D0)
    # inside the bounding extent hole is impossible here; centroid beyond half a cell from any centre is also refused
    with pytest.raises(NotAvailable):
        process_smap([_day(tmp_path, 1)], box(118.9, 5.0, 118.95, 5.05), D0, D0)


def test_fill_becomes_nan_not_zero(tmp_path):
    fb = (slice(5, 10), slice(5, 15))  # half of the AOI cells
    r = _run([_day(tmp_path, 1, fill_block_am=fb)], end=D0)
    s = [x for x in r.aoi_stats if x["overpass"] == "am"][0]
    assert (s["n_cells"], s["n_valid"]) == (100, 50)
    assert r.daily[0]["soil_moisture_am"] == pytest.approx(0.10 + 0.007 + 0.00095, abs=1e-6)
    full = (slice(5, 15), slice(5, 15))
    r2 = _run([_day(tmp_path, 1, name="b.h5", fill_block_am=full)], end=D0)
    assert r2.daily[0]["soil_moisture_am"] is None and r2.daily[0]["observed"] is True  # PM still observed


def test_undeclared_fill_applies_verified_value_with_warning(tmp_path):
    p = syn.write_synthetic_smap(tmp_path / "u.h5", D0, declare_fill=False, fill_block_am=(slice(5, 15), slice(5, 15)))
    r = rd.read_daily_aoi(p, AOI, D0)
    assert r.fill_declared is False and r.overpasses["am"].mean is None
    assert any("fill value not declared" in w for w in r.warnings)


def test_am_pm_separate_and_combined_rule(tmp_path):
    f = _day(tmp_path, 1, pm=None)  # PM group absent
    r = _run([f], end=D0)
    d = r.daily[0]
    assert d["soil_moisture_am"] == pytest.approx(AM, abs=1e-6)
    assert d["soil_moisture_pm"] is None and d["soil_moisture"] is None and d["observed"]
    assert r.counts["observed_am_days"] == 1 and r.counts["observed_pm_days"] == 0
    assert r.counts["days_with_both_overpasses"] == 0


def test_missing_days_are_none_never_zero(tmp_path):
    r = _run([_day(tmp_path, 1), _day(tmp_path, 3)])
    assert [x["observed"] for x in r.daily] == [True, False, True]
    miss = r.daily[1]
    assert miss["soil_moisture_am"] is None and miss["soil_moisture_pm"] is None and miss["soil_moisture"] is None
    assert r.counts["missing_ranges"] == [{"start": "2024-01-02", "end": "2024-01-02", "days": 1}]
    assert r.quality.valid_percent == pytest.approx(200 / 3)
    assert r.status == LayerStatus.PARTIALLY_PROCESSED


def test_duplicate_dates(tmp_path):
    a = _day(tmp_path, 1)
    b = _day(tmp_path, 1, name="dup.h5")
    r = _run([a, b], end=D0)
    assert any("duplicate date" in w for w in r.warnings) and r.counts["observed_days"] == 1
    c = _day(tmp_path, 1, name="dup2.h5", am=np.full((20, 24), 0.3))
    with pytest.raises(EnvError):
        _run([a, c], end=D0)


def test_file_outside_window_ignored_with_warning(tmp_path):
    r = _run([_day(tmp_path, 1), _day(tmp_path, 9)])
    assert any("outside window" in w for w in r.warnings) and r.counts["observed_days"] == 1


def test_unit_mismatch_refused(tmp_path):
    p = syn.write_synthetic_smap(tmp_path / "pct.h5", D0, units="percent")
    with pytest.raises(EnvError, match="never converted|not a volumetric"):
        rd.read_daily_aoi(p, AOI, D0)
    for ok in ("cm**3/cm**3", "m3/m3", "cm3/cm3"):
        assert rd.read_daily_aoi(syn.write_synthetic_smap(tmp_path / "ok.h5", D0, units=ok), AOI, D0)
    w = rd.read_daily_aoi(syn.write_synthetic_smap(tmp_path / "nu.h5", D0, units=None), AOI, D0)
    assert any("units attribute missing" in x for x in w.warnings)


def test_ambiguous_axes_refused(tmp_path):
    with pytest.raises(EnvError, match="ambiguous|axis"):
        rd.read_daily_aoi(syn.write_synthetic_smap(tmp_path / "t.h5", D0, swap_latlon_axes=True), AOI, D0)
    with pytest.raises(EnvError, match="equal length"):
        rd.read_daily_aoi(syn.write_synthetic_smap(tmp_path / "sq.h5", D0, axis_vectors=True, square_vectors=True), AOI, D0)


def test_axis_vectors_supported(tmp_path):
    p = syn.write_synthetic_smap(tmp_path / "v.h5", D0, axis_vectors=True)
    assert rd.read_daily_aoi(p, AOI, D0).overpasses["am"].mean == pytest.approx(AM, abs=1e-6)


def test_missing_variable_refused(tmp_path):
    p = syn.write_synthetic_smap(tmp_path / "n.h5", D0, sm_name="soil_moisture_renamed")
    with pytest.raises(EnvError, match="soil_moisture variable not found"):
        rd.read_daily_aoi(p, AOI, D0)


def _qual():
    q = np.zeros((20, 24), dtype=np.uint16)
    q[5:10, :] = 1  # bit 0 set: not recommended
    q[10, :] = 8  # bit 3 only: recommended (failed freeze/thaw does not affect retrieval)
    q[11, :] = syn.QFILL  # fill/gap value
    return q


def test_quality_filter_on_and_off(tmp_path):
    f = _day(tmp_path, 1, qual_am=_qual(), pm=None)
    off = _run([f], end=D0)
    assert off.daily[0]["soil_moisture_am"] == pytest.approx(AM, abs=1e-6) and off.quality_dropped_cells == 0
    on = _run([f], end=D0, quality_filter=True)
    s = on.aoi_stats[0]
    # kept rows 10, 12, 13, 14 -> mean(19-row) = 6.75
    assert on.daily[0]["soil_moisture_am"] == pytest.approx(0.10 + 0.00675 + 0.00095, abs=1e-6)
    assert (s["n_valid"], s["n_dropped_quality"]) == (40, 60) and on.quality_dropped_cells == 60
    assert on.input_hash != off.input_hash


def test_quality_filter_without_flag_is_refused(tmp_path):
    with pytest.raises(EnvError, match="retrieval_qual_flag"):
        rd.read_daily_aoi(syn.write_synthetic_smap(tmp_path / "nq.h5", D0), AOI, D0, quality_filter=True)
    with pytest.raises(NotAvailable):  # processor records the file error, nothing usable remains
        _run([_day(tmp_path, 1)], end=D0, quality_filter=True)


def test_quality_bit_rule():
    assert rd.quality_recommended(np.array([0, 8, 1, 2, 4, 65534])).tolist() == [True, True, False, False, False, False]


def test_corrupt_file_tolerated(tmp_path):
    bad = SmapFile(date(2024, 1, 2), syn.write_corrupt_file(tmp_path / "bad.h5"))
    r = _run([_day(tmp_path, 1), bad, _day(tmp_path, 3)])
    assert [e["file"] for e in r.file_errors] == ["bad.h5"]
    assert r.status == LayerStatus.PARTIALLY_PROCESSED and r.counts["observed_days"] == 2
    with pytest.raises(NotAvailable):
        _run([bad])


def test_input_hash_stable_and_changes(tmp_path):
    fs = [_day(tmp_path, 1), _day(tmp_path, 2)]
    h = _run(fs).input_hash
    assert _run(list(reversed(fs))).input_hash == h
    assert _run(fs, quality_filter=False).input_hash == h
    assert _run(fs[:1]).input_hash != h
    assert process_smap(fs, box(116.5, 4.5, 117.4, 5.5), D0, date(2024, 1, 3)).input_hash != h
    acq = [fs[0]._replace(acquisition_id="g1"), fs[1]]
    assert _run(acq).input_hash != h


def test_provenance_origin_rules(tmp_path):
    fs = [_day(tmp_path, 1)]
    assert _run(fs).provenance.dataset_version is None
    assert _run(fs).provenance.source_files == [fs[0].path.name]


def test_json_serialisable_and_features_wording(tmp_path):
    r = _run([_day(tmp_path, 1, qual_am=_qual()), _day(tmp_path, 3)], quality_filter=False)
    json.dumps(r.to_dict())
    out = smap_features(r)
    json.dumps(out)
    feats = out["features"]
    assert feats["observed_days"]["value"] == 2 and feats["missing_days"]["value"] == 1
    assert feats["mean_am"]["value"] == pytest.approx(AM, abs=1e-6)
    assert feats["last_observed_date"]["value"] == "2024-01-03"
    assert "observed days only" in feats["mean_am"]["note"]
    banned = ("risk", "score", "threshold", "saturat", "wet", "dry", "class", "susceptib", "hazard")
    text = json.dumps({k: [v.get("note"), v.get("units")] for k, v in feats.items()}).lower() + " ".join(feats).lower()
    assert not any(b in text for b in banned)
