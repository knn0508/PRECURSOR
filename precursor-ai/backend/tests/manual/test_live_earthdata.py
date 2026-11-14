"""MANUAL live test against NASA services. Never run in CI.

Needs REAL Earthdata credentials and DOWNLOADS REAL NASA DATA (part c). It is skipped unless:
  RUN_LIVE_EARTHDATA=1, EARTHDATA_USERNAME and EARTHDATA_PASSWORD are all set.
Optional: LIVE_AOI_FILE (tiny GeoJSON/WKT AOI) for the granule search;
          LIVE_DOWNLOAD_GRANULE_ID (a registered/searchable granule) for one download, refused if >= 50 MB.
Run: RUN_LIVE_EARTHDATA=1 pytest tests/manual/test_live_earthdata.py -s
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("RUN_LIVE_EARTHDATA") == "1" and os.getenv("EARTHDATA_USERNAME") and os.getenv("EARTHDATA_PASSWORD")),
    reason="manual live test: set RUN_LIVE_EARTHDATA=1 and EARTHDATA_USERNAME/EARTHDATA_PASSWORD",
)

MAX_BYTES = 50 * 1024**2


@pytest.fixture(scope="module")
def providers():
    from app.api.v1.data import deps

    return deps.get_providers()


def test_live_collection_discovery_all_providers(providers):
    assert providers, "no providers enabled"
    for name, p in providers.items():
        cols = p.search_collections()  # anonymous
        print(name, [(c.short_name, c.version) for c in cols], p.last_warnings)
        assert cols or p.last_warnings, f"{name}: no collections and no explanation"


@pytest.fixture(scope="module")
def aoi():
    path = os.getenv("LIVE_AOI_FILE")
    if not path:
        pytest.skip("set LIVE_AOI_FILE to a tiny AOI file")
    from app.services.data_acquisition.aoi import AOI

    return AOI.from_file(path)


def test_live_granule_search(providers, aoi):
    from app.services.data_acquisition.types import SearchQuery

    for name, p in providers.items():
        hits = p.search_granules(SearchQuery(aoi=aoi, max_results=3))
        print(name, [h.granule_id for h in hits], p.last_warnings)


def test_live_single_small_download(providers, aoi, tmp_path):
    from app.services.data_acquisition.types import SearchQuery

    gid = os.getenv("LIVE_DOWNLOAD_GRANULE_ID")
    if not gid:
        pytest.skip("set LIVE_DOWNLOAD_GRANULE_ID to download one small granule")
    for p in providers.values():
        hit = next((h for h in p.search_granules(SearchQuery(aoi=aoi, max_results=10)) if h.granule_id == gid), None)
        if hit:
            break
    else:
        pytest.skip("granule not found by any provider for LIVE_AOI_FILE")
    if hit.file_size_bytes is None or hit.file_size_bytes >= MAX_BYTES:
        pytest.skip(f"refusing: size {hit.file_size_bytes} is unknown or >= 50 MB")
    path = p.download_granule(hit, tmp_path)
    assert path.is_file() and path.stat().st_size > 0
