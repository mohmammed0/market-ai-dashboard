"""domain baseline

Revision ID: 20260407_0001
Revises:
Create Date: 2026-04-07 12:00:00.000000
"""

from __future__ import annotations

from alembic import op

from backend.app.db.base import Base
from backend.app import models  # noqa: F401


revision = "20260407_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
