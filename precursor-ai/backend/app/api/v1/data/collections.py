import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.data.deps import get_search_service
from app.core.exceptions import NotFoundError
from app.database.session import get_db
from app.models import DataCollection
from app.schemas.data_acquisition import CollectionRead
from app.services.data_acquisition.search_service import AcquisitionSearchService

router = APIRouter()


@router.get("/collections", response_model=list[CollectionRead], summary="Verified NASA/ASF collections")
def list_collections(
    provider: str | None = Query(None),
    refresh: bool = Query(False, description="Re-discover from the live catalog first (anonymous)"),
    db: Session = Depends(get_db),
    search: AcquisitionSearchService = Depends(get_search_service),
):
    if refresh:
        search.discover_collections()  # per-provider isolation lives in the service
        db.expire_all()
    q = select(DataCollection).order_by(DataCollection.provider, DataCollection.collection_short_name)
    if provider:
        q = q.where(DataCollection.provider == provider.upper())
    return list(db.scalars(q))


@router.get("/collections/{collection_id}", response_model=CollectionRead)
def get_collection(collection_id: uuid.UUID, db: Session = Depends(get_db)):
    col = db.get(DataCollection, collection_id)
    if col is None:
        raise NotFoundError(f"Collection {collection_id} not found")
    return col
