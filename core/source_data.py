from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import os
from pathlib import Path

import pandas as pd

from core.market_data_providers import fetch_history_from_providers
from core.market_data_settings import (
    MARKET_DATA_SESSION_CLOSE_BUFFER_MINUTES,
    MARKET_DATA_SESSION_CLOSE_HOUR,
    MARKET_DATA_SESSION_CLOSE_MINUTE,
    MARKET_DATA_TIMEZONE,
)
from core.runtime_paths import LEGACY_SOURCE_DIR, ROOT_DIR, SEED_SOURCE_DIR, SOURCE_CACHE_DIR, ensure_runtime_directories


REQUIRED_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
logger = logging.getLogger(__name__)


@dataclass
class SourceDataResult:
    frame: pd.DataFrame | None
    source: str
    error: str | None = None
    persisted_path: Path | None = None
    resolved_start_date: str | None = None
    resolved_end_date: str | None = None
    fallback_used: bool = False
    attempted_providers: list[dict] = field(default_factory=list)
    session_status: str | None = None


def normalize_symbol(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return ""
    if normalized.endswith("^") and not normalized.startswith("^"):
        normalized = f"^{normalized[:-1]}"
    if normalized.startswith("^") and normalized.count("^") > 1:
        normalized = f"^{normalized.replace('^', '')}"
    return normalized


def provider_symbol(symbol: str) -> str:
    return normalize_symbol(symbol).replace(".", "-")


def source_search_dirs(extra_dirs: list[str | Path] | None = None) -> list[Path]:
    env_dirs = [
        Path(item.strip())
        for item in os.getenv("MARKET_AI_SOURCE_DATA_DIRS", "").split(",")
        if item.strip()
    ]
    legacy_enabled = os.getenv("MARKET_AI_DISABLE_LEGACY_SOURCE_DIR", "0").strip().lower() not in {"1", "true", "yes"}
    ordered = [SOURCE_CACHE_DIR, *env_dirs]
    if legacy_enabled:
        ordered.append(LEGACY_SOURCE_DIR)
    ordered.append(SEED_SOURCE_DIR)
    if extra_dirs:
        ordered.extend(Path(item) for item in extra_dirs if str(item).strip())

    seen: set[str] = set()
    paths: list[Path] = []
    for item in ordered:
        resolved = item if item.is_absolute() else (ROOT_DIR / item).resolve()
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        paths.append(resolved)
    return paths


def _coerce_history_frame(df: pd.DataFrame, instrument: str) -> pd.DataFrame:
    normalized = pd.DataFrame({
        "date": pd.to_datetime(df["date"], errors="coerce"),
        "open": pd.to_numeric(df.get("open"), errors="coerce"),
        "high": pd.to_numeric(df.get("high"), errors="coerce"),
        "low": pd.to_numeric(df.get("low"), errors="coerce"),
        "close": pd.to_numeric(df.get("close"), errors="coerce"),
        "volume": pd.to_numeric(df.get("volume"), errors="coerce"),
    }).dropna(subset=["date", "close"])
    normalized = normalized.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    normalized["instrument"] = instrument
    return normalized


def _read_csv_frame(csv_path: Path, instrument: str) -> pd.DataFrame:
    if not csv_path.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(csv_path)
    except pd.errors.ParserError as exc:
        detail = " ".join(str(exc).split()) or exc.__class__.__name__
        logger.warning(
            "source_data.csv_parse_failed symbol=%s path=%s detail=%s",
            instrument,
            csv_path,
            detail,
        )
        try:
            frame = pd.read_csv(csv_path, engine="python", on_bad_lines="skip")
            logger.warning(
                "source_data.csv_parse_recovered symbol=%s path=%s recovered_rows=%s",
                instrument,
                csv_path,
                len(frame.index),
            )
        except Exception as recovery_exc:
            recovery_detail = " ".join(str(recovery_exc).split()) or recovery_exc.__class__.__name__
            logger.warning(
                "source_data.csv_parse_recovery_failed symbol=%s path=%s detail=%s",
                instrument,
                csv_path,
                recovery_detail,
            )
            return pd.DataFrame()
    except Exception as exc:
        detail = " ".join(str(exc).split()) or exc.__class__.__name__
        logger.warning(
            "source_data.csv_read_failed symbol=%s path=%s detail=%s",
            instrument,
            csv_path,
            detail,
        )
        return pd.DataFrame()
    if "date" not in frame.columns:
        return pd.DataFrame()
    return _coerce_history_frame(frame, instrument)


def _filter_frame(frame: pd.DataFrame, start_date=None, end_date=None) -> pd.DataFrame:
    if frame.empty:
        return frame
    filtered = frame.copy()
    start_boundary = _window_boundary(start_date, end=False)
    end_boundary = _window_boundary(end_date, end=True)
    if start_boundary is not None:
        filtered = filtered[filtered["date"] >= start_boundary]
    if end_boundary is not None:
        filtered = filtered[filtered["date"] <= end_boundary]
    return filtered.reset_index(drop=True)


def persist_history_frame(frame: pd.DataFrame, symbol: str, target_dir: Path | None = None) -> Path | None:
    if frame is None or frame.empty:
        return None
    ensure_runtime_directories()
    destination_dir = SOURCE_CACHE_DIR if target_dir is None else Path(target_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / f"{normalize_symbol(symbol)}.csv"
    export_frame = frame.copy()
    export_frame["date"] = pd.to_datetime(export_frame["date"]).dt.strftime("%Y-%m-%d")
    export_frame[REQUIRED_COLUMNS].to_csv(destination_path, index=False)
    return destination_path


def _market_now() -> datetime:
    return datetime.now(MARKET_DATA_TIMEZONE)


def _previous_market_day(value: pd.Timestamp) -> pd.Timestamp:
    candidate = value
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _resolve_daily_session_end_date(end_date) -> tuple[str | None, str | None]:
    requested = _parsed_date(end_date)
    if requested is None:
        return None, None

    now_local = _market_now()
    today_local = pd.Timestamp(now_local.date())
    candidate = min(requested.normalize(), today_local)
    session_status = "requested"

    if requested.normalize() > today_local:
        session_status = "future_clamped"

    if candidate.weekday() >= 5:
        candidate = _previous_market_day(candidate)
        session_status = "weekend_fallback"

    session_cutoff = now_local.replace(
        hour=MARKET_DATA_SESSION_CLOSE_HOUR,
        minute=MARKET_DATA_SESSION_CLOSE_MINUTE,
        second=0,
        microsecond=0,
    ) + timedelta(minutes=max(MARKET_DATA_SESSION_CLOSE_BUFFER_MINUTES, 0))
    if candidate == today_local and now_local < session_cutoff:
        candidate = _previous_market_day(candidate - timedelta(days=1))
        session_status = "session_incomplete"

    return candidate.date().isoformat(), session_status


def _needs_backfill(frame: pd.DataFrame, start_date=None, end_date=None) -> bool:
    if frame.empty:
        return True
    start_dt = _window_boundary(start_date, end=False)
    end_dt = _window_boundary(end_date, end=True)
    min_date = frame["date"].min()
    max_date = frame["date"].max()
    if start_dt is not None and not pd.isna(start_dt) and start_dt < min_date:
        return True
    if end_dt is not None and not pd.isna(end_dt) and end_dt > max_date:
        return True
    return False


def _parsed_date(value) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    return None if parsed is None or pd.isna(parsed) else parsed


def _is_date_only_value(value) -> bool:
    if isinstance(value, str):
        return len(value.strip()) <= 10
    return not isinstance(value, datetime)


def _window_boundary(value, *, end: bool) -> pd.Timestamp | None:
    parsed = _parsed_date(value)
    if parsed is None:
        return None
    if _is_date_only_value(value):
        if end:
            return parsed.normalize() + timedelta(days=1) - pd.Timedelta(microseconds=1)
        return parsed.normalize()
    return parsed


def _shift_window_for_fallback(start_date, end_date, candidate_end_date: str) -> tuple[str | None, str]:
    start_dt = _parsed_date(start_date)
    end_dt = _parsed_date(end_date)
    candidate_end_dt = _parsed_date(candidate_end_date)
    if start_dt is None or end_dt is None or candidate_end_dt is None:
        return start_date, candidate_end_date
    if start_dt <= candidate_end_dt:
        return start_date, candidate_end_date
    window = end_dt - start_dt if end_dt >= start_dt else timedelta(days=0)
    shifted_start = candidate_end_dt - window
    return shifted_start.date().isoformat(), candidate_end_date


def _fallback_end_dates(end_date, days: int = 10) -> list[str]:
    end_dt = _parsed_date(end_date)
    if end_dt is None:
        return []
    candidates = []
    for offset in range(1, max(int(days), 1) + 1):
        candidates.append((end_dt - timedelta(days=offset)).date().isoformat())
    return candidates


def _daily_end_date_candidates(end_date, days: int = 10) -> list[tuple[str, str | None]]:
    resolved_end, session_status = _resolve_daily_session_end_date(end_date)
    candidates: list[tuple[str, str | None]] = []
    seen: set[str] = set()

    for candidate, status in [(resolved_end, session_status), *[(value, "historical_fallback") for value in _fallback_end_dates(resolved_end or end_date, days=days)]]:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        candidates.append((candidate, status))
    return candidates


def _finalize_result(
    result: SourceDataResult,
    *,
    requested_start_date=None,
    requested_end_date=None,
    original_requested_end_date=None,
    session_status: str | None = None,
) -> SourceDataResult:
    if result.frame is None or result.frame.empty:
        if result.session_status is None:
            result.session_status = session_status
        return result

    if result.resolved_start_date is None and requested_start_date not in (None, ""):
        result.resolved_start_date = str(requested_start_date)
    if result.resolved_end_date is None and requested_end_date not in (None, ""):
        result.resolved_end_date = str(requested_end_date)

    latest_row_date = pd.to_datetime(result.frame["date"].max(), errors="coerce")
    requested_end_dt = _parsed_date(original_requested_end_date if original_requested_end_date not in (None, "") else requested_end_date)
    if latest_row_date is not None and not pd.isna(latest_row_date):
        latest_end = latest_row_date.date().isoformat()
        if requested_end_dt is not None and latest_row_date.normalize() < requested_end_dt.normalize():
            result.fallback_used = True
            result.resolved_end_date = latest_end
            result.session_status = session_status or result.session_status or "historical_fallback"
        elif result.resolved_end_date is None:
            result.resolved_end_date = latest_end

    if result.session_status is None:
        result.session_status = session_status
    return result


def _build_source_unavailable_result(
    instrument: str,
    source_name: str,
    *,
    remote_error: str | None,
    checked_locations: list[str],
    attempted_providers: list[dict] | None = None,
    start_date=None,
    end_date=None,
) -> SourceDataResult:
    public_detail = remote_error or "no local history and no configured market-data provider returned completed bars"
    logger.warning(
        "source_data.unavailable symbol=%s start=%s end=%s detail=%s checked_locations=%s",
        instrument,
        start_date,
        end_date,
        public_detail,
        checked_locations,
    )
    return SourceDataResult(
        frame=None,
        source=source_name,
        error=f"Source data unavailable for {instrument}: {public_detail}.",
        resolved_start_date=None if start_date in (None, "") else str(start_date),
        resolved_end_date=None if end_date in (None, "") else str(end_date),
        attempted_providers=list(attempted_providers or []),
    )


def _load_symbol_source_data_once(
    symbol: str,
    start_date=None,
    end_date=None,
    *,
    interval: str = "1d",
    persist_on_fetch: bool = True,
    allow_network: bool = True,
    extra_dirs: list[str | Path] | None = None,
) -> SourceDataResult:
    instrument = normalize_symbol(symbol)
    normalized_interval = str(interval or "1d").strip().lower()
    ensure_runtime_directories()

    combined = pd.DataFrame()
    source_name = "unavailable"
    remote_error = None
    attempted_providers: list[dict] = []

    for directory in source_search_dirs(extra_dirs=extra_dirs):
        csv_path = directory / f"{instrument}.csv"
        local_frame = _read_csv_frame(csv_path, instrument)
        if local_frame.empty:
            continue
        combined = local_frame if combined.empty else pd.concat([combined, local_frame], ignore_index=True)
        combined = _coerce_history_frame(combined, instrument)
        source_name = f"local:{directory.name}"
        if not _needs_backfill(combined, start_date, end_date):
            filtered = _filter_frame(combined, start_date, end_date)
            if not filtered.empty:
                return SourceDataResult(
                    frame=filtered,
                    source=source_name,
                    resolved_start_date=None if start_date in (None, "") else str(start_date),
                    resolved_end_date=None if end_date in (None, "") else str(end_date),
                )

    if allow_network:
        provider_result = fetch_history_from_providers(instrument, start_date=start_date, end_date=end_date, interval=interval)
        attempted_providers = list(provider_result.attempted_providers or [])
        remote_error = provider_result.error
        fetched = provider_result.frame if provider_result.frame is not None else pd.DataFrame()
        if not fetched.empty:
            combined = fetched if combined.empty else pd.concat([combined, fetched], ignore_index=True)
            combined = _coerce_history_frame(combined, instrument)
            source_name = provider_result.provider or source_name
            persisted_path = persist_history_frame(combined, instrument) if persist_on_fetch and normalized_interval == "1d" else None
            filtered = _filter_frame(combined, start_date, end_date)
            if not filtered.empty:
                return SourceDataResult(
                    frame=filtered,
                    source=source_name,
                    persisted_path=persisted_path,
                    resolved_start_date=None if start_date in (None, "") else str(start_date),
                    resolved_end_date=None if end_date in (None, "") else str(end_date),
                    attempted_providers=attempted_providers,
                )

    filtered = _filter_frame(combined, start_date, end_date)
    if not filtered.empty:
        return SourceDataResult(
            frame=filtered,
            source=source_name,
            resolved_start_date=None if start_date in (None, "") else str(start_date),
            resolved_end_date=None if end_date in (None, "") else str(end_date),
            attempted_providers=attempted_providers,
        )

    checked_locations = [str(directory / f"{instrument}.csv") for directory in source_search_dirs(extra_dirs=extra_dirs)]
    return _build_source_unavailable_result(
        instrument,
        source_name,
        remote_error=remote_error,
        checked_locations=checked_locations,
        attempted_providers=attempted_providers,
        start_date=start_date,
        end_date=end_date,
    )


def load_symbol_source_data(
    symbol: str,
    start_date=None,
    end_date=None,
    *,
    interval: str = "1d",
    persist_on_fetch: bool = True,
    allow_network: bool = True,
    extra_dirs: list[str | Path] | None = None,
) -> SourceDataResult:
    normalized_interval = str(interval or "1d").strip().lower()
    end_dt = _parsed_date(end_date)
    if normalized_interval != "1d" or end_dt is None:
        result = _load_symbol_source_data_once(
            symbol,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            persist_on_fetch=persist_on_fetch,
            allow_network=allow_network,
            extra_dirs=extra_dirs,
        )
        return _finalize_result(
            result,
            requested_start_date=start_date,
            requested_end_date=end_date,
            original_requested_end_date=end_date,
        )

    last_result: SourceDataResult | None = None
    last_session_status = None
    for candidate_end, session_status in _daily_end_date_candidates(end_date, days=10):
        fallback_start, fallback_end = _shift_window_for_fallback(start_date, end_date, candidate_end)
        last_session_status = session_status
        result = _load_symbol_source_data_once(
            symbol,
            start_date=fallback_start,
            end_date=fallback_end,
            interval=interval,
            persist_on_fetch=persist_on_fetch,
            allow_network=allow_network,
            extra_dirs=extra_dirs,
        )
        finalized = _finalize_result(
            result,
            requested_start_date=fallback_start,
            requested_end_date=fallback_end,
            original_requested_end_date=end_date,
            session_status=session_status,
        )
        last_result = finalized
        if finalized.frame is not None and not finalized.frame.empty:
            return finalized

    if last_result is not None:
        return _finalize_result(
            last_result,
            requested_start_date=start_date,
            requested_end_date=end_date,
            original_requested_end_date=end_date,
            session_status=last_session_status,
        )

    result = _load_symbol_source_data_once(
        symbol,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        persist_on_fetch=persist_on_fetch,
        allow_network=allow_network,
        extra_dirs=extra_dirs,
    )
    return _finalize_result(
        result,
        requested_start_date=start_date,
        requested_end_date=end_date,
        original_requested_end_date=end_date,
    )


def bootstrap_source_cache(symbols: list[str], start_date=None, end_date=None, *, allow_network: bool = True) -> dict:
    ensure_runtime_directories()
    items = []
    for symbol in symbols:
        result = load_symbol_source_data(
            symbol,
            start_date=start_date,
            end_date=end_date,
            allow_network=allow_network,
            persist_on_fetch=True,
        )
        items.append({
            "symbol": normalize_symbol(symbol),
            "source": result.source,
            "rows": 0 if result.frame is None else int(len(result.frame)),
            "persisted_path": None if result.persisted_path is None else str(result.persisted_path),
            "error": result.error,
            "resolved_start_date": result.resolved_start_date,
            "resolved_end_date": result.resolved_end_date,
            "fallback_used": result.fallback_used,
            "session_status": result.session_status,
            "attempted_providers": result.attempted_providers,
        })
    return {
        "items": items,
        "success_count": sum(1 for item in items if not item["error"]),
        "error_count": sum(1 for item in items if item["error"]),
        "cache_dir": str(SOURCE_CACHE_DIR),
    }
