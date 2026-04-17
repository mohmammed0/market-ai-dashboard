"""knowledge documents table

Revision ID: 20260417_0014
Revises: 20260415_0013
Create Date: 2026-04-17 10:40:00.000000
"""

from __future__ import annotations

from alembic import context, op
from sqlalchemy import inspect

from backend.app.models.knowledge import KnowledgeDocument


revision = "20260417_0014"
down_revision = "20260415_0013"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    if context.is_offline_mode():
        return set()
    inspector = inspect(op.get_bind())
    return set(inspector.get_table_names())


def _existing_indexes(table_name: str) -> set[str]:
    if context.is_offline_mode():
        return set()
    inspector = inspect(op.get_bind())
    return {str(item.get("name")) for item in inspector.get_indexes(table_name) if item.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = _existing_tables()
    table_name = KnowledgeDocument.__table__.name
    if table_name not in existing_tables:
        KnowledgeDocument.__table__.create(bind=bind, checkfirst=True)
        return

    existing_indexes = _existing_indexes(table_name)
    if "ix_knowledge_documents_symbol_source_created_at" not in existing_indexes:
        op.create_index(
            "ix_knowledge_documents_symbol_source_created_at",
            table_name,
            ["symbol", "source_type", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing_tables = _existing_tables()
    table_name = KnowledgeDocument.__table__.name
    if table_name not in existing_tables:
        return

    existing_indexes = _existing_indexes(table_name)
    if "ix_knowledge_documents_symbol_source_created_at" in existing_indexes:
        op.drop_index("ix_knowledge_documents_symbol_source_created_at", table_name=table_name)
    KnowledgeDocument.__table__.drop(bind=bind, checkfirst=True)
