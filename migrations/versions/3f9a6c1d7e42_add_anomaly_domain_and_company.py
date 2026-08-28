"""add domain and company_id to anomaly

Anomalies are now produced by per-domain detectors (pricing, efficiency,
receiving, inventory, sales) and must be scoped to a single company so the
Data Insights page never shows another tenant's data.

Revision ID: 3f9a6c1d7e42
Revises: 2d8e5f9a1c3b
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa


revision = '3f9a6c1d7e42'
down_revision = '2d8e5f9a1c3b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('anomaly', schema=None) as batch_op:
        batch_op.add_column(sa.Column('domain', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('company_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_anomaly_domain', ['domain'], unique=False)
        batch_op.create_index('ix_anomaly_company_id', ['company_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_anomaly_company_id', 'company', ['company_id'], ['id']
        )

    # Backfill so existing findings stay visible after the page starts scoping
    # by company. Every detector that existed before this migration was a
    # pricing check over item / raw_product, so the domain is known and the
    # company is derivable from the entity.
    op.execute("UPDATE anomaly SET domain = 'pricing' WHERE domain IS NULL")
    op.execute(
        """
        UPDATE anomaly SET company_id = (
            SELECT item.company_id FROM item WHERE item.id = anomaly.entity_id
        )
        WHERE company_id IS NULL AND entity_type = 'item'
        """
    )
    op.execute(
        """
        UPDATE anomaly SET company_id = (
            SELECT raw_product.company_id FROM raw_product
            WHERE raw_product.id = anomaly.entity_id
        )
        WHERE company_id IS NULL AND entity_type = 'raw_product'
        """
    )


def downgrade():
    with op.batch_alter_table('anomaly', schema=None) as batch_op:
        batch_op.drop_constraint('fk_anomaly_company_id', type_='foreignkey')
        batch_op.drop_index('ix_anomaly_company_id')
        batch_op.drop_index('ix_anomaly_domain')
        batch_op.drop_column('company_id')
        batch_op.drop_column('domain')
