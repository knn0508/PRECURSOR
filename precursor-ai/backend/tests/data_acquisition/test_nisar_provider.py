import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.services.data_acquisition.aoi import AOI
from app.services.data_acquisition.providers.nisar import NISARDataProvider, granule_from_umm
from app.services.data_acquisition.types import (
    AuthenticationError,
    DownloadError,
    Maturity,
    ProviderError,
    SearchQuery,
)

FIX = Path(__file__).parent / "fixtures"
GRANULE = json.loads((FIX / "nisar_gunw_granule.json").read_text())
COLLECTION = json.loads((FIX / "nisar_collection.json").read_text())
INSIDE = AOI.from_wkt("in", "POLYGON((-81.8 7.8,-81.5 7.8,-81.5 8.0,-81.8 8.0,-81.8 7.8))")
OUTSIDE = AOI.from_wkt("out", "POLYGON((10 10,11 10,11 11,10 11,10 10))")


def prov(*, products="GUNW", allowed="VALIDATED,PROVISIONAL,BETA", dm=None, fallback=None, **kw):
    s = Settings(_env_file=None, nisar_products=products, allowed_maturities=allowed, **kw)
    return NISARDataProvider(s, MagicMock(), dm, fallback=fallback), s


def patch_granules(monkeypatch, fn):
    monkeypatch.setattr("app.services.data_acquisition.cmr.find_granules", fn)


def test_normalizer_real_shape():
    r = granule_from_umm(GRANULE["umm"], GRANULE["meta"])
    assert r.granule_id.startswith("NISAR_L2_PR_GUNW") and r.product_type == "GUNW"
    assert r.maturity is Maturity.VALIDATED and r.collection_short_name == "NISAR_L2_GUNW_V1"
    assert (r.orbit_direction, r.relative_orbit, r.file_format) == ("DESCENDING", 32, "HDF5")
    assert r.file_size_bytes == 1_400_000_000 and r.checksum_algorithm == "MD5"  # the .h5, not the PNG
    assert r.download_url.startswith("https://") and r.download_url.endswith(".h5")
    assert r.temporal_baseline_days == 12
    assert r.metadata["polarization"] == ["HH"] and r.metadata["frame"] == 84
    assert r.metadata["pge_version"] == "1.0.20" and r.footprint.intersects(INSIDE.geometry)


def test_normalizer_tolerates_garbage():
    r = granule_from_umm({"GranuleUR": "x"}, {}, short_name_="NISAR_L3_SME2_BETA_V1")
    assert r.maturity is Maturity.BETA and r.product_type == "SME2"
    assert r.footprint is None and r.download_url is None and r.file_size_bytes is None
    assert granule_from_umm({}, {}).granule_id == ""


def test_search_collections_verifies_and_warns(monkeypatch):
    def fake(short_name):
        return [COLLECTION] if short_name == "NISAR_L2_GUNW_V1" else []

    monkeypatch.setattr("app.services.data_acquisition.cmr.find_collections", fake)
    p, _ = prov(products="GUNW,SME2")
    out = p.search_collections()
    assert [c.short_name for c in out] == ["NISAR_L2_GUNW_V1"]
    assert out[0].concept_id == "C0000000000-ASF" and out[0].maturity is Maturity.VALIDATED
    assert any("SME2" in w for w in p.last_warnings)
    assert not any("GUNW" in w for w in p.last_warnings)


def test_search_collections_all_failing_raises(monkeypatch):
    def boom(**kw):
        raise ProviderError("down")

    monkeypatch.setattr("app.services.data_acquisition.cmr.find_collections", boom)
    p, _ = prov()
    with pytest.raises(ProviderError):
        p.search_collections()


def test_search_granules_order_filter_and_intersection(monkeypatch):
    calls = []

    def fake(sn, **kw):
        calls.append(sn)
        return [GRANULE]

    patch_granules(monkeypatch, fake)
    p, _ = prov()
    q = SearchQuery(aoi=INSIDE, maturities=(Maturity.BETA, Maturity.VALIDATED), max_results=5)
    out = p.search_granules(q)
    assert calls == ["NISAR_L2_GUNW_V1", "NISAR_L2_GUNW_BETA_V1"]  # VALIDATED first
    assert [g.maturity for g in out] == [Maturity.VALIDATED, Maturity.BETA]
    assert [g.collection_short_name for g in out] == calls
    # CMR bbox is a superset: a granule not truly intersecting the AOI is dropped
    assert p.search_granules(SearchQuery(aoi=OUTSIDE)) == []


