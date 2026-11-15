from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.system import ModuleInfo, SystemInfo

router = APIRouter(prefix="/system", tags=["system"])

# Honest module registry: only foundation modules are "available" in Phase 1.
MODULES = [
    ModuleInfo(name="api", status="available", description="REST API and health checks"),
    ModuleInfo(name="monitored_areas", status="available", description="Area of interest registry (PostGIS)"),
    ModuleInfo(name="satellite_catalog", status="available", description="Satellite source/acquisition metadata"),
    ModuleInfo(name="data_acquisition", status="available", description="NASA data acquisition: NISAR, NASADEM, GPM, landslide catalog"),
    ModuleInfo(name="insar", status="available", description="InSAR processing of acquired NISAR products (real files only; no real NISAR file has been processed yet)"),
    ModuleInfo(name="time_series", status="available", description="Descriptive time-series analysis of stored series (Phase 6)"),
    ModuleInfo(name="displacement_forecast", status="available", description="Research 12-day LOS forecast: read-only third-party result bundle, not a warning (ADR-0011)"),
    ModuleInfo(name="risk_assessment", status="planned", description="Landslide risk scoring"),
    ModuleInfo(name="uncertainty", status="planned", description="Uncertainty quantification"),
    ModuleInfo(name="explainability", status="planned", description="Explainable AI"),
]


@router.get("/info", response_model=SystemInfo)
def system_info(settings: Settings = Depends(get_settings)) -> SystemInfo:
    return SystemInfo(
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        modules=MODULES,
    )
