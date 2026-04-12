"""background jobs

Revision ID: 20260410_0007
Revises: 20260408_0005
Create Date: 2026-04-10 00:00:00.000000
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260410_0007"
down_revision = "20260408_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = None if context.is_offline_mode() else sa.inspect(op.get_bind())

    if inspector is None or not inspector.has_table("background_jobs"):
        op.create_table(
            "background_jobs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("job_id", sa.String(length=80), nullable=False),
            sa.Column("job_type", sa.String(length=60), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("requested_by", sa.String(length=80), nullable=True),
            sa.Column("payload_hash", sa.String(length=128), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("result_summary_json", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("pid", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("job_id"),
        )
        if not context.is_offline_mode():
            inspector = sa.inspect(op.get_bind())

    existing_indexes = set() if inspector is None else {index["name"] for index in inspector.get_indexes("background_jobs")}
    if op.f("ix_background_jobs_id") not in existing_indexes:
        op.create_index(op.f("ix_background_jobs_id"), "background_jobs", ["id"], unique=False)
    if op.f("ix_background_jobs_job_id") not in existing_indexes:
        op.create_index(op.f("ix_background_jobs_job_id"), "background_jobs", ["job_id"], unique=False)
    if op.f("ix_background_jobs_job_type") not in existing_indexes:
        op.create_index(op.f("ix_background_jobs_job_type"), "background_jobs", ["job_type"], unique=False)
    if op.f("ix_background_jobs_status") not in existing_indexes:
        op.create_index(op.f("ix_background_jobs_status"), "background_jobs", ["status"], unique=False)
    if op.f("ix_background_jobs_payload_hash") not in existing_indexes:
        op.create_index(op.f("ix_background_jobs_payload_hash"), "background_jobs", ["payload_hash"], unique=False)
    if op.f("ix_background_jobs_created_at") not in existing_indexes:
        op.create_index(op.f("ix_background_jobs_created_at"), "background_jobs", ["created_at"], unique=False)
    if op.f("ix_background_jobs_updated_at") not in existing_indexes:
        op.create_index(op.f("ix_background_jobs_updated_at"), "background_jobs", ["updated_at"], unique=False)


def downgrade() -> None:
    inspector = None if context.is_offline_mode() else sa.inspect(op.get_bind())
    if inspector is not None and not inspector.has_table("background_jobs"):
        return

    existing_indexes = {
        op.f("ix_background_jobs_updated_at"),
        op.f("ix_background_jobs_created_at"),
        op.f("ix_background_jobs_payload_hash"),
        op.f("ix_background_jobs_status"),
        op.f("ix_background_jobs_job_type"),
        op.f("ix_background_jobs_job_id"),
        op.f("ix_background_jobs_id"),
    } if inspector is None else {index["name"] for index in inspector.get_indexes("background_jobs")}
    if op.f("ix_background_jobs_updated_at") in existing_indexes:
        op.drop_index(op.f("ix_background_jobs_updated_at"), table_name="background_jobs")
    if op.f("ix_background_jobs_created_at") in existing_indexes:
        op.drop_index(op.f("ix_background_jobs_created_at"), table_name="background_jobs")
    if op.f("ix_background_jobs_payload_hash") in existing_indexes:
        op.drop_index(op.f("ix_background_jobs_payload_hash"), table_name="background_jobs")
    if op.f("ix_background_jobs_status") in existing_indexes:
        op.drop_index(op.f("ix_background_jobs_status"), table_name="background_jobs")
    if op.f("ix_background_jobs_job_type") in existing_indexes:
        op.drop_index(op.f("ix_background_jobs_job_type"), table_name="background_jobs")
    if op.f("ix_background_jobs_job_id") in existing_indexes:
        op.drop_index(op.f("ix_background_jobs_job_id"), table_name="background_jobs")
    if op.f("ix_background_jobs_id") in existing_indexes:
        op.drop_index(op.f("ix_background_jobs_id"), table_name="background_jobs")
    op.drop_table("background_jobs")
