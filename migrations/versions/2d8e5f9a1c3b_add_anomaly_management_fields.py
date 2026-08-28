"""add anomaly management fields

Revision ID: 2d8e5f9a1c3b
Revises: 1c7f4e9a2b6d
Create Date: 2026-08-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '2d8e5f9a1c3b'
down_revision = '1c7f4e9a2b6d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('anomaly', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reviewed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('reviewed_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('fixed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('fixed_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('notes', sa.Text(), nullable=True))

    with op.batch_alter_table('anomaly', schema=None) as batch_op:
        batch_op.create_index('ix_anomaly_status', ['status'])
        batch_op.create_foreign_key('fk_anomaly_reviewed_by_id', 'user', ['reviewed_by_id'], ['id'])
        batch_op.create_foreign_key('fk_anomaly_fixed_by_id', 'user', ['fixed_by_id'], ['id'])


def downgrade():
    with op.batch_alter_table('anomaly', schema=None) as batch_op:
        batch_op.drop_constraint('fk_anomaly_fixed_by_id', type_='foreignkey')
        batch_op.drop_constraint('fk_anomaly_reviewed_by_id', type_='foreignkey')
        batch_op.drop_index('ix_anomaly_status')

    with op.batch_alter_table('anomaly', schema=None) as batch_op:
        batch_op.drop_column('notes')
        batch_op.drop_column('fixed_by_id')
        batch_op.drop_column('fixed_at')
        batch_op.drop_column('reviewed_by_id')
        batch_op.drop_column('reviewed_at')
