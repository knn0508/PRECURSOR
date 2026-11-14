"""Catalog search across providers. Failures are isolated per provider; hits are metadata only."""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.schemas.data_acquisition import GranuleResult
from app.services.data_acquisition.metadata_service import MetadataRegistrationService, scrub
from app.services.data_acquisition.providers.base import DataProvider
from app.services.data_acquisition.types import CollectionInfo, Maturity, SearchQuery

log = logging.getLogger(__name__)
_RANK = {"VALIDATED": 0, None: 1, "PROVISIONAL": 2, "BETA": 3}


@dataclass
class SearchOutcome:
    results: list[GranuleResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provider_errors: dict[str, str] = field(default_factory=dict)


class AcquisitionSearchService:
    def __init__(
        self,
        providers: dict[str, DataProvider],
        session: Session | Callable[[], Session],
        settings: Settings | None = None,
    ):
        self.providers = providers
        self._session = session
        self.settings = settings or get_settings()

    @contextmanager
    def _open(self) -> Iterator[Session]:
        if callable(self._session):  # a session factory; a Session instance is not callable
            s = self._session()
            try:
                yield s
            finally:
                s.close()
        else:
            yield self._session

    def _selected(self, names: list[str] | None) -> dict[str, DataProvider]:
        return {n: p for n, p in self.providers.items() if names is None or n in names}

    def search(
        self,
        query: SearchQuery,
        *,
        provider_names: list[str] | None = None,
        register: bool = True,
        monitored_area_id: UUID | None = None,
    ) -> SearchOutcome:
        s = self.settings
        query.aoi.validate_size(s.max_aoi_bbox_degrees)
        if query.start and query.end and query.start > query.end:
            raise ValueError("start date must not be after end date")
        allowed = set(s.allowed_maturity_list)
        maturities = tuple(m for m in query.maturities if m.value in allowed)
        if not maturities:
            raise ValueError(
                f"requested maturities {[m.value for m in query.maturities]} are not enabled "
                f"(ALLOWED_MATURITIES={sorted(allowed)})"
            )
        q = replace(query, maturities=maturities, max_results=max(1, min(query.max_results, s.max_granules_per_request)))

        out = SearchOutcome()
        hits = []
        for name, provider in self._selected(provider_names).items():
            try:
                found = provider.search_granules(q)
            except Exception as exc:  # isolate: one provider never stops the others
                log.warning("provider %s search failed: %s", name, type(exc).__name__)
                out.provider_errors[name] = scrub(exc, s) or type(exc).__name__
                continue
            out.warnings += [f"{name}: {w}" for w in provider.last_warnings]
            # a provider must not smuggle in a maturity the caller did not allow
            hits += [r for r in found if r.maturity is None or r.maturity in maturities]

        with self._open() as session:
            svc = MetadataRegistrationService(session)
            existing: dict[tuple[str, str], Any] = {}
            for name in {h.provider.value for h in hits}:
                existing.update({
                    (name, gid): a for gid, a in
                    svc.existing_by_granule_ids(name, [h.granule_id for h in hits if h.provider.value == name]).items()
                })
            for h in hits:
                acq = existing.get((h.provider.value, h.granule_id))
                if register:
                    acq, _ = svc.register_granule(h, svc.ensure_collection(h), monitored_area_id)
                out.results.append(svc.to_granule_result(acq if register else h, acq))

        out.results.sort(key=lambda r: (
            _RANK.get(r.maturity, 9), -(r.acquisition_start.timestamp() if r.acquisition_start else 0)))
        return out

    def discover_collections(self, register: bool = True) -> tuple[list[CollectionInfo], list[str]]:
        found: list[CollectionInfo] = []
        warnings: list[str] = []
        for name, provider in self.providers.items():
            try:
                cols = provider.search_collections()
            except Exception as exc:
                log.warning("provider %s collection discovery failed: %s", name, type(exc).__name__)
                warnings.append(f"{name}: collection discovery failed: {scrub(exc, self.settings)}")
                continue
            warnings += [f"{name}: {w}" for w in provider.last_warnings]
            found += cols
        if register and found:
            with self._open() as session:
                svc = MetadataRegistrationService(session)
                for c in found:
                    svc.upsert_collection(c)
        return found, warnings
