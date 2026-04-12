from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class BrokerAccountSnapshot(Base):
    __tablename__ = "broker_account_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="paper")
    account_id: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[str | None] = mapped_column(String(40), index=True)
    cash: Mapped[float | None] = mapped_column(Float)
    equity: Mapped[float | None] = mapped_column(Float)
    buying_power: Mapped[float | None] = mapped_column(Float)
    portfolio_value: Mapped[float | None] = mapped_column(Float)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    payload_json: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class BrokerPositionSnapshot(Base):
    __tablename__ = "broker_position_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="paper")
    account_id: Mapped[str | None] = mapped_column(String(120), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    side: Mapped[str | None] = mapped_column(String(32))
    qty: Mapped[float | None] = mapped_column(Float)
    market_value: Mapped[float | None] = mapped_column(Float)
    unrealized_pnl: Mapped[float | None] = mapped_column(Float)
    payload_json: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
