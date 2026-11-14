import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class DataCollection(Base):
    """A NASA/ASF collection verified against the live catalog (not assumed)."""

    __tablename__ = "data_collections"
    __table_args__ = (UniqueConstraint("collection_short_name", "version", name="uq_collection_name_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    collection_short_name: Mapped[str] = mapped_column(String(120), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(300), nullable=False)
    product_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(30), nullable=False)
    maturity: Mapped[str | None] = mapped_column(String(20), index=True)  # NISAR only
    description: Mapped[str | None] = mapped_column(Text)
    documentation_url: Mapped[str | None] = mapped_column(String(500))
    cmr_concept_id: Mapped[str | None] = mapped_column(String(60))
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    acquisitions = relationship("DataAcquisition", back_populates="collection")
