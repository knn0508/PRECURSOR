"""phase 2: data collections, acquisitions, download jobs, landslide events

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "data_collections",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("collection_short_name", sa.String(120), nullable=False),
        sa.Column("dataset_name", sa.String(300), nullable=False),
        sa.Column("product_type", sa.String(50), nullable=False),
        sa.Column("version", sa.String(30), nullable=False),
        sa.Column("maturity", sa.String(20)),
        sa.Column("description", sa.Text()),
        sa.Column("documentation_url", sa.String(500)),
        sa.Column("cmr_concept_id", sa.String(60)),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("discovered_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("collection_short_name", "version", name="uq_collection_name_version"),
    )
    op.create_index("ix_data_collections_provider", "data_collections", ["provider"])
    op.create_index("ix_data_collections_product_type", "data_collections", ["product_type"])
    op.create_index("ix_data_collections_maturity", "data_collections", ["maturity"])

    op.create_table(
        "data_acquisitions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("monitored_area_id", UUID, sa.ForeignKey("monitored_areas.id", ondelete="SET NULL")),
        sa.Column("collection_id", UUID, sa.ForeignKey("data_collections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("granule_id", sa.String(300), nullable=False),
        sa.Column("product_type", sa.String(50), nullable=False),
        sa.Column("acquisition_start", TS),
        sa.Column("acquisition_end", TS),
        sa.Column("processing_date", TS),
        sa.Column("orbit_direction", sa.String(20)),
        sa.Column("relative_orbit", sa.Integer()),
        sa.Column("spatial_footprint", geoalchemy2.Geometry("GEOMETRY", srid=4326, spatial_index=False)),
        sa.Column("crs", sa.String(30), nullable=False, server_default="EPSG:4326"),
        sa.Column("file_format", sa.String(30)),
        sa.Column("file_size_bytes", sa.BigInteger()),
        sa.Column("download_url", sa.Text()),
        sa.Column("local_file_path", sa.Text()),
        sa.Column("checksum", sa.String(128)),
        sa.Column("checksum_algorithm", sa.String(20)),
        sa.Column("maturity", sa.String(20)),
        sa.Column("status", sa.String(20), nullable=False, server_default="DISCOVERED"),
        sa.Column("retrieved_at", TS),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("validation_report", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "granule_id", name="uq_acq_provider_granule"),
    )
    op.create_index("ix_data_acquisitions_monitored_area_id", "data_acquisitions", ["monitored_area_id"])
    op.create_index("ix_data_acquisitions_collection_id", "data_acquisitions", ["collection_id"])
    op.create_index("ix_dacq_start", "data_acquisitions", ["acquisition_start"])
    op.create_index("ix_dacq_status", "data_acquisitions", ["status"])
    op.create_index("ix_dacq_product_maturity", "data_acquisitions", ["product_type", "maturity"])
    op.create_index("idx_data_acquisitions_spatial_footprint", "data_acquisitions", ["spatial_footprint"], postgresql_using="gist")
    op.create_index("ix_data_acquisitions_granule_id", "data_acquisitions", ["granule_id"])

    op.create_table(
        "download_jobs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("acquisition_id", UUID, sa.ForeignKey("data_acquisitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("bytes_downloaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", TS),
        sa.Column("completed_at", TS),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_download_jobs_acquisition_id", "download_jobs", ["acquisition_id"])
    op.create_index("ix_djob_status", "download_jobs", ["status"])

    op.create_table(
        "landslide_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("external_event_id", sa.String(60), nullable=False),
        sa.Column("event_date", TS),
        sa.Column("location_name", sa.Text()),
        sa.Column("country", sa.String(100)),
        sa.Column("trigger", sa.String(100)),
        sa.Column("landslide_type", sa.String(100)),
        sa.Column("source", sa.Text()),
        sa.Column("geometry", geoalchemy2.Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("original_attributes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("dataset_version", sa.String(60), nullable=False),
        sa.Column("retrieved_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("external_event_id", "dataset_version", name="uq_event_id_version"),
    )
    op.create_index("ix_landslide_events_country", "landslide_events", ["country"])
    op.create_index("ix_lsevent_date", "landslide_events", ["event_date"])
    op.create_index("idx_landslide_events_geometry", "landslide_events", ["geometry"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("landslide_events")
    op.drop_table("download_jobs")
    op.drop_table("data_acquisitions")
    op.drop_table("data_collections")
