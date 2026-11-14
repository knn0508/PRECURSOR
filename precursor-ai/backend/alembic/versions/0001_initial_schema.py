"""initial schema: monitored areas, satellite sources, acquisitions

Revision ID: 0001
Revises:
Create Date: 2026-11-13
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "monitored_areas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("country", sa.String(100)),
        sa.Column("region", sa.String(150)),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry("GEOMETRY", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("area_type", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "idx_monitored_areas_geometry", "monitored_areas", ["geometry"], postgresql_using="gist"
    )

    op.create_table(
        "satellite_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("satellite_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "satellite_acquisitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "satellite_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("satellite_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "area_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("monitored_areas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("acquisition_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("orbit_direction", sa.String(20)),
        sa.Column("polarization", sa.String(20)),
        sa.Column("product_type", sa.String(50)),
        sa.Column("file_path", sa.String(500)),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("processing_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_satellite_acquisitions_satellite_source_id", "satellite_acquisitions", ["satellite_source_id"])
    op.create_index("ix_acq_area_date", "satellite_acquisitions", ["area_id", "acquisition_date"])


def downgrade() -> None:
    op.drop_table("satellite_acquisitions")
    op.drop_table("satellite_sources")
    op.drop_table("monitored_areas")
