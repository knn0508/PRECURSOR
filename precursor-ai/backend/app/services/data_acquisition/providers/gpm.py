"""GPM IMERG Final Run (GES_DISC) via CMR. Daily by default; half-hourly / monthly selectable."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.data_acquisition.providers._cmr_common import CmrCollectionProvider
from app.services.data_acquisition.types import ProviderError, ProviderName

if TYPE_CHECKING:
    from app.core.config import Settings

# short names verified in CMR (version 07); the version itself is read from the catalog.
_RESOLUTIONS = {
    "daily": ("GPM_3IMERGDF", "IMERG_DAILY"),
    "half_hourly": ("GPM_3IMERGHH", "IMERG_HALF_HOURLY"),
    "monthly": ("GPM_3IMERGM", "IMERG_MONTHLY"),
}
LIMITATIONS = (
    "IMERG Final Run: ~3.5 month latency, not real-time. ~0.1 degree (~10 km) grid cell: it does not "
    "represent point or slope-scale rainfall. Each granule is a GLOBAL file; subsetting to the AOI happens after download."
)


class GPMDataProvider(CmrCollectionProvider):
    name = ProviderName.GPM

    def __init__(self, settings: "Settings", auth: Any = None, download_manager: Any = None) -> None:
        super().__init__(settings, auth, download_manager)
        if settings.gpm_resolution not in _RESOLUTIONS:
            raise ProviderError(f"gpm_resolution={settings.gpm_resolution!r} is invalid; use one of {sorted(_RESOLUTIONS)}")

    def _short_name(self) -> str:
        return _RESOLUTIONS[self.settings.gpm_resolution][0]

    def _product_type(self, short_name: str) -> str:
        return _RESOLUTIONS[self.settings.gpm_resolution][1]

    def _collection_extra(self, umm: dict[str, Any]) -> dict[str, Any]:
        return {"limitations": LIMITATIONS, "file_format": "nc4 (HDF5)"}

    def _granule_metadata(self, umm: dict[str, Any]) -> dict[str, Any]:
        return {"limitations": LIMITATIONS, "global_file": True}
