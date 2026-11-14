"""phase 4 addendum: temporal kind, aligned file path, reference grid

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14 20:56:14.091854
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    
    op.add_column('environmental_layers', sa.Column('temporal_kind', sa.String(length=10), server_default='static', nullable=False))
    op.add_column('environmental_layers', sa.Column('aligned_file_path', sa.Text(), nullable=True))
    op.add_column('environmental_processing_runs', sa.Column('reference_grid', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    


def downgrade() -> None:
    
    op.drop_column('environmental_processing_runs', 'reference_grid')
    op.drop_column('environmental_layers', 'aligned_file_path')
    op.drop_column('environmental_layers', 'temporal_kind')
    
