import pytest

from app.services.data_acquisition.providers.smap import SMAPDataProvider
from app.services.data_acquisition.types import ProviderError, SearchQuery

from ._provider_helpers import FakeAuth, FakeDM, aoi, load, settings

CMR = "app.services.data_acquisition.cmr"


@pytest.fixture
def prov(tmp_path, monkeypatch):
    f = load("smap")
    monkeypatch.setattr(f"{CMR}.find_collections", lambda **k: [f["collection"]])
    monkeypatch.setattr(f"{CMR}.find_granules", lambda *a, **k: f["granules"])
    return SMAPDataProvider(settings(tmp_path), FakeAuth(), FakeDM())


def test_collection_reports_catalog_coverage(prov):
    (c,) = prov.search_collections()
    assert c.version == "006" and c.maturity is None and c.product_type == "SMAP_SPL3SMP_E"
    assert c.extra["temporal_start"].startswith("2015") and c.extra["ends_at_present"] is True
    assert c.extra["spatial_resolution_from_title"] == "9 km"


def test_disabled_returns_nothing_and_warns(tmp_path):
    p = SMAPDataProvider(settings(tmp_path, enable_smap=False))
    assert p.search_collections() == [] and p.search_granules(SearchQuery(aoi=aoi())) == []
    assert "disabled" in p.last_warnings[0]


def test_granules_checksum_and_exact_size(prov):
    r = prov.search_granules(SearchQuery(aoi=aoi()))[0]
    assert (r.file_format, r.file_size_bytes, r.checksum, r.checksum_algorithm) == ("HDF5", 123456, "abc123", "MD5")
    assert r.download_url.startswith("https://")
    prov.download_granule(r, None)
    kw = prov.download_manager.calls[0][2]
    assert kw["expected_size"] == 123456 and kw["checksum_algorithm"] == "MD5"


def test_catalog_failure_is_provider_error(tmp_path, monkeypatch):
    def boom(**k):
        raise ProviderError("down")
    monkeypatch.setattr(f"{CMR}.find_collections", boom)
    with pytest.raises(ProviderError):
        SMAPDataProvider(settings(tmp_path)).search_granules(SearchQuery(aoi=aoi()))
