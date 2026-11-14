"""phase 4: environmental layers features runs and earthquake events

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14 16:37:04.886853
"""
import geoalchemy2
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    
    op.create_table('earthquake_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('external_id', sa.String(length=60), nullable=False),
    sa.Column('event_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('magnitude', sa.Double(), nullable=True),
    sa.Column('magnitude_type', sa.String(length=10), nullable=True),
    sa.Column('depth_km', sa.Double(), nullable=True),
    sa.Column('place', sa.Text(), nullable=True),
    sa.Column('url', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('geometry', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('original_attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source', 'external_id', name='uq_quake_source_id')
    )
    op.create_index('ix_quake_time', 'earthquake_events', ['event_time'], unique=False)
    op.create_table('environmental_processing_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('area_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('current_stage', sa.String(length=30), nullable=True),
    sa.Column('stages', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('quality_report', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('cancel_requested', sa.Boolean(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['area_id'], ['monitored_areas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_envrun_area_status', 'environmental_processing_runs', ['area_id', 'status'], unique=False)
    op.create_table('environmental_features',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('area_id', sa.UUID(), nullable=False),
    sa.Column('feature_group', sa.String(length=30), nullable=False),
    sa.Column('values', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('units', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('lineage', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('measurement_kind', sa.String(length=30), nullable=False),
    sa.Column('data_origin', sa.String(length=30), nullable=False),
    sa.Column('status', sa.String(length=25), nullable=False),
    sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['area_id'], ['monitored_areas.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['environmental_processing_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'feature_group', name='uq_envfeat_run_group')
    )
    op.create_index('ix_envfeat_area_group', 'environmental_features', ['area_id', 'feature_group'], unique=False)
    op.create_index(op.f('ix_environmental_features_run_id'), 'environmental_features', ['run_id'], unique=False)
    op.create_table('environmental_layers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('area_id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=True),
    sa.Column('deformation_product_id', sa.UUID(), nullable=True),
    sa.Column('layer_type', sa.String(length=30), nullable=False),
    sa.Column('source_provider', sa.String(length=30), nullable=False),
    sa.Column('dataset_name', sa.String(length=200), nullable=False),
    sa.Column('dataset_version', sa.String(length=60), nullable=True),
    sa.Column('measurement_kind', sa.String(length=30), nullable=False),
    sa.Column('data_origin', sa.String(length=30), nullable=False),
    sa.Column('validation_status', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=25), nullable=False),
    sa.Column('input_hash', sa.String(length=64), nullable=True),
    sa.Column('file_path', sa.Text(), nullable=True),
    sa.Column('file_format', sa.String(length=20), nullable=True),
    sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
    sa.Column('checksum_sha256', sa.String(length=64), nullable=True),
    sa.Column('units', sa.String(length=120), nullable=True),
    sa.Column('crs', sa.String(length=40), nullable=True),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('nodata', sa.Double(), nullable=True),
    sa.Column('native_resolution', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('processing_resolution', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('temporal_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('temporal_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('footprint', geoalchemy2.types.Geometry(geometry_type='POLYGON', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('quality', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('statistics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['area_id'], ['monitored_areas.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['deformation_product_id'], ['deformation_products.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['run_id'], ['environmental_processing_runs.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_environmental_layers_area_id'), 'environmental_layers', ['area_id'], unique=False)
    op.create_index(op.f('ix_environmental_layers_deformation_product_id'), 'environmental_layers', ['deformation_product_id'], unique=False)
    op.create_index(op.f('ix_environmental_layers_run_id'), 'environmental_layers', ['run_id'], unique=False)
    op.create_index('ix_envlayer_area_kind', 'environmental_layers', ['area_id', 'layer_type'], unique=False)
    op.create_index('ix_envlayer_input_hash', 'environmental_layers', ['area_id', 'layer_type', 'input_hash'], unique=False)
    


def downgrade() -> None:
    
    op.drop_index('ix_envlayer_input_hash', table_name='environmental_layers')
    op.drop_index('ix_envlayer_area_kind', table_name='environmental_layers')
    op.drop_index(op.f('ix_environmental_layers_run_id'), table_name='environmental_layers')
    op.drop_index(op.f('ix_environmental_layers_deformation_product_id'), table_name='environmental_layers')
    op.drop_index(op.f('ix_environmental_layers_area_id'), table_name='environmental_layers')
    op.drop_table('environmental_layers')
    op.drop_index(op.f('ix_environmental_features_run_id'), table_name='environmental_features')
    op.drop_index('ix_envfeat_area_group', table_name='environmental_features')
    op.drop_table('environmental_features')
    op.drop_index('ix_envrun_area_status', table_name='environmental_processing_runs')
    op.drop_table('environmental_processing_runs')
    op.drop_index('ix_quake_time', table_name='earthquake_events')
    op.drop_table('earthquake_events')
    
