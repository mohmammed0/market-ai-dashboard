"""widen broker_position_snapshots.side to VARCHAR(32)

Revision ID: 20260412_0008
Revises: 20260410_0007
Create Date: 2026-04-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260412_0008"
down_revision = "20260410_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("broker_position_snapshots") as batch_op:
        batch_op.alter_column(
            "side",
            existing_type=sa.String(12),
            type_=sa.String(32),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("broker_position_snapshots") as batch_op:
        batch_op.alter_column(
            "side",
            existing_type=sa.String(32),
            type_=sa.String(12),
            existing_nullable=True,
        )
