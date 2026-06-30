"""add current item price table

Revision ID: c9f2e8b11a21
Revises: 8a547e06531c
Create Date: 2026-06-29 11:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9f2e8b11a21'
down_revision = '8a547e06531c'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'current_item_price',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['item_id'], ['item.id']),
        sa.ForeignKeyConstraint(['company_id'], ['company.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('item_id')
    )

    conn = op.get_bind()

    distinct_rows = conn.execute(
        sa.text(
            """
            SELECT DISTINCT company_id, item_id
            FROM price_history
            """
        )
    ).fetchall()

    for row in distinct_rows:
        latest = conn.execute(
            sa.text(
                """
                SELECT price, date
                FROM price_history
                WHERE company_id = :company_id AND item_id = :item_id
                ORDER BY date DESC, id DESC
                LIMIT 1
                """
            ),
            {'company_id': row.company_id, 'item_id': row.item_id}
        ).fetchone()

        if latest is None:
            continue

        conn.execute(
            sa.text(
                """
                INSERT INTO current_item_price (item_id, company_id, price, effective_date, updated_at)
                VALUES (:item_id, :company_id, :price, :effective_date, CURRENT_TIMESTAMP)
                """
            ),
            {
                'item_id': row.item_id,
                'company_id': row.company_id,
                'price': latest.price,
                'effective_date': latest.date,
            }
        )


def downgrade():
    op.drop_table('current_item_price')
