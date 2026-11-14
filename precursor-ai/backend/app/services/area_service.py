import uuid

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import mapping, shape
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models import MonitoredArea
from app.repositories.area_repository import AreaRepository
from app.schemas.area import AreaCreate, AreaList, AreaRead


def to_read_schema(area: MonitoredArea) -> AreaRead:
    return AreaRead(
        id=area.id,
        name=area.name,
        description=area.description,
        country=area.country,
        region=area.region,
        area_type=area.area_type,
        geometry=mapping(to_shape(area.geometry)),
        created_at=area.created_at,
        updated_at=area.updated_at,
    )


class AreaService:
    def __init__(self, db: Session):
        self.repo = AreaRepository(db)

    def list_areas(self, offset: int = 0, limit: int = 100) -> AreaList:
        items = [to_read_schema(a) for a in self.repo.list(offset, limit)]
        return AreaList(items=items, total=self.repo.count())

    def get_area(self, area_id: uuid.UUID) -> AreaRead:
        area = self.repo.get(area_id)
        if area is None:
            raise NotFoundError(f"Monitored area {area_id} not found")
        return to_read_schema(area)

    def create_area(self, payload: AreaCreate) -> AreaRead:
        data = payload.model_dump(exclude={"geometry"})
        area = MonitoredArea(**data, geometry=from_shape(shape(payload.geometry), srid=4326))
        return to_read_schema(self.repo.add(area))
