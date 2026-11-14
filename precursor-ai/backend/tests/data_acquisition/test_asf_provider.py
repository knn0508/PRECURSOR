import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.data_acquisition.aoi import AOI
from app.services.data_acquisition.providers import asf
from app.services.data_acquisition.providers.asf import ASFSearchProvider
from app.services.data_acquisition.types import DownloadError, Maturity, ProviderError, SearchQuery

G = json.loads((Path(__file__).parent / "fixtures" / "nisar_gunw_granule.json").read_text())
AOI_IN = AOI.from_wkt("in", "POLYGON((-81.8 7.8,-81.5 7.8,-81.5 8.0,-81.8 8.0,-81.8 7.8))")
PRODUCT = SimpleNamespace(umm=G["umm"], meta=G["meta"])


def provider():
    return ASFSearchProvider(Settings(_env_file=None, nisar_products="GUNW", allowed_maturities="VALIDATED,BETA"))


def test_search_maps_args_and_normalizes(monkeypatch):
    calls = []
    monkeypatch.setattr(asf, "asf_search", lambda **kw: calls.append(kw) or [PRODUCT])
    out = provider().search_granules(SearchQuery(aoi=AOI_IN, maturities=(Maturity.VALIDATED, Maturity.PROVISIONAL)))
    assert [c["shortName"] for c in calls] == ["NISAR_L2_GUNW_V1"]  # PROVISIONAL not allowed by settings
    assert calls[0]["intersectsWith"].startswith("POLYGON") and calls[0]["maxResults"] == 10
    assert out[0].maturity is Maturity.VALIDATED and out[0].file_size_bytes == 1_400_000_000


def test_unsupported_combo_warns_and_all_failed_raises(monkeypatch):
    def fn(**kw):
        if "BETA" in kw["shortName"]:
            raise ProviderError("not searchable")
        return [PRODUCT]

    monkeypatch.setattr(asf, "asf_search", fn)
    p = provider()
    out = p.search_granules(SearchQuery(aoi=AOI_IN, maturities=(Maturity.VALIDATED, Maturity.BETA)))
    assert len(out) == 1 and any("BETA" in w for w in p.last_warnings)

    def boom(**kw):
        raise ProviderError("down")

    monkeypatch.setattr(asf, "asf_search", boom)
    with pytest.raises(ProviderError):
        p.search_granules(SearchQuery(aoi=AOI_IN))


def test_collections_empty_with_warning_and_download_refused(tmp_path):
    p = provider()
    assert p.search_collections() == [] and p.last_warnings
    with pytest.raises(DownloadError) as e:
        p.download_granule(None, tmp_path)
    assert e.value.retryable is False
