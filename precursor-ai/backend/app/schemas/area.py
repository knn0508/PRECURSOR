import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from shapely.geometry import shape
from shapely.errors import GeometryTypeError

ALLOWED_GEOMETRIES = {"Polygon", "MultiPolygon"}


class AreaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    country: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=150)
    area_type: str = Field(default="landslide_susceptible", max_length=50)
    geometry: dict[str, Any] = Field(description="GeoJSON Polygon/MultiPolygon in EPSG:4326 (lon, lat)")

    @field_validator("geometry")
    @classmethod
    def validate_geojson(cls, v: dict[str, Any]) -> dict[str, Any]:
        if v.get("type") not in ALLOWED_GEOMETRIES:
            raise ValueError("geometry must be a GeoJSON Polygon or MultiPolygon")
        try:
            geom = shape(v)
        except (GeometryTypeError, ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"invalid GeoJSON geometry: {exc}") from exc
        if geom.is_empty or not geom.is_valid:
            raise ValueError("geometry is empty or topologically invalid")
        minx, miny, maxx, maxy = geom.bounds
        if not (-180 <= minx and maxx <= 180 and -90 <= miny and maxy <= 90):
            raise ValueError("coordinates must be lon/lat within EPSG:4326 bounds")
        return v


class AreaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    country: str | None
    region: str | None
    area_type: str
    geometry: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AreaList(BaseModel):
    items: list[AreaRead]
    total: int
