"""Internal Tool Gateway.

Provides an MCP-like internal tool dispatch layer for AI-facing services.
Every tool reachable from the AI/explanation layer must be registered here.

Design rules
------------
- AI-facing services call tools via ``get_tool_gateway().call(tool_name, **kwargs)``
- Broker execution, order creation, halt control are NOT registered here
- Each tool has: name, description, handler, timeout, audit flag
- All calls are automatically audited (last 200 entries kept in memory)
- Tools degrade gracefully — handler errors return a structured error dict
- The gateway is a module-level singleton (initialised lazily)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.app.core.logging_utils import get_logger, log_event

logger = get_logger(__name__)


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    timeout_seconds: float = 30.0
    audit: bool = True
    safe: bool = True  # safe = exposed to AI layer


class ToolGateway:
    """Registry and dispatcher for AI-safe internal tools."""

    def __init__(self) -> None:
        self._registry: dict[str, ToolSpec] = {}
        self._audit_log: list[dict] = []
        self._counters: dict[str, int] = {}

    def register(self, spec: ToolSpec) -> None:
        self._registry[spec.name] = spec
        log_event(logger, logging.DEBUG, "tool_gateway.registered", tool=spec.name)

    def call(self, tool_name: str, **kwargs: Any) -> dict:
        """Dispatch a tool call. Returns a dict; errors are structured, not raised."""
        spec = self._registry.get(tool_name)
        if spec is None:
            log_event(logger, logging.WARNING, "tool_gateway.unknown_tool", tool=tool_name)
            return {"error": f"Unknown tool: {tool_name}", "tool": tool_name}

        start = time.monotonic()
        error_str: str | None = None
        result: dict = {}

        try:
            raw = spec.handler(**kwargs)
            result = raw if isinstance(raw, dict) else {"result": raw}
        except Exception as exc:
            error_str = str(exc)
            result = {"error": error_str, "tool": tool_name}
            log_event(logger, logging.WARNING, "tool_gateway.call_error",
                      tool=tool_name, error=error_str)

        elapsed = round(time.monotonic() - start, 4)
        self._counters[tool_name] = self._counters.get(tool_name, 0) + 1

        if spec.audit:
            safe_kwargs = {k: v for k, v in kwargs.items()
                          if k not in {"api_key", "secret", "password"}}
            self._audit_log.append({
                "tool": tool_name,
                "kwargs": safe_kwargs,
                "elapsed_seconds": elapsed,
                "error": error_str,
                "timestamp": time.time(),
            })
            if len(self._audit_log) > 200:
                self._audit_log = self._audit_log[-200:]

        return result

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "timeout_seconds": s.timeout_seconds,
                "safe": s.safe,
            }
            for s in self._registry.values()
        ]

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        return list(self._audit_log[-limit:])

    def get_counters(self) -> dict[str, int]:
        return dict(self._counters)


# ---------------------------------------------------------------------------
# Singleton + default tool registration
# ---------------------------------------------------------------------------

_gateway: ToolGateway | None = None


def get_tool_gateway() -> ToolGateway:
    global _gateway
    if _gateway is None:
        _gateway = ToolGateway()
        _register_default_tools(_gateway)
    return _gateway


def _register_default_tools(gateway: ToolGateway) -> None:  # noqa: C901
    """Register all AI-safe tools. No broker/execution tools are registered."""

    # ------------------------------------------------------------------
    # get_market_context
    # ------------------------------------------------------------------
    def _get_market_context(symbol: str, **_: Any) -> dict:
        from backend.app.services.market_data import fetch_quote_snapshots
        snapshot = fetch_quote_snapshots([str(symbol or "").strip().upper()])
        items = snapshot.get("items", [])
        return items[0] if items else {"symbol": symbol, "price": None}

    # ------------------------------------------------------------------
    # get_news_context
    # ------------------------------------------------------------------
    def _get_news_context(symbol: str, limit: int = 5, **_: Any) -> dict:
        try:
            from backend.app.services.ai_news_analyst import get_news_for_symbol  # type: ignore[attr-defined]
            return get_news_for_symbol(symbol=symbol, limit=int(limit))
        except Exception as exc:
            return {"symbol": symbol, "items": [], "error": str(exc)}

    # ------------------------------------------------------------------
    # get_strategy_metrics
    # ------------------------------------------------------------------
    def _get_strategy_metrics(symbol: str, **_: Any) -> dict:
        from backend.app.services.strategy_lab import list_strategy_evaluations
        rows = (list_strategy_evaluations(limit=20) or {}).get("items", [])
        sym = str(symbol or "").strip().upper()
        for row in rows:
            if str(row.get("instrument", "")).strip().upper() == sym:
                return row
        return {"symbol": symbol, "items": []}

    # ------------------------------------------------------------------
    # get_risk_summary
    # ------------------------------------------------------------------
    def _get_risk_summary(**_: Any) -> dict:
        from backend.app.services.risk_engine import get_risk_dashboard
        return get_risk_dashboard()

    # ------------------------------------------------------------------
    # get_execution_preview
    # ------------------------------------------------------------------
    def _get_execution_preview(symbol: str, side: str, quantity: float, **_: Any) -> dict:
        from backend.app.services.paper_fill_engine import compute_fill
        from backend.app.services.market_data import fetch_quote_snapshots
        snap = fetch_quote_snapshots([str(symbol or "").strip().upper()])
        items = snap.get("items", [])
        ref_price = float((items[0].get("price") if items else None) or 0.0)
        fill = compute_fill(side=str(side or "BUY").upper(),
                            quantity=float(quantity or 1),
                            reference_price=ref_price)
        return fill.to_audit_dict()

    # ------------------------------------------------------------------
    # get_portfolio_context
    # ------------------------------------------------------------------
    def _get_portfolio_context(**_: Any) -> dict:
        from backend.app.application.execution.service import get_internal_portfolio
        return get_internal_portfolio(limit=100)

    # ------------------------------------------------------------------
    # write_journal_note  (safe write — text only, no execution)
    # ------------------------------------------------------------------
    def _write_journal_note(symbol: str, note: str, **_: Any) -> dict:
        from datetime import datetime
        try:
            from backend.app.services.storage import session_scope
            from backend.app.models.journal import TradeJournalEntry
            with session_scope() as session:
                entry = TradeJournalEntry(
                    symbol=str(symbol or "").strip().upper(),
                    note=str(note or "")[:2000],
                    source="ai_tool_gateway",
                    created_at=datetime.utcnow(),
                )
                session.add(entry)
            return {"status": "written", "symbol": symbol}
        except Exception as exc:
            return {"status": "error", "error": str(exc), "symbol": symbol}

    gateway.register(ToolSpec(
        name="get_market_context",
        description="Fetch current price and quote snapshot for a symbol.",
        handler=_get_market_context,
    ))
    gateway.register(ToolSpec(
        name="get_news_context",
        description="Fetch latest news items and sentiment for a symbol.",
        handler=_get_news_context,
    ))
    gateway.register(ToolSpec(
        name="get_strategy_metrics",
        description="Retrieve strategy lab evaluation metrics for a symbol.",
        handler=_get_strategy_metrics,
    ))
    gateway.register(ToolSpec(
        name="get_risk_summary",
        description="Get the current portfolio risk summary and exposure.",
        handler=_get_risk_summary,
    ))
    gateway.register(ToolSpec(
        name="get_execution_preview",
        description="Preview a paper trade fill without executing it.",
        handler=_get_execution_preview,
    ))
    gateway.register(ToolSpec(
        name="get_portfolio_context",
        description="Get the current paper portfolio open positions.",
        handler=_get_portfolio_context,
    ))
    gateway.register(ToolSpec(
        name="write_journal_note",
        description="Write a text note to the trade journal. Non-executable.",
        handler=_write_journal_note,
        timeout_seconds=5.0,
    ))
