from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.platform_events import (
    DeadLetterEvent,
    EventReplayJob,
    OrderEvent,
    OrderIntent,
    PortfolioSnapshotRecord,
    ProviderHealth,
    RiskDecision,
    WorkflowRun,
)
from backend.app.services.storage import dumps_json, loads_json


class PlatformEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append_order_intent(
        self,
        *,
        order_intent_id: str,
        signal_id: str | None,
        broker: str,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        time_in_force: str,
        client_order_id: str | None,
        idempotency_key: str | None,
        status: str,
        correlation_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(OrderIntent(
            order_intent_id=order_intent_id,
            signal_id=signal_id,
            broker=broker,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            time_in_force=time_in_force,
            client_order_id=client_order_id,
            idempotency_key=idempotency_key,
            status=status,
            correlation_id=correlation_id,
            payload_json=dumps_json(payload),
        ))
        self.session.flush()

    def append_risk_decision(
        self,
        *,
        signal_id: str | None,
        symbol: str,
        intent: str,
        side: str,
        decision: str,
        approved_qty: float | None,
        reason_codes: list[str] | None,
        risk_snapshot: dict[str, Any] | None,
        correlation_id: str | None,
    ) -> None:
        self.session.add(RiskDecision(
            signal_id=signal_id,
            symbol=symbol,
            intent=intent,
            side=side,
            decision=decision,
            approved_qty=approved_qty,
            reason_codes_json=dumps_json(reason_codes or []),
            risk_snapshot_json=dumps_json(risk_snapshot or {}),
            correlation_id=correlation_id,
        ))
        self.session.flush()

    def append_order_event(
        self,
        *,
        event_id: str,
        event_type: str,
        event_version: str,
        producer: str,
        correlation_id: str | None,
        payload: dict[str, Any] | None,
        order_intent_id: str | None = None,
        client_order_id: str | None = None,
        symbol: str | None = None,
    ) -> None:
        self.session.add(OrderEvent(
            event_id=event_id,
            order_intent_id=order_intent_id,
            client_order_id=client_order_id,
            symbol=symbol,
            event_type=event_type,
            event_version=event_version,
            producer=producer,
            correlation_id=correlation_id,
            payload_json=dumps_json(payload),
        ))
        self.session.flush()

    def append_portfolio_snapshot(
        self,
        *,
        snapshot_type: str,
        active_source: str | None,
        correlation_id: str | None,
        summary: dict[str, Any] | None,
        positions: list[dict[str, Any]] | None,
    ) -> None:
        self.session.add(PortfolioSnapshotRecord(
            snapshot_type=snapshot_type,
            active_source=active_source,
            correlation_id=correlation_id,
            summary_json=dumps_json(summary or {}),
            positions_json=dumps_json(positions or []),
        ))
        self.session.flush()

    def append_dead_letter_event(
        self,
        *,
        event_id: str,
        event_type: str,
        producer: str,
        correlation_id: str | None,
        payload: dict[str, Any] | None,
        error_message: str,
    ) -> None:
        self.session.add(DeadLetterEvent(
            event_id=event_id,
            event_type=event_type,
            producer=producer,
            correlation_id=correlation_id,
            payload_json=dumps_json(payload or {}),
            error_message=error_message,
        ))
        self.session.flush()

    def record_provider_health(
        self,
        *,
        provider_type: str,
        provider_name: str,
        healthy: bool,
        detail: str | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(ProviderHealth(
            provider_type=provider_type,
            provider_name=provider_name,
            healthy=healthy,
            detail=detail,
            payload_json=dumps_json(payload or {}),
        ))
        self.session.flush()

    def create_workflow_run(self, *, workflow_name: str, correlation_id: str | None, payload: dict[str, Any] | None) -> WorkflowRun:
        row = WorkflowRun(
            workflow_name=workflow_name,
            status="started",
            correlation_id=correlation_id,
            payload_json=dumps_json(payload or {}),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def complete_workflow_run(self, row: WorkflowRun, *, status: str, result: dict[str, Any] | None) -> None:
        row.status = status
        row.result_json = dumps_json(result or {})
        row.updated_at = datetime.now(UTC).replace(tzinfo=None)
        self.session.flush()

    def create_event_replay_job(
        self,
        *,
        job_name: str,
        event_type_filter: str | None,
        replay_since: datetime | None = None,
    ) -> EventReplayJob:
        row = EventReplayJob(
            job_name=job_name,
            status="started",
            event_type_filter=event_type_filter,
            replay_since=replay_since,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def complete_event_replay_job(self, row: EventReplayJob, *, status: str, result: dict[str, Any] | None) -> None:
        row.status = status
        row.result_json = dumps_json(result or {})
        row.updated_at = datetime.now(UTC).replace(tzinfo=None)
        self.session.flush()

    def list_order_events(self, *, limit: int = 100, event_type: str | None = None) -> list[dict[str, Any]]:
        query = self.session.query(OrderEvent)
        if event_type:
            query = query.filter(OrderEvent.event_type == event_type)
        rows = query.order_by(OrderEvent.created_at.desc()).limit(limit).all()
        return [
            {
                "event_id": row.event_id,
                "event_type": row.event_type,
                "event_version": row.event_version,
                "producer": row.producer,
                "correlation_id": row.correlation_id,
                "order_intent_id": row.order_intent_id,
                "client_order_id": row.client_order_id,
                "symbol": row.symbol,
                "payload": loads_json(row.payload_json),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

