from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.data.deps import get_search_service, invalid_as_422, resolve_aoi
from app.database.session import get_db
from app.schemas.data_acquisition import SearchRequest, SearchResponse
from app.services.data_acquisition.search_service import AcquisitionSearchService
from app.services.data_acquisition.types import Maturity, SearchQuery

router = APIRouter()


@router.post("/search", response_model=SearchResponse, summary="Search NISAR granules (metadata only)")
def search(req: SearchRequest, db: Session = Depends(get_db), svc: AcquisitionSearchService = Depends(get_search_service)):
    aoi, area_id = resolve_aoi(req.aoi, db)
    query = SearchQuery(
        aoi=aoi, start=req.start_date, end=req.end_date, product_types=tuple(req.products),
        maturities=tuple(Maturity(m) for m in req.maturities), max_results=req.max_results)
    with invalid_as_422():
        # NISAR only: `products` are NISAR product types; DEM/rainfall go through /environmental/acquire.
        out = svc.search(query, provider_names=["NISAR"], register=not req.dry_run, monitored_area_id=area_id)
    return SearchResponse(
        dry_run=req.dry_run, aoi_name=aoi.name, results=out.results, warnings=out.warnings,
        provider_errors=out.provider_errors)
