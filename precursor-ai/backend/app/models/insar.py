import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class InSARProcessingRun(Base):
    """One traceable processing attempt on one input. Stage history and the quality report are JSONB: they are
    only ever read together with the run, so separate tables would add joins without adding queries."""

    __tablename__ = "insar_processing_runs"
    __table_args__ = (
        Index("ix_insar_run_status", "status"),
        Index("ix_insar_run_input_cfg", "input_ref", "config_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # SET NULL: a run keeps its provenance (input_ref) even if the acquisition row is later removed.
    acquisition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_acquisitions.id", ondelete="SET NULL"), index=True
    )
    input_kind: Mapped[str] = mapped_column(String(20), nullable=False)  # ACQUISITION | SAMPLE
    input_ref: Mapped[str] = mapped_column(String(400), nullable=False)  # granule id or sample file name
    product_kind: Mapped[str | None] = mapped_column(String(20))
    data_origin: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    current_stage: Mapped[str | None] = mapped_column(String(30))
    progress: Mapped[float] = mapped_column(nullable=False, default=0.0)
    stages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    inspection: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    quality_report: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    products = relationship("DeformationProduct", back_populates="run", cascade="all, delete-orphan")


class DeformationProduct(Base):
    """A derived raster. The file lives on disk (path relative to DATA_ROOT); the footprint is PostGIS because
    later phases need spatial joins against it."""

    __tablename__ = "deformation_products"
    __table_args__ = (Index("ix_defprod_kind", "product_type"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("insar_processing_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    acquisition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_acquisitions.id", ondelete="SET NULL"), index=True
    )
    product_type: Mapped[str] = mapped_column(String(30), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)  # relative to DATA_ROOT
    file_format: Mapped[str] = mapped_column(String(20), nullable=False, default="COG")
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    units: Mapped[str] = mapped_column(String(30), nullable=False)
    crs: Mapped[str | None] = mapped_column(String(30))
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    secondary_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_origin: Mapped[str] = mapped_column(String(30), nullable=False)
    sign_convention: Mapped[str | None] = mapped_column(Text)
    scientifically_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    statistics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    footprint = mapped_column(Geometry("POLYGON", srid=4326))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run = relationship("InSARProcessingRun", back_populates="products")
