"""market universe top-500 fields and currency references

Revision ID: 20260415_0013
Revises: 20260415_0012
Create Date: 2026-04-15 21:05:00.000000
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect

from backend.app.models.market_data import CurrencyReference


revision = "20260415_0013"
down_revision = "20260415_0012"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    if context.is_offline_mode():
        return set()
    inspector = inspect(op.get_bind())
    return set(inspector.get_table_names())


def _existing_columns(table_name: str) -> set[str]:
    if context.is_offline_mode():
        return set()
    inspector = inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_indexes(table_name: str) -> set[str]:
    if context.is_offline_mode():
        return set()
    inspector = inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = _existing_tables()
    if CurrencyReference.__table__.name not in existing_tables:
        CurrencyReference.__table__.create(bind=bind, checkfirst=True)

    table_name = "market_universe_symbols"
    existing_columns = _existing_columns(table_name)
    if "country" not in existing_columns:
        op.add_column(table_name, sa.Column("country", sa.String(length=80), nullable=True))
    if "market_cap" not in existing_columns:
        op.add_column(table_name, sa.Column("market_cap", sa.Float(), nullable=True))
    if "market_cap_rank" not in existing_columns:
        op.add_column(table_name, sa.Column("market_cap_rank", sa.Integer(), nullable=True))
    if "market_cap_currency" not in existing_columns:
        op.add_column(table_name, sa.Column("market_cap_currency", sa.String(length=16), nullable=True))
    if "market_cap_source" not in existing_columns:
        op.add_column(table_name, sa.Column("market_cap_source", sa.String(length=80), nullable=True))
    if "market_cap_updated_at" not in existing_columns:
        op.add_column(table_name, sa.Column("market_cap_updated_at", sa.DateTime(), nullable=True))

    existing_indexes = _existing_indexes(table_name)
    if "ix_market_universe_symbols_market_cap_rank_symbol" not in existing_indexes:
        op.create_index(
            "ix_market_universe_symbols_market_cap_rank_symbol",
            table_name,
            ["market_cap_rank", "symbol"],
            unique=False,
        )


def downgrade() -> None:
    table_name = "market_universe_symbols"
    existing_indexes = _existing_indexes(table_name)
    if "ix_market_universe_symbols_market_cap_rank_symbol" in existing_indexes:
        op.drop_index("ix_market_universe_symbols_market_cap_rank_symbol", table_name=table_name)

    existing_columns = _existing_columns(table_name)
    for column_name in [
        "market_cap_updated_at",
        "market_cap_source",
        "market_cap_currency",
        "market_cap_rank",
        "market_cap",
        "country",
    ]:
        if column_name in existing_columns:
            op.drop_column(table_name, column_name)

    existing_tables = _existing_tables()
    if CurrencyReference.__table__.name in existing_tables:
        CurrencyReference.__table__.drop(bind=op.get_bind(), checkfirst=True)
