"""Landslide catalog importer. All data here is TEST FIXTURE, synthetic, not NASA data. No network."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from sqlalchemy import select

from app.core.config import Settings
from app.models.data_collection import DataCollection
from app.models.landslide_event import LandslideEvent
from app.services.data_acquisition.providers import landslide_catalog as lc

HEADER = "source_name,source_link,event_id,event_date,event_title,location_description,landslide_category," \
         "landslide_trigger,country_name,longitude,latitude"
ROWS = [
    "SynthSrc,http://x/1,T1,03/15/2010 12:00:00 AM,title1,Place One,landslide,rain,Testland,10.5,20.25",
    "SynthSrc,,T2,2012-06-01,title2,,mudslide,downpour,Otherland,-70.0,-30.0",
    "SynthSrc,,T3,not a date,title3,Place Three,rockfall,,Testland,11.0,21.0",
    "SynthSrc,,T4,01/01/2011,bad,Place,x,x,Testland,10.0,95.0",      # lat out of range
    "SynthSrc,,T5,01/01/2011,bad,Place,x,x,Testland,,20.0",           # empty lon
    "SynthSrc,,T6,01/01/2011,bad,Place,x,x,Testland,abc,20.0",        # non-numeric
    "SynthSrc,,T1,01/01/2011,dup,Place,x,x,Testland,10.5,20.25",      # duplicate id
    "SynthSrc,,T7,01/01/2011,zero,Place,x,x,Testland,0,0",            # (0,0) placeholder
]


def write_csv(tmp_path: Path, header=HEADER, rows=ROWS) -> Path:
    p = tmp_path / "synthetic.csv"  # TEST FIXTURE, synthetic, not NASA data
    p.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return p


@pytest.fixture
def prov(db, tmp_path):
    return lc.LandslideCatalogProvider(Settings(data_root=tmp_path / "data"), db, sleep=lambda s: None)


def test_import_validation_and_mapping(prov, db, tmp_path):
    res = prov.import_file(write_csv(tmp_path))
    assert (res.inserted, res.updated) == (3, 0)
    assert res.skipped_invalid == 5 and res.bad_dates == 1
    assert 0 < len(res.errors) <= lc.MAX_ERRORS
    ev = {e.external_event_id: e for e in db.scalars(select(LandslideEvent))}
    assert set(ev) == {"T1", "T2", "T3"}
    assert ev["T1"].event_date == datetime(2010, 3, 15, tzinfo=timezone.utc)
    assert ev["T2"].event_date.year == 2012
    assert ev["T3"].event_date is None  # bad date keeps the row
    assert ev["T2"].location_name == "title2"  # fallback to title
    assert ev["T1"].source == "SynthSrc (http://x/1)"
    r = lc.to_read_schema(ev["T1"])
    assert (r.longitude, r.latitude) == (10.5, 20.25)
    assert ev["T1"].original_attributes["event_date"] == "03/15/2010 12:00:00 AM"
    assert ev["T1"].original_attributes["event_title"] == "title1"
    col = db.scalar(select(DataCollection).where(DataCollection.provider == "LANDSLIDE_CATALOG"))
    assert lc.DATASET_NOTE in col.description
    assert col.metadata_json["limitations"] == lc.DATASET_NOTE
    assert col.metadata_json["sha256"] == res.sha256 and col.metadata_json["row_count"] == len(ROWS)


def test_reimport_idempotent(prov, db, tmp_path):
    p = write_csv(tmp_path)
    prov.import_file(p)
    res = prov.import_file(p)
    assert (res.inserted, res.updated) == (0, 3)
    assert len(db.scalars(select(LandslideEvent)).all()) == 3
    assert len(db.scalars(select(DataCollection)).all()) == 1
    other = prov.import_file(p, dataset_version="v2")
    assert other.inserted == 3


def test_header_case_whitespace_and_missing_optional(prov, db, tmp_path):
    p = write_csv(tmp_path, header=" Event_ID , LATITUDE,Longitude", rows=["A1,5.5,6.5"])
    res = prov.import_file(p)
    assert res.inserted == 1
    e = db.scalar(select(LandslideEvent))
    assert e.country is None
    assert e.original_attributes == {" Event_ID ": "A1", " LATITUDE": "5.5", "Longitude": "6.5"}  # original names kept


def test_missing_required_column(prov, tmp_path):
    p = write_csv(tmp_path, header="event_id,latitude,place", rows=["1,2,x"])
    with pytest.raises(ValueError, match=r"longitude.*headers found: \['event_id', 'latitude', 'place'\]"):
        prov.import_file(p)


def test_list_events_filters(prov, db, tmp_path):
    prov.import_file(write_csv(tmp_path))
    rows, total = lc.list_events(db, bbox=(10, 20, 12, 22))
    assert {r.external_event_id for r in rows} == {"T1", "T3"} and total == 2
    aoi = {"type": "Polygon", "coordinates": [[[-71, -31], [-69, -31], [-69, -29], [-71, -29], [-71, -31]]]}
    assert [r.external_event_id for r in lc.list_events(db, aoi_geometry=aoi)[0]] == ["T2"]
    rows, _ = lc.list_events(db, date_from=datetime(2011, 1, 1, tzinfo=timezone.utc))
    assert [r.external_event_id for r in rows] == ["T2"]  # T3 undated, T1 older
    assert lc.list_events(db, country="testland")[1] == 2
    rows, total = lc.list_events(db, limit=1, offset=1)
    assert len(rows) == 1 and total == 3


class FakeResp:
    def __init__(self, status, body=b""):
        self.status_code, self.body = status, body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, chunk_size=0):
        yield self.body


class FakeHttp:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_fetch_retry_atomic_no_overwrite(db, tmp_path):
    http = FakeHttp(FakeResp(503), requests.ConnectionError("boom"), FakeResp(200, b"a,b\n1,2\n"))
    s = Settings(data_root=tmp_path / "data", request_timeout_s=7, download_retries=3)
    prov = lc.LandslideCatalogProvider(s, db, http_session=http, sleep=lambda x: None)
    p = prov.fetch()
    assert p.read_bytes() == b"a,b\n1,2\n" and len(http.calls) == 3
    assert http.calls[0][0] == lc.SOURCE_URL and http.calls[0][1]["timeout"] == 7
    assert not list(p.parent.glob("*.part"))
    assert p.with_name(p.name + ".sha256").exists()
    assert prov.fetch() == p and len(http.calls) == 3  # reuse, no new request
    http.responses.append(FakeResp(200, b"new"))
    p2 = prov.fetch(force=True)
    assert p2 != p and p.read_bytes() == b"a,b\n1,2\n" and p2.read_bytes() == b"new"


def test_fetch_gives_up_without_leaving_files(db, tmp_path):
    http = FakeHttp(FakeResp(503), FakeResp(503))
    s = Settings(data_root=tmp_path / "data", download_retries=2)
    prov = lc.LandslideCatalogProvider(s, db, http_session=http, sleep=lambda x: None)
    with pytest.raises(RuntimeError, match="after 2 attempts"):
        prov.fetch()
    assert list((tmp_path / "data" / "raw" / "landslide_catalog").iterdir()) == []


def test_run_import_response(prov, tmp_path):
    out = prov.run_import(file_path=write_csv(tmp_path))
    assert out.inserted == 3 and out.limitations == lc.LIMITATIONS and out.dataset_version == "export-2016-03-07"
