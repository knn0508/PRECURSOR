"""USGS fetch/parse tests. ALL data are SYNTHETIC; a FAKE session is used, no network."""
from datetime import UTC, datetime

import pytest

from app.services.environmental.providers.synthetic import usgs_collection, usgs_feature
from app.services.environmental.providers.usgs_earthquake import USGSEarthquakeProvider
from app.services.environmental.seismic.earthquake_processor import normalise_events, parse_feature
from app.services.environmental.types import EnvError

BB = (115.0, 5.0, 117.0, 7.0)
T0, T1 = datetime(2020, 1, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC)


class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._b, self.headers = status, body, headers or {}

    def json(self):
        return self._b


class FakeSession:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        return self.script.pop(0)


def feats(a, b):
    return [usgs_feature(f"synthetic{i}", 116.0, 6.0, 10.0, 4.5, 1_600_000_000_000 + i) for i in range(a, b)]


def prov(**kw):
    sleeps = []
    return USGSEarthquakeProvider(sleep=sleeps.append, **kw), sleeps


def test_pagination_stops_on_short_page():
    p, _ = prov(page_size=3)
    s = FakeSession([Resp(body=usgs_collection(feats(0, 3))), Resp(body=usgs_collection(feats(3, 5)))])
    r = p.fetch(BB, T0, T1, session=s)
    assert len(r.events) == 5 and r.pages == 2 and not r.truncated
    assert [c["offset"] for c in s.calls] == [1, 4] and s.calls[0]["limit"] == 3 and s.calls[0]["format"] == "geojson"


def test_retry_on_429_and_5xx_then_success():
    p, sleeps = prov(page_size=10)
    s = FakeSession([Resp(429, headers={"Retry-After": "2"}), Resp(503), Resp(body=usgs_collection(feats(0, 2)))])
    assert len(p.fetch(BB, T0, T1, session=s).events) == 2
    assert len(s.calls) == 3 and sleeps[0] == 2.0 and len(sleeps) == 2


def test_retries_are_bounded():
    p, _ = prov(max_retries=2)
    s = FakeSession([Resp(500)] * 5)
    with pytest.raises(EnvError):
        p.fetch(BB, T0, T1, session=s)
    assert len(s.calls) == 3


def test_400_on_first_page_raises_and_later_page_truncates():
    p, _ = prov(page_size=2)
    with pytest.raises(EnvError, match="400"):
        p.fetch(BB, T0, T1, session=FakeSession([Resp(400)]))
    r = p.fetch(BB, T0, T1, session=FakeSession([Resp(body=usgs_collection(feats(0, 2))), Resp(400)]))
    assert r.truncated and len(r.events) == 2 and any("truncated" in w for w in r.warnings)


def test_global_cap_truncation_warning():
    p, _ = prov(page_size=2, max_records=4)
    s = FakeSession([Resp(body=usgs_collection(feats(i, i + 2))) for i in (0, 2, 4)])
    r = p.fetch(BB, T0, T1, session=s)
    assert r.truncated and len(r.events) == 4 and any("cap" in w for w in r.warnings)


def test_malformed_skipped_and_duplicates_dropped():
    bad = [usgs_feature("b1", 200.0, 6.0, 5.0, 4.0, 1_600_000_000_000), {"id": "b2"}, usgs_feature("b3", 1, 1, 1, None, 1)]
    good = feats(0, 2)
    p, _ = prov(page_size=50)
    r = p.fetch(BB, T0, T1, session=FakeSession([Resp(body=usgs_collection(good + bad + [good[0]]))]))
    assert [e["id"] for e in r.events] == ["synthetic0", "synthetic1"]
    assert sum("skipped" in w for w in r.warnings) == 3 and any("duplicate" in w for w in r.warnings)


def test_epoch_ms_time_and_fields():
    e = parse_feature(usgs_feature("x", 116.5, 6.25, 12.5, 5.1, 1_600_000_000_000))
    assert e["time"] == datetime(2020, 9, 13, 12, 26, 40, tzinfo=UTC) and e["time"].tzinfo is not None
    assert (e["lon"], e["lat"], e["depth_km"], e["magnitude"], e["mag_type"]) == (116.5, 6.25, 12.5, 5.1, "mww")
    assert parse_feature(usgs_feature("y", 0, 0, None, 1.0, 0))["depth_km"] is None  # missing depth is not 0


@pytest.mark.parametrize("lon,lat,depth,mag,t", [(181, 0, 1, 1, 0), (0, -90.1, 1, 1, 0), (float("nan"), 0, 1, 1, 0),
                                                 (0, 0, 1, None, 0), (0, 0, 1, 1, "x"), (0, 0, 5000, 1, 0)])
def test_invalid_values_rejected_not_clamped(lon, lat, depth, mag, t):
    with pytest.raises(ValueError):
        parse_feature(usgs_feature("z", lon, lat, depth, mag, t))


def test_normalise_sorts_and_dedupes():
    a = parse_feature(usgs_feature("a", 1, 1, 1, 1, 2000))
    b = parse_feature(usgs_feature("b", 1, 1, 1, 1, 1000))
    out, w = normalise_events([a, b, a])
    assert [e["id"] for e in out] == ["b", "a"] and any("duplicate" in x for x in w)
