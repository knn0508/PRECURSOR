import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class LandslideEvent(Base):
    """NASA Global Landslide Catalog record.

    HISTORICAL REFERENCE ONLY: the Open Data Portal export is a one-time export whose last event is
    dated 2017-09-28. It is neither complete nor current; absence of an event proves nothing.
    """

    __tablename__ = "landslide_events"
    __table_args__ = (
        UniqueConstraint("external_event_id", "dataset_version", name="uq_event_id_version"),
        Index("ix_lsevent_date", "event_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_event_id: Mapped[str] = mapped_column(String(60), nullable=False)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location_name: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(100), index=True)
    trigger: Mapped[str | None] = mapped_column(String(100))
    landslide_type: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str | None] = mapped_column(Text)
    geometry = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    original_attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    dataset_version: Mapped[str] = mapped_column(String(60), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
