import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class MonitoredArea(Base):
    __tablename__ = "monitored_areas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(150))
    # EPSG:4326 (WGS84 lon/lat). GeoAlchemy2 creates a GiST spatial index automatically.
    geometry = mapped_column(Geometry("GEOMETRY", srid=4326), nullable=False)
    area_type: Mapped[str] = mapped_column(String(50), nullable=False, default="landslide_susceptible")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    acquisitions = relationship("SatelliteAcquisition", back_populates="area", cascade="all, delete-orphan")