def test_maturity_intersection_with_settings(monkeypatch):
    patch_granules(monkeypatch, lambda *a, **k: pytest.fail("must not query"))
    p, _ = prov(allowed="VALIDATED")
    assert p.search_granules(SearchQuery(aoi=INSIDE, maturities=(Maturity.BETA,))) == []
    assert p.last_warnings


def test_cap_and_partial_failure(monkeypatch):
    def fake(sn, **kw):
        if "GCOV" in sn:
            raise ProviderError(f"CMR granule search failed for {sn}")
        return [GRANULE] * 5

    patch_granules(monkeypatch, fake)
    p, _ = prov(products="GCOV,GUNW", max_granules_per_request=3)
    out = p.search_granules(SearchQuery(aoi=INSIDE, max_results=50))
    assert len(out) == 3 and any("GCOV" in w for w in p.last_warnings)


def test_all_failed_raises_or_falls_back(monkeypatch):
    def boom(*a, **k):
        raise ProviderError("down")

    patch_granules(monkeypatch, boom)
    p, _ = prov()
    with pytest.raises(ProviderError):
        p.search_granules(SearchQuery(aoi=INSIDE))
    fb = MagicMock(last_warnings=[])
    fb.search_granules.return_value = ["fallback-result"]
    p, _ = prov(fallback=fb)
    assert p.search_granules(SearchQuery(aoi=INSIDE)) == ["fallback-result"]
    assert any("fallback" in w for w in p.last_warnings)


def test_get_granule_metadata(monkeypatch):
    seen = []

    def fake(sn, **kw):
        seen.append((sn, kw.get("granule_ur")))
        return [GRANULE] if "PROVISIONAL" in sn else []

    patch_granules(monkeypatch, fake)
    p, _ = prov()
    gid = GRANULE["umm"]["GranuleUR"]
    r = p.get_granule_metadata(gid)
    assert r.maturity is Maturity.PROVISIONAL and all(ur == gid for _, ur in seen)
    assert all("GUNW" in sn for sn, _ in seen)  # product inferred from the id


class FakeDM:
    def __init__(self):
        self.args = None

    def download(self, url, dest, **kw):
        self.args = (url, dest, kw)


def test_download_delegates(tmp_path):
    dm = FakeDM()
    p, _ = prov(dm=dm, data_root=tmp_path / "data")
    g = granule_from_umm(GRANULE["umm"], GRANULE["meta"])
    path = p.download_granule(g, tmp_path)
    url, dest, kw = dm.args
    assert path == dest == tmp_path / url.rsplit("/", 1)[1]
    assert kw["expected_size"] == g.file_size_bytes and kw["checksum"] == g.checksum
    assert kw["checksum_algorithm"] == "MD5" and kw["session"] is p._auth.get_session.return_value
    default = p.download_granule(g, None)
    assert default.parent == tmp_path / "data" / "raw" / "nisar" / "gunw"


def test_download_refusals(tmp_path):
    dm = FakeDM()
    p, _ = prov(dm=dm, max_file_size_bytes=100)
    g = granule_from_umm(GRANULE["umm"], GRANULE["meta"])
    with pytest.raises(DownloadError) as e:
        p.download_granule(g, tmp_path)
    assert e.value.retryable is False
    g.file_size_bytes, g.download_url = 1, None
    with pytest.raises(DownloadError):
        p.download_granule(g, tmp_path)
    assert dm.args is None


def test_download_requires_auth(tmp_path):
    dm = FakeDM()
    p, _ = prov(dm=dm)
    p._auth.get_session.side_effect = AuthenticationError("no creds")
    with pytest.raises(AuthenticationError):
        p.download_granule(granule_from_umm(GRANULE["umm"], GRANULE["meta"]), tmp_path)
    assert dm.args is None
