"""training_jobs: add worker_id, worker_hostname, heartbeat_at for remote GPU worker

Revision ID: 20260414_0010
Revises: 20260412_0008
Create Date: 2026-04-14 00:00:00.000000
"""

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260414_0010"
down_revision = "20260412_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = None if context.is_offline_mode() else inspect(op.get_bind())
    if inspector is not None and not inspector.has_table("training_jobs"):
        return

    existing_columns = set() if inspector is None else {
        column["name"] for column in inspector.get_columns("training_jobs")
    }
    existing_indexes = set() if inspector is None else {
        index["name"] for index in inspector.get_indexes("training_jobs")
    }

    with op.batch_alter_table("training_jobs") as batch_op:
        if "worker_id" not in existing_columns:
            batch_op.add_column(sa.Column("worker_id", sa.String(120), nullable=True))
        if "worker_hostname" not in existing_columns:
            batch_op.add_column(sa.Column("worker_hostname", sa.String(255), nullable=True))
        if "heartbeat_at" not in existing_columns:
            batch_op.add_column(sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
        if "ix_training_jobs_worker_id" not in existing_indexes:
            batch_op.create_index("ix_training_jobs_worker_id", ["worker_id"])


def downgrade() -> None:
    inspector = None if context.is_offline_mode() else inspect(op.get_bind())
    if inspector is not None and not inspector.has_table("training_jobs"):
        return

    existing_columns = set() if inspector is None else {
        column["name"] for column in inspector.get_columns("training_jobs")
    }
    existing_indexes = set() if inspector is None else {
        index["name"] for index in inspector.get_indexes("training_jobs")
    }

    with op.batch_alter_table("training_jobs") as batch_op:
        if "ix_training_jobs_worker_id" in existing_indexes:
            batch_op.drop_index("ix_training_jobs_worker_id")
        if "heartbeat_at" in existing_columns:
            batch_op.drop_column("heartbeat_at")
        if "worker_hostname" in existing_columns:
            batch_op.drop_column("worker_hostname")
        if "worker_id" in existing_columns:
            batch_op.drop_column("worker_id")
