"""add price_sheet_id to price_history

Revision ID: e7f1a2c3d4e5
Revises: c9f2e8b11a21
Create Date: 2026-06-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f1a2c3d4e5'
down_revision = 'c9f2e8b11a21'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('price_history', schema=None) as batch_op:
        batch_op.add_column(sa.Column('price_sheet_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_price_history_price_sheet_id_price_sheet',
            'price_sheet',
            ['price_sheet_id'],
            ['id']
        )

    op.create_index(
        'ix_price_history_sheet_item_company',
        'price_history',
        ['price_sheet_id', 'item_id', 'company_id'],
        unique=False
    )


def downgrade():
    op.drop_index('ix_price_history_sheet_item_company', table_name='price_history')

    with op.batch_alter_table('price_history', schema=None) as batch_op:
        batch_op.drop_constraint('fk_price_history_price_sheet_id_price_sheet', type_='foreignkey')
        batch_op.drop_column('price_sheet_id')
