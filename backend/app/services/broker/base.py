from __future__ import annotations

from typing import Any

from backend.app.services.runtime_settings import get_broker_guardrails


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(value)
    except Exception:
        return int(default)


class BrokerProvider:
    provider_name = "none"
    mode = "disabled"

    def _base_status(self, **overrides) -> dict:
        guardrails = get_broker_guardrails()
        payload = {
            "provider": self.provider_name,
            "enabled": False,
            "configured": False,
            "sdk_installed": False,
            "connected": False,
            "mode": self.mode,
            "paper": True,
            "live_execution_enabled": guardrails["live_execution_enabled"],
            "order_submission_enabled": guardrails["order_submission_enabled"],
            "detail": "Broker integration is disabled.",
        }
        payload.update(overrides)
        return payload

    def get_status(self) -> dict:
        return self._base_status()

    def get_account(self, refresh: bool = False) -> dict:
        return {**self.get_status(), "account": None}

    def get_positions(self, refresh: bool = False) -> dict:
        status = self.get_status()
        return {**status, "items": [], "count": 0}

    def get_orders(self, refresh: bool = False) -> dict:
        status = self.get_status()
        return {**status, "items": [], "count": 0}

    def submit_order(self, symbol: str, qty: float, side: str, order_type: str = "market",
                     time_in_force: str = "day", limit_price: float | None = None,
                     estimated_price: float | None = None,
                     stop_price: float | None = None, take_profit_price: float | None = None,
                     stop_loss_price: float | None = None) -> dict:
        """Submit an order to the broker. Returns order details or error."""
        return {"ok": False, "error": "Broker does not support order submission.", "order": None}

    def cancel_order(self, order_id: str) -> dict:
        """Cancel an existing order."""
        return {"ok": False, "error": "Broker does not support order cancellation."}

    def get_summary(self, refresh: bool = False) -> dict:
        account_payload = self.get_account(refresh=refresh)
        positions_payload = self.get_positions(refresh=refresh)
        orders_payload = self.get_orders(refresh=refresh)
        positions = positions_payload.get("items", [])
        orders = orders_payload.get("items", [])
        return {
            **self.get_status(),
            "account": account_payload.get("account"),
            "positions": positions,
            "orders": orders,
            "totals": {
                "positions": len(positions),
                "open_orders": len(orders),
                "market_value": round(sum(_safe_float(item.get("market_value")) for item in positions), 2),
                "unrealized_pnl": round(sum(_safe_float(item.get("unrealized_pnl")) for item in positions), 2),
            },
        }


class DisabledBrokerProvider(BrokerProvider):
    def __init__(self, detail: str = "Broker integration is disabled.") -> None:
        self.detail = detail

    def get_status(self) -> dict:
        return self._base_status(detail=self.detail)
