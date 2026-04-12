"""runtime settings store

Revision ID: 20260407_0003
Revises: 20260407_0002
Create Date: 2026-04-07 18:00:00.000000
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260407_0003"
down_revision = "20260407_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_tables = set() if context.is_offline_mode() else set(inspect(op.get_bind()).get_table_names())
    if "runtime_settings" in existing_tables:
        return

    op.create_table(
        "runtime_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_runtime_settings_id", "runtime_settings", ["id"], unique=False)
    op.create_index("ix_runtime_settings_is_secret", "runtime_settings", ["is_secret"], unique=False)
    op.create_index("ix_runtime_settings_key", "runtime_settings", ["key"], unique=True)
    op.create_index("ix_runtime_settings_updated_at", "runtime_settings", ["updated_at"], unique=False)


def downgrade() -> None:
    existing_tables = {"runtime_settings"} if context.is_offline_mode() else set(inspect(op.get_bind()).get_table_names())
    if "runtime_settings" not in existing_tables:
        return
    op.drop_index("ix_runtime_settings_updated_at", table_name="runtime_settings")
    op.drop_index("ix_runtime_settings_key", table_name="runtime_settings")
    op.drop_index("ix_runtime_settings_is_secret", table_name="runtime_settings")
    op.drop_index("ix_runtime_settings_id", table_name="runtime_settings")
    op.drop_table("runtime_settings")
