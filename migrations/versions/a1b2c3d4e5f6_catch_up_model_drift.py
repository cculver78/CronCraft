# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

"""Catch up model drift

Adds columns that were created outside of migrations (via db.create_all or
raw ALTER TABLE) so Alembic's version history matches reality.

Revision ID: a1b2c3d4e5f6
Revises: df04c56128a0
Create Date: 2026-03-19 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'df04c56128a0'
branch_labels = None
depends_on = None


def upgrade():
    # --- users table: 9 missing columns ---
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('timezone', sa.String(length=50), nullable=True, server_default='UTC'))
        batch_op.add_column(sa.Column('username', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('display_name', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('email_verified', sa.Boolean(), nullable=True, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('is_admin', sa.Boolean(), nullable=True, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('plan_started_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('date_format', sa.String(length=20), nullable=True, server_default='YYYY-MM-DD'))
        batch_op.add_column(sa.Column('time_format', sa.String(length=10), nullable=True, server_default='24h'))
        batch_op.add_column(sa.Column('grace_period_end', sa.DateTime(), nullable=True))
        batch_op.create_unique_constraint('uq_users_username', ['username'])

    # --- jobs table: 2 missing columns ---
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notes', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('miss_count', sa.Integer(), nullable=True, server_default=sa.text('0')))


def downgrade():
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_column('miss_count')
        batch_op.drop_column('notes')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_username', type_='unique')
        batch_op.drop_column('grace_period_end')
        batch_op.drop_column('time_format')
        batch_op.drop_column('date_format')
        batch_op.drop_column('plan_started_at')
        batch_op.drop_column('is_admin')
        batch_op.drop_column('email_verified')
        batch_op.drop_column('display_name')
        batch_op.drop_column('username')
        batch_op.drop_column('timezone')
