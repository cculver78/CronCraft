# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

"""Add account lockout columns to users table.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-11 18:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_locked', sa.Boolean(), server_default=sa.text('0'), nullable=True))
        batch_op.add_column(sa.Column('failed_login_attempts', sa.Integer(), server_default=sa.text('0'), nullable=True))
        batch_op.add_column(sa.Column('lock_token', sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('lock_token')
        batch_op.drop_column('failed_login_attempts')
        batch_op.drop_column('is_locked')
