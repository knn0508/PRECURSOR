"""Event feature tests; all events are SYNTHETIC."""
from datetime import UTC, datetime

import pytest
from shapely.geometry import box

from app.services.environmental.features.historical_event_features import LIMITATION, haversine_km, historical_event_features
from app.services.environmental.features.seismic_features import seismic_features
from app.services.environmental.providers.synthetic import usgs_feature
from app.services.environmental.seismic.earthquake_processor import parse_feature

AOI = box(116.0, 5.0, 117.0, 6.0)


def ev(i, lon, lat, d="2010-05-01T00:00:00"):
    return {"id": i, "lon": lon, "lat": lat, "event_date": d}


def test_haversine_known_pair():
    # London (51.5074,-0.1278) to Paris (48.8566,2.3522): ~343.5 km
    assert haversine_km(-0.1278, 51.5074, 2.3522, 48.8566) == pytest.approx(343.5, abs=2.0)
    assert haversine_km(10, 10, 10, 10) == 0.0
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.01)  # 1 degree of meridian on R=6371.0088


def test_historical_inclusion_edges_skipped_and_limitation():
    events = [ev("in", 116.5, 5.5, "2010-05-01T00:00:00"), ev("edge", 116.0, 5.5, "2012-01-01"), ev("corner", 117.0, 6.0),
              ev("out", 118.0, 5.5), ev("nolat", 116.5, None), ev("badlat", 116.5, 95.0), ev("nodate", 116.5, 5.5, None),
              ev("baddate", 116.5, 5.5, "not a date"), {"id": "nocoords", "event_date": "2010-01-01"}]
    f = historical_event_features(events, AOI)
    assert f["count"] == 3 and f["skipped"] == 5
    assert f["counts_by_year"] == {2010: 2, 2012: 1} and f["date_min"].startswith("2010-05-01") and f["date_max"].startswith("2012")
    assert f["nearest_event_distance_km"] == pytest.approx(0.0, abs=1e-6)  # "in" sits on the centroid (116.5, 5.5)
    assert f["limitation"] == LIMITATION and "2017-09-28" in LIMITATION and "not ground truth" in LIMITATION


def test_historical_empty_has_null_distance_and_still_limitation():
    f = historical_event_features([ev("out", 100, 0)], AOI)
    assert f["count"] == 0 and f["nearest_event_distance_km"] is None and f["date_min"] is None and f["limitation"]


def test_datetime_objects_accepted():
    f = historical_event_features([ev("a", 116.5, 5.5, datetime(2001, 1, 1, tzinfo=UTC))], AOI)
    assert f["counts_by_year"] == {2001: 1}


def test_seismic_features():
    raw = [usgs_feature("a", 116.5, 5.5, 10.0, 3.5, 1_600_000_000_000), usgs_feature("b", 116.5, 6.5, 30.0, 5.5, 1_600_000_100_000),
           usgs_feature("c", 117.5, 5.5, None, 2.0, 1_600_000_200_000), usgs_feature("late", 116.5, 5.5, 5.0, 4.0, 1_700_000_000_000)]
    events = [parse_feature(r) for r in raw]
    f = seismic_features(events, (116.5, 5.5), end=datetime(2021, 1, 1, tzinfo=UTC))
    assert f["count"] == 3 and f["magnitude"] == {"min": 2.0, "max": 5.5, "mean": pytest.approx(11.0 / 3)}
    assert f["magnitude_histogram"]["counts"] == [1, 1, 0, 1, 0, 0] and f["magnitude_histogram"]["outside"] == 0
    assert f["depth_km"] == {"min": 10.0, "max": 30.0, "n_with_depth": 2}
    assert f["nearest_event_distance_km"] == pytest.approx(0.0, abs=1e-6) and "independent" in f["note"]
    empty = seismic_features([], (0, 0))
    assert empty["count"] == 0 and empty["magnitude"] is None and empty["nearest_event_distance_km"] is None
