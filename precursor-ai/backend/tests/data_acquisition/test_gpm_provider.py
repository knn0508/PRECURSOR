import pytest

from app.services.data_acquisition.providers.gpm import GPMDataProvider
from app.services.data_acquisition.types import ProviderError, SearchQuery

from ._provider_helpers import FakeAuth, FakeDM, aoi, load, settings

CMR = "app.services.data_acquisition.cmr"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    f = load("gpm")
    seen = {}
    monkeypatch.setattr(f"{CMR}.find_collections", lambda **k: [f["collection"]])
    monkeypatch.setattr(f"{CMR}.find_granules", lambda *a, **k: seen.update(gran=(a, k)) or f["granules"][: k["limit"]])
    return GPMDataProvider(settings(tmp_path), FakeAuth(), FakeDM()), seen


def test_invalid_resolution(tmp_path):
    with pytest.raises(ProviderError, match="gpm_resolution"):
        GPMDataProvider(settings(tmp_path, gpm_resolution="hourly"))


@pytest.mark.parametrize("res,short", [("daily", "GPM_3IMERGDF"), ("half_hourly", "GPM_3IMERGHH"), ("monthly", "GPM_3IMERGM")])
def test_resolution_selects_collection(tmp_path, monkeypatch, res, short):
    seen = {}
    monkeypatch.setattr(f"{CMR}.find_collections", lambda **k: seen.update(k) or [])
    p = GPMDataProvider(settings(tmp_path, gpm_resolution=res))
    p.search_collections()
    assert seen["short_name"] == short and p.last_warnings


def test_collection_notes(setup):
    p, _ = setup
    (c,) = p.search_collections()
    assert c.version == "07" and c.product_type == "IMERG_DAILY" and c.extra["spatial_resolution_from_title"] == "0.1 degree"
    assert c.extra["units"] is None  # not in the catalog record, so not invented
    assert "3.5 month" in c.extra["limitations"] and "not represent" in c.extra["limitations"]


def test_granules_and_cap_warning(setup):
    p, seen = setup
    recs = p.search_granules(SearchQuery(aoi=aoi(), max_results=2))
    assert len(recs) == 2 and seen["gran"][1]["version"] == "07"
    assert any("more than 2" in w for w in p.last_warnings)
    r = recs[0]
    assert "3.5 month" in r.metadata["limitations"] and r.metadata["size_exact"] is False
    assert r.file_size_bytes == int(26.98 * 1024**2)


def test_download_does_not_trust_approximate_size(setup):
    p, _ = setup
    r = p.search_granules(SearchQuery(aoi=aoi()))[0]
    p.download_granule(r, None)
    assert p.download_manager.calls[0][2]["expected_size"] is None


def test_no_warning_under_cap(setup):
    p, _ = setup
    assert len(p.search_granules(SearchQuery(aoi=aoi(), max_results=10))) == 3
    assert p.last_warnings == []
