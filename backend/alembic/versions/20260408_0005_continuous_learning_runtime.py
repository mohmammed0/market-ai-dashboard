"""continuous learning runtime tables

Revision ID: 20260408_0005
Revises: 20260408_0004
Create Date: 2026-04-08 10:20:00.000000
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260408_0005"
down_revision = "20260408_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_tables = set() if context.is_offline_mode() else set(inspect(op.get_bind()).get_table_names())

    if "continuous_learning_states" not in existing_tables:
        op.create_table(
            "continuous_learning_states",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("engine_key", sa.String(length=80), nullable=False),
            sa.Column("desired_state", sa.String(length=20), nullable=False, server_default="running"),
            sa.Column("runtime_status", sa.String(length=20), nullable=False, server_default="idle"),
            sa.Column("active_stage", sa.String(length=60), nullable=True),
            sa.Column("worker_id", sa.String(length=120), nullable=True),
            sa.Column("active_pid", sa.Integer(), nullable=True),
            sa.Column("current_run_id", sa.String(length=80), nullable=True),
            sa.Column("last_started_at", sa.DateTime(), nullable=True),
            sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
            sa.Column("last_success_at", sa.DateTime(), nullable=True),
            sa.Column("last_cycle_started_at", sa.DateTime(), nullable=True),
            sa.Column("last_cycle_completed_at", sa.DateTime(), nullable=True),
            sa.Column("next_cycle_at", sa.DateTime(), nullable=True),
            sa.Column("current_model_version", sa.String(length=160), nullable=True),
            sa.Column("best_strategy_name", sa.String(length=160), nullable=True),
            sa.Column("best_strategy_run_id", sa.String(length=80), nullable=True),
            sa.Column("latest_metrics_json", sa.Text(), nullable=True),
            sa.Column("latest_artifact_path", sa.Text(), nullable=True),
            sa.Column("last_failure_reason", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_continuous_learning_states_id", "continuous_learning_states", ["id"], unique=False)
        op.create_index("ix_continuous_learning_states_engine_key", "continuous_learning_states", ["engine_key"], unique=True)
        op.create_index("ix_continuous_learning_states_desired_state", "continuous_learning_states", ["desired_state"], unique=False)
        op.create_index("ix_continuous_learning_states_runtime_status", "continuous_learning_states", ["runtime_status"], unique=False)
        op.create_index("ix_continuous_learning_states_active_stage", "continuous_learning_states", ["active_stage"], unique=False)
        op.create_index("ix_continuous_learning_states_worker_id", "continuous_learning_states", ["worker_id"], unique=False)
        op.create_index("ix_continuous_learning_states_active_pid", "continuous_learning_states", ["active_pid"], unique=False)
        op.create_index("ix_continuous_learning_states_current_run_id", "continuous_learning_states", ["current_run_id"], unique=False)
        op.create_index("ix_continuous_learning_states_last_started_at", "continuous_learning_states", ["last_started_at"], unique=False)
        op.create_index("ix_continuous_learning_states_last_heartbeat_at", "continuous_learning_states", ["last_heartbeat_at"], unique=False)
        op.create_index("ix_continuous_learning_states_last_success_at", "continuous_learning_states", ["last_success_at"], unique=False)
        op.create_index("ix_continuous_learning_states_last_cycle_started_at", "continuous_learning_states", ["last_cycle_started_at"], unique=False)
        op.create_index("ix_continuous_learning_states_last_cycle_completed_at", "continuous_learning_states", ["last_cycle_completed_at"], unique=False)
        op.create_index("ix_continuous_learning_states_next_cycle_at", "continuous_learning_states", ["next_cycle_at"], unique=False)
        op.create_index("ix_continuous_learning_states_best_strategy_run_id", "continuous_learning_states", ["best_strategy_run_id"], unique=False)
        op.create_index("ix_continuous_learning_states_updated_at", "continuous_learning_states", ["updated_at"], unique=False)

    if "continuous_learning_runs" not in existing_tables:
        op.create_table(
            "continuous_learning_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="running"),
            sa.Column("stage", sa.String(length=60), nullable=True),
            sa.Column("cycle_type", sa.String(length=30), nullable=False, server_default="full"),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("duration_seconds", sa.Float(), nullable=True),
            sa.Column("summary_json", sa.Text(), nullable=True),
            sa.Column("metrics_json", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
        )
        op.create_index("ix_continuous_learning_runs_id", "continuous_learning_runs", ["id"], unique=False)
        op.create_index("ix_continuous_learning_runs_run_id", "continuous_learning_runs", ["run_id"], unique=True)
        op.create_index("ix_continuous_learning_runs_status", "continuous_learning_runs", ["status"], unique=False)
        op.create_index("ix_continuous_learning_runs_stage", "continuous_learning_runs", ["stage"], unique=False)
        op.create_index("ix_continuous_learning_runs_cycle_type", "continuous_learning_runs", ["cycle_type"], unique=False)
        op.create_index("ix_continuous_learning_runs_started_at", "continuous_learning_runs", ["started_at"], unique=False)
        op.create_index("ix_continuous_learning_runs_completed_at", "continuous_learning_runs", ["completed_at"], unique=False)

    if "continuous_learning_artifacts" not in existing_tables:
        op.create_table(
            "continuous_learning_artifacts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.String(length=80), nullable=False),
            sa.Column("artifact_type", sa.String(length=80), nullable=False),
            sa.Column("artifact_key", sa.String(length=120), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("file_path", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_continuous_learning_artifacts_id", "continuous_learning_artifacts", ["id"], unique=False)
        op.create_index("ix_continuous_learning_artifacts_run_id", "continuous_learning_artifacts", ["run_id"], unique=False)
        op.create_index("ix_continuous_learning_artifacts_artifact_type", "continuous_learning_artifacts", ["artifact_type"], unique=False)
        op.create_index("ix_continuous_learning_artifacts_artifact_key", "continuous_learning_artifacts", ["artifact_key"], unique=False)
        op.create_index("ix_continuous_learning_artifacts_created_at", "continuous_learning_artifacts", ["created_at"], unique=False)


def downgrade() -> None:
    existing_tables = (
        {"continuous_learning_states", "continuous_learning_runs", "continuous_learning_artifacts"}
        if context.is_offline_mode()
        else set(inspect(op.get_bind()).get_table_names())
    )

    if "continuous_learning_artifacts" in existing_tables:
        op.drop_index("ix_continuous_learning_artifacts_created_at", table_name="continuous_learning_artifacts")
        op.drop_index("ix_continuous_learning_artifacts_artifact_key", table_name="continuous_learning_artifacts")
        op.drop_index("ix_continuous_learning_artifacts_artifact_type", table_name="continuous_learning_artifacts")
        op.drop_index("ix_continuous_learning_artifacts_run_id", table_name="continuous_learning_artifacts")
        op.drop_index("ix_continuous_learning_artifacts_id", table_name="continuous_learning_artifacts")
        op.drop_table("continuous_learning_artifacts")

    if "continuous_learning_runs" in existing_tables:
        op.drop_index("ix_continuous_learning_runs_completed_at", table_name="continuous_learning_runs")
        op.drop_index("ix_continuous_learning_runs_started_at", table_name="continuous_learning_runs")
        op.drop_index("ix_continuous_learning_runs_cycle_type", table_name="continuous_learning_runs")
        op.drop_index("ix_continuous_learning_runs_stage", table_name="continuous_learning_runs")
        op.drop_index("ix_continuous_learning_runs_status", table_name="continuous_learning_runs")
        op.drop_index("ix_continuous_learning_runs_run_id", table_name="continuous_learning_runs")
        op.drop_index("ix_continuous_learning_runs_id", table_name="continuous_learning_runs")
        op.drop_table("continuous_learning_runs")

    if "continuous_learning_states" in existing_tables:
        op.drop_index("ix_continuous_learning_states_updated_at", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_best_strategy_run_id", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_next_cycle_at", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_last_cycle_completed_at", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_last_cycle_started_at", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_last_success_at", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_last_heartbeat_at", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_last_started_at", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_current_run_id", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_active_pid", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_worker_id", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_active_stage", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_runtime_status", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_desired_state", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_engine_key", table_name="continuous_learning_states")
        op.drop_index("ix_continuous_learning_states_id", table_name="continuous_learning_states")
        op.drop_table("continuous_learning_states")
