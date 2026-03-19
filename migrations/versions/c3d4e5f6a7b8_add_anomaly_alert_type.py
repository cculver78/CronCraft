# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

"""Add anomaly alert type

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-19 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None

OLD_ALERT_TYPES = ('missed', 'recovered', 'failed', 'dependency_failed')
NEW_ALERT_TYPES = ('missed', 'recovered', 'failed', 'dependency_failed', 'anomaly')


def upgrade():
    # batch_alter_table handles both SQLite (table recreate) and MySQL
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.alter_column(
            'alert_type',
            existing_type=sa.Enum(*OLD_ALERT_TYPES),
            type_=sa.Enum(*NEW_ALERT_TYPES),
            existing_nullable=True
        )


def downgrade():
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.alter_column(
            'alert_type',
            existing_type=sa.Enum(*NEW_ALERT_TYPES),
            type_=sa.Enum(*OLD_ALERT_TYPES),
            existing_nullable=True
        )
