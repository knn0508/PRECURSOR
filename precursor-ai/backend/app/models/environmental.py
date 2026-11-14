import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, DateTime, Double, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class EnvironmentalProcessingRun(Base):
    """One pipeline run for one monitored area. Stage history and the quality report are JSONB (read with the run)."""

    __tablename__ = "environmental_processing_runs"
    __table_args__ = (Index("ix_envrun_area_status", "area_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitored_areas.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED")
    current_stage: Mapped[str | None] = mapped_column(String(30))
    stages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    quality_report: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reference_grid: Mapped[dict | None] = mapped_column(JSONB)  # common metric grid chosen by the REFERENCE_GRID stage
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    layers = relationship("EnvironmentalLayer", back_populates="run", cascade="all, delete-orphan")
    features = relationship("EnvironmentalFeature", back_populates="run", cascade="all, delete-orphan")


class EnvironmentalLayer(Base):
    """A processed (or referenced) environmental layer for an area. Files stay on disk (path relative to DATA_ROOT).

    INSAR_* layers are REFERENCES to Phase 3 `deformation_products` (file_path NULL); they are never copied or
    reinterpreted, and keep that product's data_origin so synthetic data stays labelled synthetic.
    """

    __tablename__ = "environmental_layers"
    __table_args__ = (
        Index("ix_envlayer_area_kind", "area_id", "layer_type"),
        Index("ix_envlayer_input_hash", "area_id", "layer_type", "input_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    area_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitored_areas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("environmental_processing_runs.id", ondelete="SET NULL"), index=True
    )
    deformation_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deformation_products.id", ondelete="SET NULL"), index=True
    )
    layer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_provider: Mapped[str] = mapped_column(String(30), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str | None] = mapped_column(String(60))
    measurement_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    data_origin: Mapped[str] = mapped_column(String(30), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_VALIDATED")
    status: Mapped[str] = mapped_column(String(25), nullable=False)
    temporal_kind: Mapped[str] = mapped_column(String(10), nullable=False, default="static", server_default="static")
    aligned_file_path: Mapped[str | None] = mapped_column(Text)  # raster resampled to the reference grid (relative to DATA_ROOT)
    input_hash: Mapped[str | None] = mapped_column(String(64))  # identical inputs+config -> stage can be skipped
    file_path: Mapped[str | None] = mapped_column(Text)  # relative to DATA_ROOT
    file_format: Mapped[str | None] = mapped_column(String(20))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    units: Mapped[str | None] = mapped_column(String(120))
    crs: Mapped[str | None] = mapped_column(String(40))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    nodata: Mapped[float | None] = mapped_column(Double)
    native_resolution: Mapped[dict | None] = mapped_column(JSONB)
    processing_resolution: Mapped[dict | None] = mapped_column(JSONB)
    temporal_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    temporal_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    footprint = mapped_column(Geometry("POLYGON", srid=4326))
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    quality: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    statistics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run = relationship("EnvironmentalProcessingRun", back_populates="layers")


class EnvironmentalFeature(Base):
    """Descriptive features of one group (terrain, rainfall, ...) for one run. Values, units and lineage are JSONB.
    Features are summaries of observations; they are NOT risk scores and never contain a prediction."""

    __tablename__ = "environmental_features"
    __table_args__ = (
        UniqueConstraint("run_id", "feature_group", name="uq_envfeat_run_group"),
        Index("ix_envfeat_area_group", "area_id", "feature_group"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environmental_processing_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitored_areas.id", ondelete="CASCADE"), nullable=False)
    feature_group: Mapped[str] = mapped_column(String(30), nullable=False)
    values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    units: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    lineage: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # layer ids + provenance dicts
    measurement_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="STATISTICAL_SUMMARY")
    data_origin: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(25), nullable=False)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run = relationship("EnvironmentalProcessingRun", back_populates="features")


class EarthquakeEvent(Base):
    """A USGS earthquake catalog record, stored as an independent observation. Not linked to any landslide."""

    __tablename__ = "earthquake_events"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_quake_source_id"),
        Index("ix_quake_time", "event_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="USGS")
    external_id: Mapped[str] = mapped_column(String(60), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    magnitude: Mapped[float | None] = mapped_column(Double)
    magnitude_type: Mapped[str | None] = mapped_column(String(10))
    depth_km: Mapped[float | None] = mapped_column(Double)
    place: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(20))  # reviewed / automatic, as reported by USGS
    geometry = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    original_attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
