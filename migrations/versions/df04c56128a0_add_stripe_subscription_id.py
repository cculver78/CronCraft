"""Add stripe subscription id

Revision ID: df04c56128a0
Revises: 83556a4cb07d
Create Date: 2026-03-18 10:48:07.591767

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'df04c56128a0'
down_revision = '83556a4cb07d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('stripe_subscription_id')
