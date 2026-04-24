"""added notifications table

Revision ID: f3b18a4c9d12
Revises: e84bede56e8e
Create Date: 2026-04-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3b18a4c9d12'
down_revision = 'e84bede56e8e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('link_url', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['company.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notification_user_id_created_at', 'notification', ['user_id', 'created_at'])


def downgrade():
    op.drop_index('ix_notification_user_id_created_at', table_name='notification')
    op.drop_table('notification')
