"""add shared analytics fact table

Revision ID: 1c7f4e9a2b6d
Revises: a3de420f077e
Create Date: 2026-08-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '1c7f4e9a2b6d'
down_revision = 'a3de420f077e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'analytics_fact',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fact_type', sa.String(length=32), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('location', sa.String(length=100), nullable=True),
        sa.Column('item_id', sa.Integer(), nullable=True),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('supplier_id', sa.Integer(), nullable=True),
        sa.Column('raw_product_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Float(), nullable=False, server_default='0'),
        sa.Column('revenue', sa.Float(), nullable=False, server_default='0'),
        sa.Column('cost', sa.Float(), nullable=False, server_default='0'),
        sa.Column('margin', sa.Float(), nullable=False, server_default='0'),
        sa.Column('labor_hours', sa.Float(), nullable=False, server_default='0'),
        sa.Column('source_table', sa.String(length=100), nullable=True),
        sa.Column('source_id', sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "fact_type IN ('item_sale', 'cost_margin', 'receiving', 'labor', 'inventory_snapshot', 'customer_order')",
            name='ck_analytics_fact_type',
        ),
        sa.UniqueConstraint(
            'fact_type', 'source_table', 'source_id',
            name='uq_analytics_fact_source',
        ),
        sa.ForeignKeyConstraint(['company_id'], ['company.id']),
        sa.ForeignKeyConstraint(['item_id'], ['item.id']),
        sa.ForeignKeyConstraint(['customer_id'], ['customer.id']),
        sa.ForeignKeyConstraint(['supplier_id'], ['grower_or_distributor.id']),
        sa.ForeignKeyConstraint(['raw_product_id'], ['raw_product.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    for column in ('fact_type', 'date', 'company_id', 'item_id', 'customer_id', 'supplier_id', 'raw_product_id'):
        op.create_index(f'ix_analytics_fact_{column}', 'analytics_fact', [column])


def downgrade():
    for column in ('fact_type', 'date', 'company_id', 'item_id', 'customer_id', 'supplier_id', 'raw_product_id'):
        op.drop_index(f'ix_analytics_fact_{column}', table_name='analytics_fact')
    op.drop_table('analytics_fact')