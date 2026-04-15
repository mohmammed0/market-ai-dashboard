from __future__ import annotations

import logging
from typing import Any

from backend.app.core.logging_utils import log_event
from backend.app.config import ALPACA_ACCOUNT_REFRESH_SECONDS
from backend.app.services.cache import get_cache
from backend.app.services.broker.base import BrokerProvider, _safe_float, _safe_int
from backend.app.services.runtime_settings import get_alpaca_runtime_config

try:
    from alpaca.trading.client import TradingClient
except Exception:  # pragma: no cover - optional dependency
    TradingClient = None

try:
    from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest, LimitOrderRequest, StopOrderRequest, StopLimitOrderRequest
except Exception:  # pragma: no cover - optional dependency
    GetOrdersRequest = None
    MarketOrderRequest = None
    LimitOrderRequest = None
    StopOrderRequest = None
    StopLimitOrderRequest = None

try:
    from alpaca.trading.enums import OrderSide, TimeInForce
except Exception:  # pragma: no cover - optional dependency
    OrderSide = None
    TimeInForce = None

try:
    from alpaca.trading.enums import QueryOrderStatus
except Exception:  # pragma: no cover - optional dependency
    QueryOrderStatus = None


logger = logging.getLogger(__name__)
_LAST_CONNECTIVITY_STATE: tuple[bool | None, str | None] = (None, None)
_LAST_REQUEST_FAILURE: tuple[str | None, str | None] = (None, None)


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _enum_text(value: Any) -> str | None:
    text = _coerce_text(value)
    if not text:
        return None
    return text.split(".")[-1].strip() or None


def _serialize_account(account: Any) -> dict:
    return {
        "account_id": _coerce_text(getattr(account, "id", None)),
        "status": _enum_text(getattr(account, "status", None)),
        "currency": _coerce_text(getattr(account, "currency", None)),
        "equity": _safe_float(getattr(account, "equity", None)),
        "cash": _safe_float(getattr(account, "cash", None)),
        "buying_power": _safe_float(getattr(account, "buying_power", None)),
        "portfolio_value": _safe_float(getattr(account, "portfolio_value", None)),
        "daytrade_count": _safe_int(getattr(account, "daytrade_count", None)),
        "pattern_day_trader": bool(getattr(account, "pattern_day_trader", False)),
        "trading_blocked": bool(getattr(account, "trading_blocked", False)),
        "transfers_blocked": bool(getattr(account, "transfers_blocked", False)),
        "account_blocked": bool(getattr(account, "account_blocked", False)),
    }


def _serialize_position(position: Any) -> dict:
    _raw_side = _coerce_text(getattr(position, "side", None)) or "long"
    side = _raw_side.split(".")[-1].upper()  # "PositionSide.LONG" → "LONG"
    qty = _safe_float(getattr(position, "qty", None))
    return {
        "symbol": _coerce_text(getattr(position, "symbol", None)),
        "side": side,
        "qty": qty,
        "avg_entry_price": _safe_float(getattr(position, "avg_entry_price", None)),
        "market_value": _safe_float(getattr(position, "market_value", None)),
        "cost_basis": _safe_float(getattr(position, "cost_basis", None)),
        "current_price": _safe_float(getattr(position, "current_price", None)),
        "unrealized_pnl": _safe_float(getattr(position, "unrealized_pl", None)),
        "unrealized_pnl_pct": round(_safe_float(getattr(position, "unrealized_plpc", None)) * 100.0, 2),
        "change_today_pct": round(_safe_float(getattr(position, "change_today", None)) * 100.0, 2),
    }


def _serialize_order(order: Any) -> dict:
    return {
        "id": _coerce_text(getattr(order, "id", None)),
        "client_order_id": _coerce_text(getattr(order, "client_order_id", None)),
        "symbol": _coerce_text(getattr(order, "symbol", None)),
        "side": _enum_text(getattr(order, "side", None)),
        "type": _enum_text(getattr(order, "order_type", None)),
        "status": _enum_text(getattr(order, "status", None)),
        "qty": _safe_float(getattr(order, "qty", None)),
        "filled_qty": _safe_float(getattr(order, "filled_qty", None)),
        "filled_avg_price": _safe_float(getattr(order, "filled_avg_price", None)),
        "submitted_at": _coerce_text(getattr(order, "submitted_at", None)),
        "updated_at": _coerce_text(getattr(order, "updated_at", None)),
    }


