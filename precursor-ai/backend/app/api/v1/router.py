from fastapi import APIRouter

from app.api.v1 import acquisitions, areas, environmental, features_cv, health, insar, system
from app.api.v1.data.router import router as data_router

api_router = APIRouter()
api_router.include_router(acquisitions.router)
api_router.include_router(health.router)
api_router.include_router(system.router)
api_router.include_router(areas.router)
api_router.include_router(data_router)
api_router.include_router(insar.router)
api_router.include_router(environmental.router)
api_router.include_router(features_cv.router)
