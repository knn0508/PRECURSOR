"""Builds the enabled granule providers and reports their status."""
from __future__ import annotations

import importlib
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.data_acquisition import DataAcquisition
from app.models.data_collection import DataCollection
from app.schemas.data_acquisition import ProviderStatus
from app.services.data_acquisition.providers.base import DataProvider
from app.services.data_acquisition.types import AcquisitionStatus, ProviderName

log = logging.getLogger(__name__)

# provider -> (settings flag, module, class). The landslide catalog is not a granule provider.
_GRANULE = {
    ProviderName.NISAR: ("enable_nisar", "nisar", "NISARDataProvider"),
    ProviderName.NASADEM: ("enable_nasadem", "nasadem", "NASADEMDataProvider"),
    ProviderName.GPM: ("enable_gpm", "gpm", "GPMDataProvider"),
    ProviderName.SMAP: ("enable_smap", "smap", "SMAPDataProvider"),
}
_ENABLE_FLAGS = {**{n: v[0] for n, v in _GRANULE.items()}, ProviderName.LANDSLIDE_CATALOG: "enable_landslide_catalog"}


def build_providers(settings: Settings, auth: Any, download_manager: Any) -> dict[str, DataProvider]:
    providers: dict[str, DataProvider] = {}
    for name, (flag, module, cls) in _GRANULE.items():
        if not getattr(settings, flag):
            continue
        try:  # lazy: a provider whose module is missing or broken is skipped, never fatal
            klass = getattr(importlib.import_module(f"app.services.data_acquisition.providers.{module}"), cls)
            providers[name.value] = klass(settings, auth, download_manager)
        except Exception as exc:
            log.warning("provider %s unavailable: %s: %s", name.value, type(exc).__name__, exc)
    return providers


def provider_statuses(settings: Settings, auth: Any, providers: dict[str, DataProvider], session: Session) -> list[ProviderStatus]:
    collections = dict(session.execute(
        select(DataCollection.provider, func.count()).group_by(DataCollection.provider)).all())
    last = dict(session.execute(
        select(DataAcquisition.provider, func.max(DataAcquisition.retrieved_at))
        .where(DataAcquisition.status == AcquisitionStatus.VALIDATED.value)
        .group_by(DataAcquisition.provider)).all())
    out = []
    for name in ProviderName:
        enabled = bool(getattr(settings, _ENABLE_FLAGS[name]))
        provider = providers.get(name.value)
        needs_auth = name != ProviderName.LANDSLIDE_CATALOG and (
            provider.requires_auth_for_download if provider else True)
        note = None
        if enabled and name != ProviderName.LANDSLIDE_CATALOG and provider is None:
            note = "enabled but the provider implementation could not be loaded"
        out.append(ProviderStatus(
            name=name.value, enabled=enabled, optional=name == ProviderName.SMAP,
            authentication=auth.status() if needs_auth else "not_required",
            collections_discovered=collections.get(name.value, 0),
            last_successful_acquisition=last.get(name.value), note=note,
        ))
    return out
