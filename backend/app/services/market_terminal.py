from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from backend.app.models import AlertHistory
from backend.app.services.cached_analysis import get_ranked_analysis_result
from backend.app.services.decision_support import build_decision_payload
from backend.app.services.events_calendar import fetch_market_events
from backend.app.services.market_data import fetch_quote_snapshots, get_recent_quote_series, load_history
from backend.app.services.market_universe import (
    get_market_overview,
    get_market_symbol_snapshot,
    get_market_universe_facets,
    search_market_universe,
)
from backend.app.services.risk_engine import get_risk_dashboard
from backend.app.services.storage import session_scope
from backend.app.services.workspace_store import get_workspace_overview
from core.source_data import normalize_symbol


EASTERN_TZ = ZoneInfo("America/New_York")
TIMEFRAME_CONFIG = {
    "1S": {"mode": "micro", "bucket_seconds": 1},
    "5S": {"mode": "micro", "bucket_seconds": 5},
    "15S": {"mode": "micro", "bucket_seconds": 15},
    "30S": {"mode": "micro", "bucket_seconds": 30},
    "1M": {"interval": "1m"},
    "5M": {"interval": "5m"},
    "15M": {"interval": "15m"},
    "30M": {"interval": "30m"},
    "1H": {"interval": "60m"},
    "4H": {"interval": "60m", "resample_rule": "4H"},
    "1D": {"interval": "1d"},
    "1W": {"interval": "1wk"},
    "1MTH": {"interval": "1mo"},
}
RANGE_DAYS = {
    "TODAY": 1,
    "5D": 5,
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "YTD": None,
    "1Y": 365,
    "5Y": 365 * 5,
    "MAX": 365 * 15,
}


def _session_context() -> dict:
    now_et = datetime.now(EASTERN_TZ)
    minutes = now_et.hour * 60 + now_et.minute
    pre_start = 4 * 60
    regular_start = 9 * 60 + 30
    regular_end = 16 * 60
    after_end = 20 * 60
    if pre_start <= minutes < regular_start:
        label = "ما قبل الافتتاح"
    elif regular_start <= minutes < regular_end:
        label = "الجلسة النظامية"
    elif regular_end <= minutes < after_end:
        label = "ما بعد الإغلاق"
    else:
        label = "السوق مغلق"
    return {
        "label": label,
        "timestamp_et": now_et.isoformat(),
        "is_regular": label == "الجلسة النظامية",
    }


def _date_window(range_key: str) -> tuple[str, str]:
    today = date.today()
    normalized = str(range_key or "3M").strip().upper()
    if normalized == "YTD":
        start = date(today.year, 1, 1)
    else:
        days = RANGE_DAYS.get(normalized, 90)
        start = today - timedelta(days=days)
    return start.isoformat(), today.isoformat()


def _build_frame(items: list[dict]) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    frame = pd.DataFrame(items)
    if "datetime" in frame.columns:
        frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
    numeric_columns = ["open", "high", "low", "close", "volume", "price", "change_pct"]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)


def _resample_ohlcv(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    indexed = frame.set_index("datetime")
    aggregated = indexed.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["close"]).reset_index()
    return aggregated


