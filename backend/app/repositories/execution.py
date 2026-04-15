from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.domain.alerts.contracts import AlertRecord
from backend.app.domain.execution.contracts import ExecutionEventRecord, PaperOrderRecord, PositionState, SignalRecord, TradeRecord
from backend.app.models.alerts import AlertHistory
from backend.app.models.execution import ExecutionAuditEvent, PaperOrder, PaperPosition, PaperTrade, SignalHistory
from backend.app.services.storage import dumps_json, loads_json


def _serialize_position(row: PaperPosition) -> PositionState:
    return PositionState(
        id=row.id,
        symbol=row.symbol,
        strategy_mode=row.strategy_mode,
        side=row.side,
        quantity=float(row.quantity or 0.0),
        avg_entry_price=float(row.avg_entry_price or 0.0),
        current_price=float(row.current_price or 0.0) if row.current_price is not None else None,
        market_value=float(row.market_value or 0.0) if row.market_value is not None else 0.0,
        unrealized_pnl=float(row.unrealized_pnl or 0.0) if row.unrealized_pnl is not None else 0.0,
        realized_pnl=float(row.realized_pnl or 0.0) if row.realized_pnl is not None else 0.0,
        status=row.status,
        opened_at=row.opened_at,
        updated_at=row.updated_at,
    )


def _serialize_trade(row: PaperTrade) -> TradeRecord:
    return TradeRecord(
        id=row.id,
        symbol=row.symbol,
        strategy_mode=row.strategy_mode,
        action=row.action,
        side=row.side,
        quantity=float(row.quantity or 0.0),
        price=float(row.price or 0.0),
        realized_pnl=float(row.realized_pnl or 0.0) if row.realized_pnl is not None else None,
        notes=row.notes,
        created_at=row.created_at,
    )


def _serialize_signal(row: SignalHistory) -> SignalRecord:
    return SignalRecord(
        id=row.id,
        symbol=row.symbol,
        strategy_mode=row.strategy_mode,
        signal=row.signal,
        confidence=float(row.confidence or 0.0) if row.confidence is not None else 0.0,
        price=float(row.price or 0.0) if row.price is not None else None,
        reasoning=row.reasoning,
        payload=loads_json(row.payload_json),
        created_at=row.created_at,
    )


def _serialize_alert(row: AlertHistory) -> AlertRecord:
    return AlertRecord(
        id=row.id,
        symbol=row.symbol,
        strategy_mode=row.strategy_mode,
        alert_type=row.alert_type,
        severity=row.severity,
        message=row.message,
        payload=loads_json(row.payload_json),
        created_at=row.created_at,
    )


def _serialize_audit_event(row: ExecutionAuditEvent) -> ExecutionEventRecord:
    return ExecutionEventRecord(
        event_type=row.event_type,
        source=row.source,
        portfolio_source=row.portfolio_source or "internal_paper",
        symbol=row.symbol,
        strategy_mode=row.strategy_mode,
        correlation_id=row.correlation_id,
        payload=loads_json(row.payload_json),
    )


