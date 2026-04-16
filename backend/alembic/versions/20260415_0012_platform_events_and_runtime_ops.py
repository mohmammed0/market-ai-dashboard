"""platform events and runtime ops tables

Revision ID: 20260415_0012
Revises: 20260415_0011
Create Date: 2026-04-15 20:15:00.000000
"""

from __future__ import annotations

from alembic import context, op
from sqlalchemy import inspect

from backend.app.models.platform_events import (
    DeadLetterEvent,
    EventReplayJob,
    OrderEvent,
    OrderIntent,
    PortfolioSnapshotRecord,
    ProviderHealth,
    RiskDecision,
    SchedulerLease,
    WorkflowRun,
)


revision = "20260415_0012"
down_revision = "20260415_0011"
branch_labels = None
depends_on = None

TABLES = [
    OrderIntent.__table__,
    RiskDecision.__table__,
    OrderEvent.__table__,
    PortfolioSnapshotRecord.__table__,
    WorkflowRun.__table__,
    ProviderHealth.__table__,
    SchedulerLease.__table__,
    EventReplayJob.__table__,
    DeadLetterEvent.__table__,
]


def _existing_tables() -> set[str]:
    if context.is_offline_mode():
        return set()
    inspector = inspect(op.get_bind())
    return set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = _existing_tables()
    for table in TABLES:
        if table.name not in existing_tables:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    existing_tables = _existing_tables()
    for table in reversed(TABLES):
        if table.name in existing_tables:
            table.drop(bind=bind, checkfirst=True)
