"""phase 3: insar processing runs and deformation products

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14 14:36:51.287326
"""
import geoalchemy2
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    
    op.create_table('insar_processing_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('acquisition_id', sa.UUID(), nullable=True),
    sa.Column('input_kind', sa.String(length=20), nullable=False),
    sa.Column('input_ref', sa.String(length=400), nullable=False),
    sa.Column('product_kind', sa.String(length=20), nullable=True),
    sa.Column('data_origin', sa.String(length=30), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('current_stage', sa.String(length=30), nullable=True),
    sa.Column('progress', sa.Double(), nullable=False),
    sa.Column('stages', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('config_hash', sa.String(length=64), nullable=False),
    sa.Column('inspection', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('quality_report', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('cancel_requested', sa.Boolean(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['acquisition_id'], ['data_acquisitions.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_insar_processing_runs_acquisition_id'), 'insar_processing_runs', ['acquisition_id'], unique=False)
    op.create_index('ix_insar_run_input_cfg', 'insar_processing_runs', ['input_ref', 'config_hash'], unique=False)
    op.create_index('ix_insar_run_status', 'insar_processing_runs', ['status'], unique=False)
    op.create_table('deformation_products',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('acquisition_id', sa.UUID(), nullable=True),
    sa.Column('product_type', sa.String(length=30), nullable=False),
    sa.Column('file_path', sa.Text(), nullable=False),
    sa.Column('file_format', sa.String(length=20), nullable=False),
    sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
    sa.Column('units', sa.String(length=30), nullable=False),
    sa.Column('crs', sa.String(length=30), nullable=True),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('reference_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('secondary_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('data_origin', sa.String(length=30), nullable=False),
    sa.Column('sign_convention', sa.Text(), nullable=True),
    sa.Column('scientifically_validated', sa.Boolean(), nullable=False),
    sa.Column('statistics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('footprint', geoalchemy2.types.Geometry(geometry_type='POLYGON', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['acquisition_id'], ['data_acquisitions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['run_id'], ['insar_processing_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_deformation_products_acquisition_id'), 'deformation_products', ['acquisition_id'], unique=False)
    op.create_index(op.f('ix_deformation_products_run_id'), 'deformation_products', ['run_id'], unique=False)
    op.create_index('ix_defprod_kind', 'deformation_products', ['product_type'], unique=False)
    


def downgrade() -> None:
    
    op.drop_index('ix_defprod_kind', table_name='deformation_products')
    op.drop_index(op.f('ix_deformation_products_run_id'), table_name='deformation_products')
    op.drop_index(op.f('ix_deformation_products_acquisition_id'), table_name='deformation_products')
    op.drop_table('deformation_products')
    op.drop_index('ix_insar_run_status', table_name='insar_processing_runs')
    op.drop_index('ix_insar_run_input_cfg', table_name='insar_processing_runs')
    op.drop_index(op.f('ix_insar_processing_runs_acquisition_id'), table_name='insar_processing_runs')
    op.drop_table('insar_processing_runs')
    
