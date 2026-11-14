import uuid
from datetime import datetime

from pydantic import BaseModel


class AcquisitionRead(BaseModel):
    id: uuid.UUID
    satellite_source: str
    area_id: uuid.UUID
    acquisition_date: datetime
    orbit_direction: str | None
    polarization: str | None
    product_type: str | None
    processing_status: str


class AcquisitionList(BaseModel):
    items: list[AcquisitionRead]
    total: int
