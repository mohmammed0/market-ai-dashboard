from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.domain.broker.contracts import BrokerSummary
from backend.app.models.broker_state import BrokerAccountSnapshot, BrokerPositionSnapshot
from backend.app.services.storage import dumps_json, loads_json


class BrokerSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record_summary(self, summary: BrokerSummary) -> None:
        account = summary.account
        if account is not None:
            self.session.add(BrokerAccountSnapshot(
                provider=summary.status.provider,
                mode=summary.status.mode,
                account_id=account.account_id,
                status=account.status,
                cash=account.cash,
                equity=account.equity,
                buying_power=account.buying_power,
                portfolio_value=account.portfolio_value,
                is_connected=summary.status.connected,
                payload_json=dumps_json(account.model_dump()),
            ))

        for position in summary.positions:
            self.session.add(BrokerPositionSnapshot(
                provider=summary.status.provider,
                mode=summary.status.mode,
                account_id=account.account_id if account else None,
                symbol=position.symbol or "",
                side=position.side,
                qty=position.qty,
                market_value=position.market_value,
                unrealized_pnl=position.unrealized_pnl,
                payload_json=dumps_json(position.model_dump()),
            ))

    def latest_summary(self, provider: str | None = None) -> dict:
        query = self.session.query(BrokerAccountSnapshot)
        if provider:
            query = query.filter(BrokerAccountSnapshot.provider == provider)
        account_row = query.order_by(BrokerAccountSnapshot.captured_at.desc()).first()
        if account_row is None:
            return {"account": None, "positions": []}

        position_rows = (
            self.session.query(BrokerPositionSnapshot)
            .filter(BrokerPositionSnapshot.provider == account_row.provider, BrokerPositionSnapshot.mode == account_row.mode)
            .order_by(BrokerPositionSnapshot.captured_at.desc())
            .limit(50)
            .all()
        )
        return {
            "account": loads_json(account_row.payload_json),
            "positions": [loads_json(row.payload_json) for row in position_rows],
        }
