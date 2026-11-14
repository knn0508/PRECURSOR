import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class DataAcquisition(Base):
    """One registered NASA granule. A row may be metadata-only (DISCOVERED) or have a file on disk.

    Distinct from the Phase 1 `satellite_acquisitions` table, which is left untouched.
    """

    __tablename__ = "data_acquisitions"
    __table_args__ = (
        UniqueConstraint("provider", "granule_id", name="uq_acq_provider_granule"),
        Index("ix_dacq_start", "acquisition_start"),
        Index("ix_dacq_status", "status"),
        Index("ix_dacq_product_maturity", "product_type", "maturity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # SET NULL: deleting an area must not erase the provenance of files already on disk.
    monitored_area_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("monitored_areas.id", ondelete="SET NULL"), index=True
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_collections.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    granule_id: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    product_type: Mapped[str] = mapped_column(String(50), nullable=False)
    acquisition_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acquisition_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    orbit_direction: Mapped[str | None] = mapped_column(String(20))
    relative_orbit: Mapped[int | None] = mapped_column(Integer)
    spatial_footprint = mapped_column(Geometry("GEOMETRY", srid=4326))
    crs: Mapped[str] = mapped_column(String(30), nullable=False, default="EPSG:4326")
    file_format: Mapped[str | None] = mapped_column(String(30))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    download_url: Mapped[str | None] = mapped_column(Text)
    local_file_path: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(String(128))
    checksum_algorithm: Mapped[str | None] = mapped_column(String(20))
    maturity: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DISCOVERED")
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # set when a file lands
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    validation_report: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    collection = relationship("DataCollection", back_populates="acquisitions")
    jobs = relationship("DownloadJob", back_populates="acquisition", cascade="all, delete-orphan")
