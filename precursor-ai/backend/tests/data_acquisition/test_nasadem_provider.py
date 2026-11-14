import pytest
from shapely.geometry import box

from app.services.data_acquisition.aoi import AOI
from app.services.data_acquisition.providers.nasadem import NASADEMDataProvider, tiles_for_aoi
from app.services.data_acquisition.types import DownloadError, ProviderName, SearchQuery

from ._provider_helpers import FakeAuth, FakeDM, aoi, load, settings

CMR = "app.services.data_acquisition.cmr"


def _aoi(w, s, e, n):
    return AOI.from_geometry("t", box(w, s, e, n))


@pytest.mark.parametrize("bbox,expected", [
    ((44.2, 40.2, 44.8, 40.8), ["n40e044"]),
    ((44, 40, 45, 41), ["n40e044"]),  # edges on integers: no extra tile
    ((43.5, 40.5, 44.5, 41.5), ["n40e043", "n40e044", "n41e043", "n41e044"]),
    ((-70.5, -1.5, -69.5, -0.5), ["s02w071", "s02w070", "s01w071", "s01w070"]),
    ((-0.5, -0.5, 0.5, 0.5), ["s01w001", "s01e000", "n00w001", "n00e000"]),
])
def test_tiles_for_aoi(bbox, expected):
    assert sorted(tiles_for_aoi(_aoi(*bbox))) == sorted(expected)


def test_tiles_use_polygon_not_just_bbox():
    tri = AOI.from_wkt("tri", "POLYGON((43.9 40.1, 44.9 40.1, 44.1 40.9, 43.9 40.1))")
    assert "n40e043" in tiles_for_aoi(tri)
    far = AOI.from_wkt("tri2", "POLYGON((44.1 40.1, 44.9 40.1, 44.1 40.9, 44.1 40.1))")
    assert tiles_for_aoi(far) == ["n40e044"]


@pytest.fixture
def prov(tmp_path, monkeypatch):
    f = load("nasadem")
    monkeypatch.setattr(f"{CMR}.find_collections", lambda **k: [f["collection"]])
    monkeypatch.setattr(f"{CMR}.find_granules", lambda *a, **k: f["granules"])
    return NASADEMDataProvider(settings(tmp_path), FakeAuth(), FakeDM())


def test_collection_from_catalog(prov):
    (c,) = prov.search_collections()
    assert (c.provider, c.short_name, c.version, c.maturity, c.product_type) == (ProviderName.NASADEM, "NASADEM_HGT", "001", None, "DEM")
    assert c.concept_id.startswith("C-TEST")


def test_unknown_collection_warns(tmp_path, monkeypatch):
    monkeypatch.setattr(f"{CMR}.find_collections", lambda **k: [])
    p = NASADEMDataProvider(settings(tmp_path))
    assert p.search_collections() == [] and p.last_warnings


def test_search_drops_padded_neighbour_tile_and_warns(prov):
    recs = prov.search_granules(SearchQuery(aoi=aoi()))
    assert [r.metadata["tile"] for r in recs] == ["n40e044"]
    assert any("n40e043" in w for w in prov.last_warnings)
    r = recs[0]
    assert r.download_url.startswith("https://") and r.product_type == "DEM" and r.version == "001"


def test_download_uses_auth_session_and_target_path(prov, tmp_path):
    r = prov.search_granules(SearchQuery(aoi=aoi()))[0]
    path = prov.download_granule(r, None)
    url, dest, kw = prov.download_manager.calls[0]
    assert url == r.download_url and kw["session"] == "SESSION" and path == dest
    assert dest.parent == tmp_path / "raw" / "nasadem"


def test_download_refusals(prov):
    r = prov.search_granules(SearchQuery(aoi=aoi()))[0]
    r.file_size_bytes = 10**12
    with pytest.raises(DownloadError) as e:
        prov.download_granule(r, None)
    assert e.value.retryable is False
    r.file_size_bytes, r.download_url = None, None
    with pytest.raises(DownloadError):
        prov.download_granule(r, None)
