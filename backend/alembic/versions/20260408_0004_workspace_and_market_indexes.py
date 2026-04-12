"""workspace state and market indexes

Revision ID: 20260408_0004
Revises: 20260407_0003
Create Date: 2026-04-08 02:10:00.000000
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260408_0004"
down_revision = "20260407_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = None if context.is_offline_mode() else inspect(op.get_bind())
    existing_tables = set() if inspector is None else set(inspector.get_table_names())

    if "watchlists" not in existing_tables:
        op.create_table(
            "watchlists",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("category", sa.String(length=40), nullable=False, server_default="custom"),
            sa.Column("color_token", sa.String(length=24), nullable=True),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_watchlists_id", "watchlists", ["id"], unique=False)
        op.create_index("ix_watchlists_name", "watchlists", ["name"], unique=False)
        op.create_index("ix_watchlists_category", "watchlists", ["category"], unique=False)
        op.create_index("ix_watchlists_is_system", "watchlists", ["is_system"], unique=False)
        op.create_index("ix_watchlists_is_default", "watchlists", ["is_default"], unique=False)
        op.create_index("ix_watchlists_updated_at", "watchlists", ["updated_at"], unique=False)

    if "watchlist_items" not in existing_tables:
        op.create_table(
            "watchlist_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("watchlist_id", sa.Integer(), nullable=False),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["watchlist_id"], ["watchlists.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_items_watchlist_symbol"),
        )
        op.create_index("ix_watchlist_items_id", "watchlist_items", ["id"], unique=False)
        op.create_index("ix_watchlist_items_watchlist_id", "watchlist_items", ["watchlist_id"], unique=False)
        op.create_index("ix_watchlist_items_symbol", "watchlist_items", ["symbol"], unique=False)
        op.create_index("ix_watchlist_items_display_order", "watchlist_items", ["display_order"], unique=False)
        op.create_index("ix_watchlist_items_created_at", "watchlist_items", ["created_at"], unique=False)

    if "workspace_states" not in existing_tables:
        op.create_table(
            "workspace_states",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workspace_key", sa.String(length=64), nullable=False),
            sa.Column("active_symbol", sa.String(length=20), nullable=True),
            sa.Column("active_watchlist_id", sa.Integer(), nullable=True),
            sa.Column("timeframe", sa.String(length=16), nullable=False, server_default="1D"),
            sa.Column("range_key", sa.String(length=16), nullable=False, server_default="3M"),
            sa.Column("layout_mode", sa.String(length=24), nullable=False, server_default="terminal"),
            sa.Column("compare_symbols_json", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_workspace_states_id", "workspace_states", ["id"], unique=False)
        op.create_index("ix_workspace_states_workspace_key", "workspace_states", ["workspace_key"], unique=True)
        op.create_index("ix_workspace_states_active_symbol", "workspace_states", ["active_symbol"], unique=False)
        op.create_index("ix_workspace_states_active_watchlist_id", "workspace_states", ["active_watchlist_id"], unique=False)
        op.create_index("ix_workspace_states_timeframe", "workspace_states", ["timeframe"], unique=False)
        op.create_index("ix_workspace_states_range_key", "workspace_states", ["range_key"], unique=False)
        op.create_index("ix_workspace_states_updated_at", "workspace_states", ["updated_at"], unique=False)

    existing_indexes = (
        set()
        if inspector is None or "quote_snapshots" not in existing_tables
        else {index["name"] for index in inspector.get_indexes("quote_snapshots")}
    )
    if "ix_quote_snapshots_symbol_captured_at" not in existing_indexes and "quote_snapshots" in existing_tables:
        op.create_index("ix_quote_snapshots_symbol_captured_at", "quote_snapshots", ["symbol", "captured_at"], unique=False)

    existing_indexes = (
        set()
        if inspector is None or "ohlcv_bars" not in existing_tables
        else {index["name"] for index in inspector.get_indexes("ohlcv_bars")}
    )
    if "ix_ohlcv_bars_symbol_timeframe_bar_time" not in existing_indexes and "ohlcv_bars" in existing_tables:
        op.create_index("ix_ohlcv_bars_symbol_timeframe_bar_time", "ohlcv_bars", ["symbol", "timeframe", "bar_time"], unique=False)


def downgrade() -> None:
    inspector = None if context.is_offline_mode() else inspect(op.get_bind())
    existing_tables = {"watchlists", "watchlist_items", "workspace_states", "quote_snapshots", "ohlcv_bars"} if inspector is None else set(inspector.get_table_names())

    if "quote_snapshots" in existing_tables:
        existing_indexes = (
            {"ix_quote_snapshots_symbol_captured_at"}
            if inspector is None
            else {index["name"] for index in inspector.get_indexes("quote_snapshots")}
        )
        if "ix_quote_snapshots_symbol_captured_at" in existing_indexes:
            op.drop_index("ix_quote_snapshots_symbol_captured_at", table_name="quote_snapshots")

    if "ohlcv_bars" in existing_tables:
        existing_indexes = (
            {"ix_ohlcv_bars_symbol_timeframe_bar_time"}
            if inspector is None
            else {index["name"] for index in inspector.get_indexes("ohlcv_bars")}
        )
        if "ix_ohlcv_bars_symbol_timeframe_bar_time" in existing_indexes:
            op.drop_index("ix_ohlcv_bars_symbol_timeframe_bar_time", table_name="ohlcv_bars")

    if "workspace_states" in existing_tables:
        op.drop_index("ix_workspace_states_updated_at", table_name="workspace_states")
        op.drop_index("ix_workspace_states_range_key", table_name="workspace_states")
        op.drop_index("ix_workspace_states_timeframe", table_name="workspace_states")
        op.drop_index("ix_workspace_states_active_watchlist_id", table_name="workspace_states")
        op.drop_index("ix_workspace_states_active_symbol", table_name="workspace_states")
        op.drop_index("ix_workspace_states_workspace_key", table_name="workspace_states")
        op.drop_index("ix_workspace_states_id", table_name="workspace_states")
        op.drop_table("workspace_states")

    if "watchlist_items" in existing_tables:
        op.drop_index("ix_watchlist_items_created_at", table_name="watchlist_items")
        op.drop_index("ix_watchlist_items_display_order", table_name="watchlist_items")
        op.drop_index("ix_watchlist_items_symbol", table_name="watchlist_items")
        op.drop_index("ix_watchlist_items_watchlist_id", table_name="watchlist_items")
        op.drop_index("ix_watchlist_items_id", table_name="watchlist_items")
        op.drop_table("watchlist_items")

    if "watchlists" in existing_tables:
        op.drop_index("ix_watchlists_updated_at", table_name="watchlists")
        op.drop_index("ix_watchlists_is_default", table_name="watchlists")
        op.drop_index("ix_watchlists_is_system", table_name="watchlists")
        op.drop_index("ix_watchlists_category", table_name="watchlists")
        op.drop_index("ix_watchlists_name", table_name="watchlists")
        op.drop_index("ix_watchlists_id", table_name="watchlists")
        op.drop_table("watchlists")
