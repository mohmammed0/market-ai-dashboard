"""database hardening indexes

Revision ID: 20260415_0011
Revises: 20260414_0010
Create Date: 2026-04-15 18:30:00.000000
"""

from __future__ import annotations

from alembic import context, op
from sqlalchemy import inspect


revision = "20260415_0011"
down_revision = "20260414_0010"
branch_labels = None
depends_on = None


INDEXES: dict[str, list[tuple[str, list[str]]]] = {
    "paper_positions": [
        ("ix_paper_positions_symbol_strategy_status", ["symbol", "strategy_mode", "status"]),
        ("ix_paper_positions_status_updated_at", ["status", "updated_at"]),
    ],
    "paper_trades": [
        ("ix_paper_trades_symbol_strategy_created_at", ["symbol", "strategy_mode", "created_at"]),
    ],
    "signal_history": [
        ("ix_signal_history_symbol_strategy_created_at", ["symbol", "strategy_mode", "created_at"]),
    ],
    "paper_orders": [
        ("ix_paper_orders_symbol_status_updated_at", ["symbol", "status", "updated_at"]),
        ("ix_paper_orders_status_updated_at", ["status", "updated_at"]),
    ],
    "execution_audit_events": [
        ("ix_execution_audit_events_event_type_created_at", ["event_type", "created_at"]),
        ("ix_execution_audit_events_symbol_created_at", ["symbol", "created_at"]),
        ("ix_execution_audit_events_event_type_correlation_id", ["event_type", "correlation_id"]),
    ],
    "background_jobs": [
        ("ix_background_jobs_status_created_at", ["status", "created_at"]),
        ("ix_background_jobs_job_type_status_created_at", ["job_type", "status", "created_at"]),
        ("ix_background_jobs_job_type_payload_hash_status", ["job_type", "payload_hash", "status"]),
    ],
    "model_runs": [
        ("ix_model_runs_model_type_started_at", ["model_type", "started_at"]),
        ("ix_model_runs_model_type_is_active", ["model_type", "is_active"]),
    ],
    "model_predictions": [
        ("ix_model_predictions_symbol_model_type_predicted_at", ["symbol", "model_type", "predicted_at"]),
    ],
    "strategy_evaluation_runs": [
        ("ix_strategy_evaluation_runs_instrument_started_at", ["instrument", "started_at"]),
        ("ix_strategy_evaluation_runs_status_started_at", ["status", "started_at"]),
    ],
    "training_jobs": [
        ("ix_training_jobs_status_requested_at", ["status", "requested_at"]),
        ("ix_training_jobs_model_type_status_requested_at", ["model_type", "status", "requested_at"]),
        ("ix_training_jobs_worker_status_heartbeat_at", ["worker_id", "status", "heartbeat_at"]),
    ],
    "scheduler_runs": [
        ("ix_scheduler_runs_job_name_ran_at", ["job_name", "ran_at"]),
        ("ix_scheduler_runs_status_ran_at", ["status", "ran_at"]),
    ],
    "automation_runs": [
        ("ix_automation_runs_job_name_started_at", ["job_name", "started_at"]),
        ("ix_automation_runs_status_started_at", ["status", "started_at"]),
    ],
    "automation_artifacts": [
        ("ix_automation_artifacts_run_id_created_at", ["run_id", "created_at"]),
        ("ix_automation_artifacts_job_name_created_at", ["job_name", "created_at"]),
    ],
    "continuous_learning_states": [
        ("ix_cont_learning_state_runtime_status_updated_at", ["runtime_status", "updated_at"]),
        ("ix_cont_learning_state_desired_state_updated_at", ["desired_state", "updated_at"]),
    ],
    "continuous_learning_runs": [
        ("ix_cont_learning_runs_status_started_at", ["status", "started_at"]),
        ("ix_cont_learning_runs_cycle_type_started_at", ["cycle_type", "started_at"]),
    ],
    "continuous_learning_artifacts": [
        ("ix_cont_learning_artifacts_run_id_created_at", ["run_id", "created_at"]),
    ],
    "market_universe_symbols": [
        ("ix_market_universe_symbols_active_exchange_symbol", ["active", "exchange", "symbol"]),
        ("ix_market_universe_symbols_active_is_etf_symbol", ["active", "is_etf", "symbol"]),
    ],
    "feature_snapshots": [
        ("ix_feature_snapshots_symbol_feature_set_as_of", ["symbol", "feature_set", "as_of"]),
    ],
    "watchlist_items": [
        ("ix_watchlist_items_watchlist_display_order_symbol", ["watchlist_id", "display_order", "symbol"]),
    ],
}


def _existing_schema() -> tuple[set[str], dict[str, set[str]]]:
    if context.is_offline_mode():
        return set(INDEXES.keys()), {table_name: set() for table_name in INDEXES}
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    indexes = {
        table_name: {item["name"] for item in inspector.get_indexes(table_name)}
        for table_name in INDEXES
        if table_name in tables
    }
    return tables, indexes


def upgrade() -> None:
    tables, indexes = _existing_schema()
    for table_name, entries in INDEXES.items():
        if table_name not in tables:
            continue
        existing_indexes = indexes.get(table_name, set())
        for index_name, columns in entries:
            if index_name not in existing_indexes:
                op.create_index(index_name, table_name, columns, unique=False)


def downgrade() -> None:
    tables, indexes = _existing_schema()
    for table_name, entries in reversed(list(INDEXES.items())):
        if table_name not in tables:
            continue
        existing_indexes = indexes.get(table_name, set())
        for index_name, _columns in reversed(entries):
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=table_name)
