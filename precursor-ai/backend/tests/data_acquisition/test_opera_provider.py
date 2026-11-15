"""OPERA DISP-S1 provider: offline (CMR is faked); no network, no login."""
from pathlib import Path
from unittest.mock import patch

from app.core.config import Settings
from app.services.data_acquisition.providers.opera import OperaDispDataProvider
from app.services.data_acquisition.registry import build_providers
from app.services.data_acquisition.storage import provider_dir
from app.services.data_acquisition.types import GranuleRecord, ProviderName

UMM = {"umm": {"ShortName": "OPERA_L3_DISP-S1_V1", "Version": "1", "EntryTitle": "OPERA DISP-S1", "Abstract": "x"}, "meta": {"concept-id": "C1"}}


def test_collection_verified_against_catalog():
    p = OperaDispDataProvider(Settings())
    with patch("app.services.data_acquisition.cmr.find_collections", return_value=[UMM]):
        c = p.search_collections()
    assert c[0].provider == ProviderName.OPERA and c[0].product_type == "DISP-S1" and c[0].short_name == "OPERA_L3_DISP-S1_V1"


def test_no_collection_means_warning_not_invention():
    p = OperaDispDataProvider(Settings())
    with patch("app.services.data_acquisition.cmr.find_collections", return_value=[]):
        assert p.search_collections() == [] and p.last_warnings


def test_registry_and_storage():
    assert "OPERA" in build_providers(Settings(), None, None)
    g = GranuleRecord(provider=ProviderName.OPERA, granule_id="g", collection_short_name="s", product_type="DISP-S1", version="1", maturity=None,
                      acquisition_start=None, acquisition_end=None, footprint=None, processing_date=None, file_format="nc", file_size_bytes=None,
                      download_url=None, checksum=None, checksum_algorithm=None, metadata={})
    assert provider_dir(Path("/d"), g).as_posix().endswith("raw/opera/disp_s1")
    assert "OPERA" not in build_providers(Settings(enable_opera=False), None, None)
