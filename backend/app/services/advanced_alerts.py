from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from backend.app.config import (
    ALERT_BREAKOUT_PCT,
    ALERT_CONFIDENCE_JUMP,
    ALERT_UNUSUAL_MOVE_PCT,
    ALERT_VOLUME_SPIKE_MULTIPLIER,
)
from backend.app.application.alerts.service import list_alert_history as list_alert_history_view
from backend.app.domain.alerts.contracts import AlertRecord
from backend.app.models import SignalHistory
from backend.app.repositories.execution import ExecutionRepository
from backend.app.services.market_data import fetch_quote_snapshots, load_history
from backend.app.services.storage import session_scope


def _build_alert(symbol, strategy_mode, alert_type, severity, message, payload):
    return {
        "symbol": symbol,
        "strategy_mode": strategy_mode,
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "payload": payload,
    }


def _persist_alerts(items: list[dict]) -> None:
    if not items:
        return
    with session_scope() as session:
        repo = ExecutionRepository(session)
        for item in items:
            repo.append_alert(AlertRecord(
                symbol=item.get("symbol"),
                strategy_mode=item.get("strategy_mode"),
                alert_type=item.get("alert_type"),
                severity=item.get("severity", "info"),
                message=item.get("message", ""),
                payload=item.get("payload", {}),
            ))


def _latest_signal_rows(symbols: list[str]) -> dict:
    latest = {}
    with session_scope() as session:
        rows = (
            session.query(SignalHistory)
            .filter(SignalHistory.symbol.in_(symbols))
            .order_by(SignalHistory.created_at.desc())
            .all()
        )
        for row in rows:
            latest.setdefault(row.symbol, []).append({
                "symbol": row.symbol,
                "signal": row.signal,
                "strategy_mode": row.strategy_mode,
                "confidence": row.confidence,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })
    return latest


def generate_advanced_alerts(symbols: list[str], persist: bool = True) -> dict:
    normalized_symbols = [str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()]
    snapshot_payload = fetch_quote_snapshots(normalized_symbols, include_profile=False)
    quote_items = snapshot_payload.get("items", [])
    snapshots = {item["symbol"]: item for item in quote_items}
    signal_rows = _latest_signal_rows(normalized_symbols)
    alerts = []
    errors = [
        {
            "symbol": item.get("symbol"),
            "stage": "snapshot",
            "error": item.get("error"),
        }
        for item in snapshot_payload.get("errors", [])
        if item.get("error")
    ]

    for symbol in normalized_symbols:
        try:
            snapshot = snapshots.get(symbol) or {}
            change_pct = float(snapshot.get("change_pct") or 0.0)
            volume = float(snapshot.get("volume") or 0.0)

            if change_pct >= ALERT_BREAKOUT_PCT:
                alerts.append(_build_alert(symbol, None, "price_breakout", "warning", f"{symbol} is breaking out with {change_pct:.2f}% upside momentum.", snapshot))
            elif change_pct <= -ALERT_BREAKOUT_PCT:
                alerts.append(_build_alert(symbol, None, "price_breakdown", "warning", f"{symbol} is breaking down with {change_pct:.2f}% downside momentum.", snapshot))

            if abs(change_pct) >= ALERT_UNUSUAL_MOVE_PCT:
                alerts.append(_build_alert(symbol, None, "unusual_move", "critical", f"{symbol} moved {change_pct:.2f}% and triggered the unusual-move threshold.", snapshot))

            history = load_history(symbol, interval="1d", persist=True)
            if history.get("error"):
                errors.append({
                    "symbol": symbol,
                    "stage": "history",
                    "error": history.get("error"),
                })
            else:
                items = history.get("items", [])
                if items:
                    frame = pd.DataFrame(items)
                    recent_volume = pd.to_numeric(frame.get("volume"), errors="coerce").tail(20)
                    avg_volume = float(recent_volume.mean()) if not recent_volume.dropna().empty else 0.0
                    if avg_volume and volume >= avg_volume * ALERT_VOLUME_SPIKE_MULTIPLIER:
                        alerts.append(_build_alert(
                            symbol,
                            None,
                            "volume_spike",
                            "warning",
                            f"{symbol} volume is running {volume / avg_volume:.2f}x its 20-day average.",
                            {"current_volume": volume, "average_volume_20d": avg_volume},
                        ))

            recent_signals = signal_rows.get(symbol, [])
            if len(recent_signals) >= 2:
                latest = recent_signals[0]
                previous = recent_signals[1]
                if str(latest.get("signal")).upper() != str(previous.get("signal")).upper():
                    alerts.append(_build_alert(
                        symbol,
                        latest.get("strategy_mode"),
                        "signal_change",
                        "info",
                        f"{symbol} changed from {previous.get('signal')} to {latest.get('signal')} on {latest.get('strategy_mode')}.",
                        {
                            "previous_signal": previous.get("signal"),
                            "latest_signal": latest.get("signal"),
                            "latest_confidence": latest.get("confidence"),
                        },
                    ))
                if abs(float(latest.get("confidence") or 0.0) - float(previous.get("confidence") or 0.0)) >= ALERT_CONFIDENCE_JUMP:
                    alerts.append(_build_alert(
                        symbol,
                        latest.get("strategy_mode"),
                        "confidence_change",
                        "info",
                        f"{symbol} confidence shifted materially from {previous.get('confidence')} to {latest.get('confidence')}.",
                        {"previous_confidence": previous.get("confidence"), "latest_confidence": latest.get("confidence")},
                    ))
        except Exception as exc:
            errors.append({
                "symbol": symbol,
                "stage": "alert_eval",
                "error": " ".join(str(exc).split()) or exc.__class__.__name__,
            })

    if persist:
        _persist_alerts(alerts)
        # Send Telegram notification for each generated alert (non-blocking)
        try:
            from core.telegram_notifier import send_telegram_message, is_telegram_configured
            if alerts and is_telegram_configured():
                for _alert in alerts:
                    _alert_type = _alert.get("alert_type", "alert")
                    _symbol = _alert.get("symbol", "")
                    _detail = _alert.get("message", "")
                    _msg = f"\U0001f6a8 <b>{_alert_type}</b>\n{_symbol}: {_detail}"
                    send_telegram_message(_msg)
        except Exception:
            pass  # Never let Telegram failure crash the alert pipeline

    failed_symbols = sorted({item.get("symbol") for item in errors if item.get("symbol")})

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "count": len(alerts),
        "requested_symbols": len(normalized_symbols),
        "failed_symbols": len(failed_symbols),
        "error_symbols": failed_symbols[:25],
        "errors": errors[:25],
        "items": alerts,
    }


def list_alert_history(limit: int = 100, severity: str | None = None) -> dict:
    limit = max(1, min(int(limit or 100), 500))
    return list_alert_history_view(limit=limit, severity=severity)
