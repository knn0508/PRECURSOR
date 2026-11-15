"""OPERA L3 DISP-S1 (Sentinel-1 cumulative LOS displacement, ASF DAAC) via CMR. Search needs no login; downloads follow the usual approval rule."""
from __future__ import annotations

from typing import Any

from app.services.data_acquisition.providers._cmr_common import CmrCollectionProvider
from app.services.data_acquisition.types import ProviderName

LIMITATIONS = (
    "C-band Sentinel-1 LOS displacement relative to a ministack reference; masked pixels (low coherence, unwrapping failure) are not "
    "measurements. Files are frame-wide and large: the displacement-forecast module subsets remotely instead of downloading them whole."
)


class OperaDispDataProvider(CmrCollectionProvider):
    name = ProviderName.OPERA

    def _short_name(self) -> str:
        return "OPERA_L3_DISP-S1_V1"

    def _product_type(self, short_name: str) -> str:
        return "DISP-S1"

    def _collection_extra(self, umm: dict[str, Any]) -> dict[str, Any]:
        return {"limitations": LIMITATIONS, "file_format": "NetCDF"}

    def _granule_metadata(self, umm: dict[str, Any]) -> dict[str, Any]:
        return {"limitations": LIMITATIONS}