def _serialize_ohlcv_frame(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    return [
        {
            "datetime": pd.to_datetime(row.datetime).isoformat(timespec="seconds"),
            "open": None if pd.isna(row.open) else round(float(row.open), 4),
            "high": None if pd.isna(row.high) else round(float(row.high), 4),
            "low": None if pd.isna(row.low) else round(float(row.low), 4),
            "close": None if pd.isna(row.close) else round(float(row.close), 4),
            "volume": None if pd.isna(row.volume) else float(row.volume),
        }
        for row in frame.itertuples()
    ]


def _normalize_compare_series(frame: pd.DataFrame, symbol: str, value_column: str = "close") -> dict:
    if frame.empty or value_column not in frame.columns:
        return {"symbol": symbol, "items": []}
    base = float(frame.iloc[0][value_column] or 0.0)
    if base <= 0:
        return {"symbol": symbol, "items": []}
    items = []
    for row in frame.itertuples():
        current = getattr(row, value_column, None)
        if current in (None, 0) or pd.isna(current):
            continue
        items.append({
            "datetime": pd.to_datetime(row.datetime).isoformat(timespec="seconds"),
            "value": round(((float(current) / base) - 1.0) * 100.0, 4),
        })
    return {"symbol": symbol, "items": items}


def build_market_terminal_bootstrap(
    *,
    symbol: str = "AAPL",
    q: str = "",
    exchange: str = "ALL",
    security_type: str = "all",
    category: str = "all",
    limit: int = 40,
) -> dict:
    normalized_symbol = normalize_symbol(symbol or "AAPL")
    explorer = search_market_universe(q=q, exchange=exchange, security_type=security_type, category=category, limit=limit, include_quotes=True)
    snapshot = get_market_symbol_snapshot(normalized_symbol)
    workspace = get_workspace_overview()
    return {
        "overview": get_market_overview(),
        "facets": get_market_universe_facets(),
        "explorer": explorer,
        "selected_snapshot": snapshot,
        "workspace": workspace,
        "session": _session_context(),
    }


def build_market_terminal_chart(
    *,
    symbol: str,
    timeframe: str = "1D",
    range_key: str = "3M",
    compare_symbols: list[str] | None = None,
) -> dict:
    normalized_symbol = normalize_symbol(symbol)
    normalized_timeframe = str(timeframe or "1D").strip().upper()
    normalized_range = str(range_key or "3M").strip().upper()
    compare_list = [normalize_symbol(item) for item in (compare_symbols or []) if str(item).strip()]
    compare_list = [item for index, item in enumerate(compare_list) if item != normalized_symbol and item not in compare_list[:index]][:3]

    start_date, end_date = _date_window(normalized_range)
    config = TIMEFRAME_CONFIG.get(normalized_timeframe, TIMEFRAME_CONFIG["1D"])
    data_mode = "candlestick"
    items = []
    compare_payload = []
    data_note = None

    if config.get("mode") == "micro":
        fetch_quote_snapshots([normalized_symbol, *compare_list], include_profile=False)
        lookback_minutes = 60 if normalized_range == "TODAY" else 240
        series = get_recent_quote_series(normalized_symbol, bucket_seconds=config["bucket_seconds"], lookback_minutes=lookback_minutes)
        frame = _build_frame(series.get("items", []))
        if frame.empty:
            data_note = "بيانات اللقطات اللحظية لا تزال تتراكم. استمر في التحديث الحي لملء العرض تحت الدقيقة."
        items = [
            {
                "datetime": pd.to_datetime(row.datetime).isoformat(timespec="seconds"),
                "price": None if pd.isna(row.price) else round(float(row.price), 4),
                "volume": None if pd.isna(row.volume) else float(row.volume),
            }
            for row in frame.itertuples()
        ]
        data_mode = "line"
        compare_payload = [
            _normalize_compare_series(_build_frame(get_recent_quote_series(item, bucket_seconds=config["bucket_seconds"], lookback_minutes=lookback_minutes).get("items", [])), item, value_column="price")
            for item in compare_list
        ]
        compare_payload = [item for item in compare_payload if item["items"]]
    else:
        history = load_history(normalized_symbol, start_date=start_date, end_date=end_date, interval=config["interval"], persist=True)
        frame = _build_frame(history.get("items", []))
        if config.get("resample_rule") and not frame.empty:
            frame = _resample_ohlcv(frame, config["resample_rule"])
        items = _serialize_ohlcv_frame(frame)
        compare_payload = []
        for compare_symbol in compare_list:
            compare_history = load_history(compare_symbol, start_date=start_date, end_date=end_date, interval=config["interval"], persist=True)
            compare_frame = _build_frame(compare_history.get("items", []))
            if config.get("resample_rule") and not compare_frame.empty:
                compare_frame = _resample_ohlcv(compare_frame, config["resample_rule"])
            compare_payload.append(_normalize_compare_series(compare_frame, compare_symbol))
        compare_payload = [item for item in compare_payload if item["items"]]

    return {
        "symbol": normalized_symbol,
        "timeframe": normalized_timeframe,
        "range_key": normalized_range,
        "compare_symbols": compare_list,
        "mode": data_mode,
        "items": items,
        "compare_series": compare_payload,
        "session": _session_context(),
        "data_note": data_note,
    }


def build_market_terminal_context(symbol: str, start_date: str = "2024-01-01", end_date: str | None = None) -> dict:
    normalized_symbol = normalize_symbol(symbol)
    resolved_end_date = end_date or date.today().isoformat()
    decision = build_decision_payload(
        normalized_symbol,
        start_date,
        resolved_end_date,
        include_dl=True,
        include_ensemble=True,
    )
    analysis = decision.get("analysis") or get_ranked_analysis_result(
        normalized_symbol,
        start_date,
        resolved_end_date,
        include_ml=True,
        include_dl=True,
        ttl_seconds=300,
    )
    risk = get_risk_dashboard()
    with session_scope() as session:
        alert_rows = (
            session.query(AlertHistory)
            .filter(AlertHistory.symbol == normalized_symbol)
            .order_by(AlertHistory.created_at.desc())
            .limit(4)
            .all()
        )
    alerts = [
        {
            "id": row.id,
            "alert_type": row.alert_type,
            "severity": row.severity,
            "message": row.message,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in alert_rows
    ]
    events = fetch_market_events(symbols=[normalized_symbol], limit=4)
    return {
        "symbol": normalized_symbol,
        "decision": decision,
        "signal": {
            "signal": analysis.get("signal"),
            "enhanced_signal": analysis.get("enhanced_signal"),
            "confidence": analysis.get("confidence"),
            "best_setup": analysis.get("best_setup"),
            "setup_type": analysis.get("setup_type"),
            "technical_score": analysis.get("technical_score"),
            "enhanced_combined_score": analysis.get("enhanced_combined_score"),
        },
        "risk": {
            "gross_exposure_pct": risk.get("gross_exposure_pct"),
            "portfolio_warnings": risk.get("portfolio_warnings", [])[:3],
        },
        "alerts": alerts,
        "events": events.get("items", []),
    }
