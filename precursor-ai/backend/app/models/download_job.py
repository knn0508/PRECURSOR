import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class DownloadJob(Base):
    __tablename__ = "download_jobs"
    __table_args__ = (Index("ix_djob_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    acquisition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_acquisitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 0..1, real bytes only
    bytes_downloaded: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    acquisition = relationship("DataAcquisition", back_populates="jobs")
