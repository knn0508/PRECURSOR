from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MonitoredArea
from app.repositories.base import BaseRepository


class AreaRepository(BaseRepository[MonitoredArea]):
    def __init__(self, db: Session):
        super().__init__(db, MonitoredArea)

    def list(self, offset: int = 0, limit: int = 100) -> list[MonitoredArea]:
        stmt = select(MonitoredArea).order_by(MonitoredArea.created_at.desc()).offset(offset).limit(limit)
        return list(self.db.scalars(stmt))
