"""SMAP L3 soil moisture (OPTIONAL provider, off unless settings.enable_smap). Resolution/coverage come from the catalog."""
from __future__ import annotations

from typing import Any

from app.services.data_acquisition.providers._cmr_common import CmrCollectionProvider
from app.services.data_acquisition.types import ProviderName

LIMITATIONS = (
    "Coarse SMAP grid (see spatial_resolution_from_title): does not represent slope-scale soil moisture. "
    "Valid dates are limited to the collection temporal extent reported by the catalog."
)


class SMAPDataProvider(CmrCollectionProvider):
    name = ProviderName.SMAP

    def _short_name(self) -> str | None:
        if not self.settings.enable_smap:
            self.last_warnings.append("SMAP provider is disabled (settings.enable_smap=False)")
            return None
        return self.settings.smap_collection

    def _product_type(self, short_name: str) -> str:
        return f"SMAP_{short_name}"

    def _collection_extra(self, umm: dict[str, Any]) -> dict[str, Any]:
        return {"limitations": LIMITATIONS}

    def _granule_metadata(self, umm: dict[str, Any]) -> dict[str, Any]:
        return {"limitations": LIMITATIONS}
