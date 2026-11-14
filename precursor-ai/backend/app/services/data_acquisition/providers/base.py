"""Provider contract. Every NASA/ASF source implements this; nothing else is coupled to a library."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from app.services.data_acquisition.types import (
    CollectionInfo,
    GranuleRecord,
    ProviderName,
    SearchQuery,
)

ProgressCallback = Callable[[int, int | None], None]  # (bytes_done, bytes_total_or_None)


class DataProvider(ABC):
    name: ProviderName
    #: True when downloads need Earthdata Login. Discovery/search never do.
    requires_auth_for_download: bool = True

    def __init__(self) -> None:
        #: Human-readable notes from the most recent call (e.g. "no VALIDATED SME2 collection exists",
        #: "collection X search failed: ..."). Reset at the start of each search_granules/search_collections.
        self.last_warnings: list[str] = []

    @abstractmethod
    def search_collections(self) -> list[CollectionInfo]:
        """Discover (verify against the live catalog) the collections this provider can serve.

        Must NOT assume a collection exists: return only what the catalog confirmed.
        """

    @abstractmethod
    def search_granules(self, query: SearchQuery) -> list[GranuleRecord]:
        """Metadata-only search. Must honour AOI intersection, dates, products, maturities, max_results."""

    @abstractmethod
    def get_granule_metadata(self, granule_id: str) -> GranuleRecord | None:
        """Re-fetch one granule from the catalog, or None if the catalog does not know it."""

    @abstractmethod
    def download_granule(
        self,
        granule: GranuleRecord,
        dest_dir: Path | None = None,
        *,
        progress: ProgressCallback | None = None,
    ) -> Path:
        """Fetch the granule's data file into dest_dir, or the storage.target_path layout when None (resumable, retried, atomic) and return its path.

        Delegates the byte transfer to DownloadManager; raises DownloadError / AuthenticationError.
        """
