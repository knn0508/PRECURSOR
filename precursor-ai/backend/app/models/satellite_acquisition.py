import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class SatelliteAcquisition(Base):
    __tablename__ = "satellite_acquisitions"
    __table_args__ = (Index("ix_acq_area_date", "area_id", "acquisition_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    satellite_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("satellite_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    area_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitored_areas.id", ondelete="CASCADE"), nullable=False
    )
    acquisition_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    orbit_direction: Mapped[str | None] = mapped_column(String(20))  # ASCENDING / DESCENDING
    polarization: Mapped[str | None] = mapped_column(String(20))  # VV, VH, HH, HV
    product_type: Mapped[str | None] = mapped_column(String(50))  # SLC, GRD, GUNW
    file_path: Mapped[str | None] = mapped_column(String(500))
    # Python attribute `metadata` is reserved by SQLAlchemy; the DB column is still "metadata".
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    processing_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source = relationship("SatelliteSource", back_populates="acquisitions")
    area = relationship("MonitoredArea", back_populates="acquisitions")