class AlpacaBrokerProvider(BrokerProvider):
    provider_name = "alpaca"

    @staticmethod
    def _log_connectivity_change(connected: bool, detail: str | None) -> None:
        global _LAST_CONNECTIVITY_STATE
        next_state = (bool(connected), str(detail or ""))
        if next_state == _LAST_CONNECTIVITY_STATE:
            return
        _LAST_CONNECTIVITY_STATE = next_state
        log_event(
            logger,
            logging.INFO if connected else logging.WARNING,
            "broker.alpaca.connectivity",
            connected=connected,
            detail=detail,
        )

    @staticmethod
    def _mode(config: dict) -> str:
        return "paper" if config.get("paper", True) else "live"

    @staticmethod
    def _summarize_exception(exc: Exception) -> str:
        detail = " ".join(str(exc).split()).strip()
        return detail or exc.__class__.__name__

    @staticmethod
    def _log_request_failure(operation: str, exc: Exception) -> None:
        global _LAST_REQUEST_FAILURE
        detail = AlpacaBrokerProvider._summarize_exception(exc)
        next_state = (operation, detail)
        if next_state == _LAST_REQUEST_FAILURE:
            return
        _LAST_REQUEST_FAILURE = next_state
        log_event(
            logger,
            logging.WARNING,
            "broker.alpaca.request_failed",
            operation=operation,
            detail=detail,
        )

    def _base_alpaca_status(self, config: dict, **overrides) -> dict:
        payload = self._base_status(
            enabled=config.get("enabled", False),
            configured=bool(config.get("api_key") and config.get("secret_key")),
            sdk_installed=TradingClient is not None,
            mode=self._mode(config),
            paper=bool(config.get("paper", True)),
            live_execution_enabled=bool(config.get("live_execution_enabled", False)),
            order_submission_enabled=bool(config.get("order_submission_enabled", False)),
            detail="Alpaca broker integration is ready."
            if config.get("enabled", False)
            else "Alpaca integration is disabled by configuration.",
        )
        payload.update(overrides)
        return payload

    def _can_connect(self) -> tuple[bool, dict]:
        config = get_alpaca_runtime_config()
        if not config.get("enabled", False):
            return False, self._base_alpaca_status(config, detail="Alpaca integration is disabled by configuration.")
        if TradingClient is None:
            return False, self._base_alpaca_status(config, detail="alpaca-py is not installed.")
        if not config.get("api_key") or not config.get("secret_key"):
            return False, self._base_alpaca_status(config, detail="Alpaca API credentials are not configured.")
        return True, self._base_alpaca_status(config, detail="Alpaca credentials configured.")

    def _client(self):
        can_connect, status = self._can_connect()
        if not can_connect:
            return None, status
        try:
            config = get_alpaca_runtime_config()
            kwargs = {"paper": bool(config.get("paper", True))}
            if config.get("url_override"):
                kwargs["url_override"] = config["url_override"]
            return TradingClient(config["api_key"], config["secret_key"], **kwargs), None
        except Exception as exc:  # pragma: no cover - external client init
            logger.exception("Failed to initialize Alpaca TradingClient.")
            config = get_alpaca_runtime_config()
            return None, self._base_alpaca_status(config, detail=f"Failed to initialize Alpaca client: {exc}")

    def _cached(self, key: str, factory, refresh: bool = False):
        cache = get_cache()
        if refresh:
            return cache.set(key, factory(), ttl_seconds=ALPACA_ACCOUNT_REFRESH_SECONDS)
        return cache.get_or_set(key, factory, ttl_seconds=ALPACA_ACCOUNT_REFRESH_SECONDS)

    def get_status(self) -> dict:
        client, status = self._client()
        if client is None:
            self._log_connectivity_change(False, status.get("detail"))
            return status
        config = get_alpaca_runtime_config()
        try:
            account = self._cached("broker:alpaca:account:status", client.get_account)
            serialized = _serialize_account(account)
            payload = self._base_alpaca_status(
                config,
                connected=True,
                detail=f"Connected to Alpaca {self._mode(config)} account.",
                account_status=serialized.get("status"),
                account_id=serialized.get("account_id"),
                cash=serialized.get("cash"),
                equity=serialized.get("equity"),
            )
            self._log_connectivity_change(True, payload.get("detail"))
            return payload
        except Exception as exc:  # pragma: no cover - external service
            self._log_request_failure("status", exc)
            payload = self._base_alpaca_status(config, detail=f"Alpaca status request failed: {self._summarize_exception(exc)}")
            self._log_connectivity_change(False, payload.get("detail"))
            return payload

    def get_account(self, refresh: bool = False) -> dict:
        client, status = self._client()
        if client is None:
            return {**status, "account": None}
        config = get_alpaca_runtime_config()
        try:
            account = self._cached("broker:alpaca:account", client.get_account, refresh=refresh)
            return {
                **self._base_alpaca_status(config, connected=True, detail=f"Connected to Alpaca {self._mode(config)} account."),
                "account": _serialize_account(account),
            }
        except Exception as exc:  # pragma: no cover - external service
            self._log_request_failure("account", exc)
            return {
                **self._base_alpaca_status(config, detail=f"Alpaca account request failed: {self._summarize_exception(exc)}"),
                "account": None,
            }

    def get_positions(self, refresh: bool = False) -> dict:
        client, status = self._client()
        if client is None:
            return {**status, "items": [], "count": 0}
        config = get_alpaca_runtime_config()
        try:
            rows = self._cached("broker:alpaca:positions", client.get_all_positions, refresh=refresh)
            items = [_serialize_position(row) for row in rows or []]
            return {
                **self._base_alpaca_status(config, connected=True, detail=f"Loaded {len(items)} Alpaca positions."),
                "items": items,
                "count": len(items),
            }
        except Exception as exc:  # pragma: no cover - external service
            self._log_request_failure("positions", exc)
            return {
                **self._base_alpaca_status(config, detail=f"Alpaca positions request failed: {self._summarize_exception(exc)}"),
                "items": [],
                "count": 0,
            }

    def get_orders(self, refresh: bool = False) -> dict:
        client, status = self._client()
        if client is None:
            return {**status, "items": [], "count": 0}
        config = get_alpaca_runtime_config()
        try:
            def load_orders():
                if GetOrdersRequest is not None and QueryOrderStatus is not None:
                    request = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=50, nested=True)
                    return client.get_orders(filter=request)
                return client.get_orders()

            rows = self._cached("broker:alpaca:orders", load_orders, refresh=refresh)
            items = [_serialize_order(row) for row in rows or []]
            return {
                **self._base_alpaca_status(config, connected=True, detail=f"Loaded {len(items)} Alpaca orders."),
                "items": items,
                "count": len(items),
            }
        except Exception as exc:  # pragma: no cover - external service
            self._log_request_failure("orders", exc)
            return {
                **self._base_alpaca_status(config, detail=f"Alpaca orders request failed: {self._summarize_exception(exc)}"),
                "items": [],
                "count": 0,
            }

    def submit_order(self, symbol: str, qty: float, side: str, order_type: str = "market",
                     time_in_force: str = "day", limit_price: float | None = None,
                     stop_price: float | None = None, take_profit_price: float | None = None,
                     stop_loss_price: float | None = None) -> dict:
        """Submit an order to Alpaca paper/live account."""
        client, status = self._client()
        if client is None:
            return {"ok": False, "error": status.get("detail", "Cannot connect to Alpaca"), "order": None}

        config = get_alpaca_runtime_config()
        if not config.get("order_submission_enabled", False):
            return {"ok": False, "error": "Order submission is disabled in settings.", "order": None}

        if OrderSide is None or TimeInForce is None:
            return {"ok": False, "error": "alpaca-py SDK order classes not available.", "order": None}

        try:
            order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
            tif = TimeInForce.DAY if time_in_force.lower() == "day" else TimeInForce.GTC

            if order_type.lower() == "limit" and limit_price and LimitOrderRequest:
                order_data = LimitOrderRequest(
                    symbol=symbol.upper(), qty=qty, side=order_side,
                    time_in_force=tif, limit_price=limit_price,
                )
            elif order_type.lower() == "stop" and stop_price and StopOrderRequest:
                order_data = StopOrderRequest(
                    symbol=symbol.upper(), qty=qty, side=order_side,
                    time_in_force=tif, stop_price=stop_price,
                )
            elif order_type.lower() == "stop_limit" and stop_price and limit_price and StopLimitOrderRequest:
                order_data = StopLimitOrderRequest(
                    symbol=symbol.upper(), qty=qty, side=order_side,
                    time_in_force=tif, stop_price=stop_price, limit_price=limit_price,
                )
            else:
                if MarketOrderRequest is None:
                    return {"ok": False, "error": "alpaca-py MarketOrderRequest not available.", "order": None}
                order_data = MarketOrderRequest(
                    symbol=symbol.upper(), qty=qty, side=order_side,
                    time_in_force=tif,
                )

            order = client.submit_order(order_data)
            serialized = _serialize_order(order)
            log_event(
                logger, logging.INFO, "broker.alpaca.order_submitted",
                symbol=symbol, side=side, qty=qty, order_type=order_type,
                order_id=serialized.get("id"), mode=self._mode(config),
            )
            # Invalidate orders cache
            cache = get_cache()
            cache.delete("broker:alpaca:orders")
            cache.delete("broker:alpaca:positions")

            return {"ok": True, "error": None, "order": serialized, "mode": self._mode(config)}

        except Exception as exc:
            self._log_request_failure("submit_order", exc)
            return {"ok": False, "error": f"Order submission failed: {self._summarize_exception(exc)}", "order": None}

    def cancel_order(self, order_id: str) -> dict:
        """Cancel an order on Alpaca."""
        client, status = self._client()
        if client is None:
            return {"ok": False, "error": status.get("detail", "Cannot connect to Alpaca")}
        try:
            client.cancel_order_by_id(order_id)
            cache = get_cache()
            cache.delete("broker:alpaca:orders")
            log_event(logger, logging.INFO, "broker.alpaca.order_cancelled", order_id=order_id)
            return {"ok": True, "error": None}
        except Exception as exc:
            self._log_request_failure("cancel_order", exc)
            return {"ok": False, "error": f"Cancel failed: {self._summarize_exception(exc)}"}

    def get_summary(self, refresh: bool = False) -> dict:
        account_payload = self.get_account(refresh=refresh)
        if not account_payload.get("connected", False):
            status = {
                key: account_payload.get(key)
                for key in [
                    "provider",
                    "enabled",
                    "configured",
                    "sdk_installed",
                    "connected",
                    "mode",
                    "paper",
                    "live_execution_enabled",
                    "order_submission_enabled",
                    "detail",
                ]
            }
            return {
                **status,
                "account": account_payload.get("account"),
                "positions": [],
                "orders": [],
                "totals": {
                    "positions": 0,
                    "open_orders": 0,
                    "market_value": 0.0,
                    "unrealized_pnl": 0.0,
                },
            }
        positions_payload = self.get_positions(refresh=refresh)
        orders_payload = self.get_orders(refresh=refresh)
        positions = positions_payload.get("items", [])
        orders = orders_payload.get("items", [])
        status = {
            key: account_payload.get(key)
            for key in [
                "provider",
                "enabled",
                "configured",
                "sdk_installed",
                "connected",
                "mode",
                "paper",
                "live_execution_enabled",
                "order_submission_enabled",
                "detail",
            ]
        }
        return {
            **status,
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
