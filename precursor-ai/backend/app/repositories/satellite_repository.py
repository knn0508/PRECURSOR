from sqlalchemy.orm import Session

from app.models import SatelliteAcquisition, SatelliteSource
from app.repositories.base import BaseRepository


class SatelliteSourceRepository(BaseRepository[SatelliteSource]):
    def __init__(self, db: Session):
        super().__init__(db, SatelliteSource)


class SatelliteAcquisitionRepository(BaseRepository[SatelliteAcquisition]):
    def __init__(self, db: Session):
        super().__init__(db, SatelliteAcquisition)
