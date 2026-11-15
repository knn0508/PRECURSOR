from fastapi import APIRouter

from app.api.v1 import acquisitions, areas, displacement_forecast, environmental, features_cv, health, insar, prediction, system, timeseries, uncertainty
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
api_router.include_router(prediction.router)
api_router.include_router(uncertainty.router)
api_router.include_router(timeseries.router)
api_router.include_router(displacement_forecast.router)
