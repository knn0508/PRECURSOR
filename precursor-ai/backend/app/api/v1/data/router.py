from fastapi import APIRouter

from app.api.v1.data import acquisitions, collections, downloads, environmental, landslide_events, search, status

router = APIRouter(prefix="/data", tags=["data"])
for m in (collections, search, acquisitions, downloads, environmental, landslide_events, status):
    router.include_router(m.router)