def _serialize_order(row: PaperOrder) -> PaperOrderRecord:
    return PaperOrderRecord(
        id=row.id,
        client_order_id=row.client_order_id,
        symbol=row.symbol,
        strategy_mode=row.strategy_mode,
        side=row.side,
        order_type=row.order_type,
        quantity=float(row.quantity or 0.0),
        limit_price=float(row.limit_price or 0.0) if row.limit_price is not None else None,
        status=row.status,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ExecutionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_open_positions(self) -> list[PositionState]:
        rows = (
            self.session.query(PaperPosition)
            .filter(PaperPosition.status == "OPEN")
            .order_by(PaperPosition.updated_at.desc())
            .all()
        )
        return [_serialize_position(row) for row in rows]

    def get_open_position_row(self, symbol: str, strategy_mode: str) -> PaperPosition | None:
        return (
            self.session.query(PaperPosition)
            .filter(
                PaperPosition.symbol == str(symbol).strip().upper(),
                PaperPosition.strategy_mode == strategy_mode,
                PaperPosition.status == "OPEN",
            )
            .first()
        )

    def upsert_position(
        self,
        *,
        symbol: str,
        strategy_mode: str,
        side: str,
        quantity: float,
        avg_entry_price: float,
        current_price: float,
        market_value: float,
        unrealized_pnl: float,
        realized_pnl: float,
        status: str = "OPEN",
        opened_at: datetime | None = None,
        stop_loss_price: float | None = None,
        trailing_stop_pct: float | None = None,
        trailing_stop_price: float | None = None,
        high_water_mark: float | None = None,
    ) -> PositionState:
        row = self.get_open_position_row(symbol, strategy_mode)
        if row is None:
            row = PaperPosition(
                symbol=str(symbol).strip().upper(),
                strategy_mode=strategy_mode,
                opened_at=opened_at or datetime.utcnow(),
            )
            self.session.add(row)

        row.side = side
        row.quantity = quantity
        row.avg_entry_price = avg_entry_price
        row.current_price = current_price
        row.market_value = market_value
        row.unrealized_pnl = unrealized_pnl
        row.realized_pnl = realized_pnl
        row.status = status
        row.updated_at = datetime.utcnow()
        if stop_loss_price is not None:
            row.stop_loss_price = stop_loss_price
        if trailing_stop_pct is not None:
            row.trailing_stop_pct = trailing_stop_pct
        if trailing_stop_price is not None:
            row.trailing_stop_price = trailing_stop_price
        if high_water_mark is not None:
            row.high_water_mark = high_water_mark
        self.session.flush()
        return _serialize_position(row)

    def close_position(self, row: PaperPosition, *, current_price: float, realized_pnl: float) -> PositionState:
        row.current_price = current_price
        row.market_value = 0.0
        row.unrealized_pnl = 0.0
        row.realized_pnl = float(row.realized_pnl or 0.0) + float(realized_pnl or 0.0)
        row.status = "CLOSED"
        row.updated_at = datetime.utcnow()
        self.session.flush()
        return _serialize_position(row)

    def append_trade(self, trade: TradeRecord) -> TradeRecord:
        row = PaperTrade(
            symbol=trade.symbol,
            strategy_mode=trade.strategy_mode,
            action=trade.action,
            side=trade.side,
            quantity=trade.quantity,
            price=trade.price,
            realized_pnl=trade.realized_pnl,
            notes=trade.notes,
        )
        self.session.add(row)
        self.session.flush()
        return _serialize_trade(row)

    def list_trades(self, limit: int = 100) -> list[TradeRecord]:
        rows = self.session.query(PaperTrade).order_by(PaperTrade.created_at.desc()).limit(limit).all()
        return [_serialize_trade(row) for row in rows]

    def append_signal(self, signal: SignalRecord) -> SignalRecord:
        row = SignalHistory(
            symbol=signal.symbol,
            strategy_mode=signal.strategy_mode,
            signal=signal.signal,
            confidence=signal.confidence,
            price=signal.price,
            reasoning=signal.reasoning,
            payload_json=dumps_json(signal.payload),
        )
        self.session.add(row)
        self.session.flush()
        return _serialize_signal(row)

    def latest_signal(self, symbol: str, strategy_mode: str) -> SignalRecord | None:
        row = (
            self.session.query(SignalHistory)
            .filter(
                SignalHistory.symbol == str(symbol).strip().upper(),
                SignalHistory.strategy_mode == strategy_mode,
            )
            .order_by(SignalHistory.created_at.desc())
            .first()
        )
        return None if row is None else _serialize_signal(row)

    def list_signals(self, limit: int = 100) -> list[SignalRecord]:
        rows = self.session.query(SignalHistory).order_by(SignalHistory.created_at.desc()).limit(limit).all()
        return [_serialize_signal(row) for row in rows]

    def append_alert(self, alert: AlertRecord) -> AlertRecord:
        row = AlertHistory(
            symbol=alert.symbol,
            strategy_mode=alert.strategy_mode,
            alert_type=alert.alert_type,
            severity=alert.severity,
            message=alert.message,
            payload_json=dumps_json(alert.payload),
        )
        self.session.add(row)
        self.session.flush()
        return _serialize_alert(row)

    def list_alerts(self, limit: int = 100, severity: str | None = None) -> list[AlertRecord]:
        query = self.session.query(AlertHistory)
        if severity:
            query = query.filter(AlertHistory.severity == severity)
        rows = query.order_by(AlertHistory.created_at.desc()).limit(limit).all()
        return [_serialize_alert(row) for row in rows]

    def append_audit_event(self, event: ExecutionEventRecord) -> None:
        self.session.add(ExecutionAuditEvent(
            event_type=event.event_type,
            source=event.source,
            portfolio_source=event.portfolio_source,
            symbol=event.symbol,
            strategy_mode=event.strategy_mode,
            correlation_id=event.correlation_id,
            payload_json=dumps_json(event.payload),
        ))
        self.session.flush()

    def list_audit_events(self, limit: int = 100, symbol: str | None = None) -> list[ExecutionEventRecord]:
        query = self.session.query(ExecutionAuditEvent)
        if symbol:
            query = query.filter(ExecutionAuditEvent.symbol == str(symbol).strip().upper())
        rows = query.order_by(ExecutionAuditEvent.created_at.desc()).limit(limit).all()
        return [_serialize_audit_event(row) for row in rows]

    def append_order(self, order: PaperOrderRecord) -> PaperOrderRecord:
        row = PaperOrder(
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            strategy_mode=order.strategy_mode,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            limit_price=order.limit_price,
            status=order.status,
            notes=order.notes,
        )
        self.session.add(row)
        self.session.flush()
        return _serialize_order(row)

    def list_orders(self, limit: int = 100, status: str | None = "OPEN") -> list[PaperOrderRecord]:
        query = self.session.query(PaperOrder)
        if status:
            query = query.filter(PaperOrder.status == status)
        rows = query.order_by(PaperOrder.updated_at.desc()).limit(limit).all()
        return [_serialize_order(row) for row in rows]

    def get_order_row(self, order_id: int) -> PaperOrder | None:
        return self.session.query(PaperOrder).filter(PaperOrder.id == int(order_id)).first()

    def serialize_order(self, row: PaperOrder) -> PaperOrderRecord:
        """Expose the serializer so callers can convert a raw row without re-querying."""
        return _serialize_order(row)

    def get_order_by_client_id(self, client_order_id: str) -> PaperOrder | None:
        """Return an existing order by its client_order_id, or None."""
        return (
            self.session.query(PaperOrder)
            .filter(PaperOrder.client_order_id == str(client_order_id).strip())
            .first()
        )

    def has_audit_event(self, event_type: str, correlation_id: str) -> bool:
        """Return True if any audit event with (event_type, correlation_id) exists."""
        return (
            self.session.query(ExecutionAuditEvent.id)
            .filter(
                ExecutionAuditEvent.event_type == event_type,
                ExecutionAuditEvent.correlation_id == correlation_id,
            )
            .first()
        ) is not None

    def cancel_order(self, row: PaperOrder, note: str | None = None) -> PaperOrderRecord:
        row.status = "CANCELED"
        row.updated_at = datetime.utcnow()
        if note:
            row.notes = note
        self.session.flush()
        return _serialize_order(row)
