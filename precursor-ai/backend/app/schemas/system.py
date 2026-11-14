from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app_name: str
    version: str
    database: Literal["connected", "unavailable"]


class ModuleInfo(BaseModel):
    name: str
    status: Literal["available", "planned"]
    description: str


class SystemInfo(BaseModel):
    app_name: str
    version: str
    environment: str
    modules: list[ModuleInfo]
