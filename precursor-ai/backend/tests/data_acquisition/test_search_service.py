import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.models.data_acquisition import DataAcquisition
from app.services.data_acquisition.aoi import AOI
from app.services.data_acquisition.search_service import AcquisitionSearchService
from app.services.data_acquisition.types import AOIError, Maturity, ProviderName, SearchQuery
from tests.data_acquisition.fakes import FakeProvider, make_record


def _q(polygon, **kw):
    return SearchQuery(aoi=AOI.from_geojson("t", polygon), **kw)


def _count(db):
    return db.scalar(select(func.count()).select_from(DataAcquisition))


def test_register_then_dry_run_writes_nothing(db, polygon):
    prov = FakeProvider(records=[make_record("A")])
    svc = AcquisitionSearchService({"NISAR": prov}, db, Settings())
    dry = svc.search(_q(polygon), register=False)
    assert _count(db) == 0 and not dry.results[0].registered
    assert dry.warnings == ["NISAR: fake warning"]
    real = svc.search(_q(polygon))
    assert _count(db) == 1 and real.results[0].registered and real.results[0].status == "DISCOVERED"
    svc.search(_q(polygon))
    assert _count(db) == 1  # re-search is idempotent


def test_provider_failure_is_isolated(db, polygon):
    bad = FakeProvider(ProviderName.GPM, fail_search=RuntimeError("boom https://x/y?token=SECRET"))
    good = FakeProvider(records=[make_record("A")])
    out = AcquisitionSearchService({"GPM": bad, "NISAR": good}, db, Settings()).search(_q(polygon))
    assert len(out.results) == 1
    assert set(out.provider_errors) == {"GPM"} and "SECRET" not in out.provider_errors["GPM"]


def test_maturity_filter_and_ordering(db, polygon):
    recs = [make_record("B", Maturity.PROVISIONAL, day=5), make_record("V1", day=1), make_record("V2", day=9)]
    prov = FakeProvider(records=recs)
    settings = Settings(allowed_maturities="VALIDATED,PROVISIONAL")
    svc = AcquisitionSearchService({"NISAR": prov}, db, settings)
    out = svc.search(_q(polygon, maturities=(Maturity.VALIDATED, Maturity.PROVISIONAL, Maturity.BETA)))
    assert [r.granule_id for r in out.results] == ["V2", "V1", "B"]
    with pytest.raises(ValueError):  # BETA is not enabled at all
        svc.search(_q(polygon, maturities=(Maturity.BETA,)))
    # a provider returning a non-allowed maturity is filtered out
    prov.records = [make_record("X", Maturity.BETA)]
    assert svc.search(_q(polygon), register=False).results == []


def test_aoi_too_large_and_bad_dates(db):
    big = {"type": "Polygon", "coordinates": [[[0, 0], [20, 0], [20, 20], [0, 20], [0, 0]]]}
    svc = AcquisitionSearchService({"NISAR": FakeProvider()}, db, Settings())
    with pytest.raises(AOIError):
        svc.search(SearchQuery(aoi=AOI.from_geojson("big", big)))
    from datetime import datetime
    with pytest.raises(ValueError):
        svc.search(SearchQuery(aoi=AOI.from_geojson("x", big | {"coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}),
                               start=datetime(2026, 2, 1), end=datetime(2026, 1, 1)))


def test_discover_collections_isolated_and_persisted(db):
    ok = FakeProvider()
    bad = FakeProvider(ProviderName.GPM, fail_search=RuntimeError("down"))
    cols, warnings = AcquisitionSearchService({"NISAR": ok, "GPM": bad}, db, Settings()).discover_collections()
    assert len(cols) == 1 and any("GPM" in w and "down" in w for w in warnings)
    from app.models.data_collection import DataCollection
    assert db.scalar(select(func.count()).select_from(DataCollection)) == 1
