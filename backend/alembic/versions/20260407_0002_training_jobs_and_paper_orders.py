"""training jobs and paper orders

Revision ID: 20260407_0002
Revises: 20260407_0001
Create Date: 2026-04-07 14:00:00.000000
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260407_0002"
down_revision = "20260407_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_tables = set() if context.is_offline_mode() else set(inspect(op.get_bind()).get_table_names())

    if "paper_orders" not in existing_tables:
        op.create_table(
            "paper_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("client_order_id", sa.String(length=80), nullable=False),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("strategy_mode", sa.String(length=20), nullable=True),
            sa.Column("side", sa.String(length=10), nullable=False),
            sa.Column("order_type", sa.String(length=20), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("limit_price", sa.Float(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_paper_orders_client_order_id", "paper_orders", ["client_order_id"], unique=True)
        op.create_index("ix_paper_orders_id", "paper_orders", ["id"], unique=False)
        op.create_index("ix_paper_orders_order_type", "paper_orders", ["order_type"], unique=False)
        op.create_index("ix_paper_orders_status", "paper_orders", ["status"], unique=False)
        op.create_index("ix_paper_orders_strategy_mode", "paper_orders", ["strategy_mode"], unique=False)
        op.create_index("ix_paper_orders_symbol", "paper_orders", ["symbol"], unique=False)

    if "training_jobs" not in existing_tables:
        op.create_table(
            "training_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("job_id", sa.String(length=80), nullable=False),
            sa.Column("model_type", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("requested_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("requested_by", sa.String(length=80), nullable=True),
            sa.Column("pid", sa.Integer(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
        )
        op.create_index("ix_training_jobs_id", "training_jobs", ["id"], unique=False)
        op.create_index("ix_training_jobs_job_id", "training_jobs", ["job_id"], unique=True)
        op.create_index("ix_training_jobs_model_type", "training_jobs", ["model_type"], unique=False)
        op.create_index("ix_training_jobs_requested_at", "training_jobs", ["requested_at"], unique=False)
        op.create_index("ix_training_jobs_status", "training_jobs", ["status"], unique=False)


def downgrade() -> None:
    existing_tables = {"training_jobs", "paper_orders"} if context.is_offline_mode() else set(inspect(op.get_bind()).get_table_names())

    if "training_jobs" in existing_tables:
        op.drop_index("ix_training_jobs_status", table_name="training_jobs")
        op.drop_index("ix_training_jobs_requested_at", table_name="training_jobs")
        op.drop_index("ix_training_jobs_model_type", table_name="training_jobs")
        op.drop_index("ix_training_jobs_job_id", table_name="training_jobs")
        op.drop_index("ix_training_jobs_id", table_name="training_jobs")
        op.drop_table("training_jobs")

    if "paper_orders" in existing_tables:
        op.drop_index("ix_paper_orders_symbol", table_name="paper_orders")
        op.drop_index("ix_paper_orders_strategy_mode", table_name="paper_orders")
        op.drop_index("ix_paper_orders_status", table_name="paper_orders")
        op.drop_index("ix_paper_orders_order_type", table_name="paper_orders")
        op.drop_index("ix_paper_orders_id", table_name="paper_orders")
        op.drop_index("ix_paper_orders_client_order_id", table_name="paper_orders")
        op.drop_table("paper_orders")
