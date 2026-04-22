from __future__ import annotations

from core.date_defaults import indicator_warmup_start_date_iso, recent_end_date_iso, recent_start_date_iso
from core.legacy_adapters.analysis import run_analysis as engine_run_analysis
from core.signal_intelligence import enhance_signal


def _trim_chart_data(chart_data: dict, visible_start_date: str, visible_end_date: str) -> dict:
    if not isinstance(chart_data, dict):
        return chart_data
    dates = list(chart_data.get("dates") or [])
    if not dates:
        return chart_data
    keep_indexes = [
        index
        for index, value in enumerate(dates)
        if visible_start_date <= str(value)[:10] <= visible_end_date
    ]
    if not keep_indexes:
        return chart_data
    trimmed = {"dates": [dates[index] for index in keep_indexes]}
    for key, values in chart_data.items():
        if key == "dates":
            continue
        if isinstance(values, list):
            trimmed[key] = [values[index] for index in keep_indexes if index < len(values)]
        else:
            trimmed[key] = values
    return trimmed


def _trim_table_data(table_data: list[dict], visible_start_date: str, visible_end_date: str) -> list[dict]:
    if not isinstance(table_data, list):
        return table_data
    trimmed = [
        row
        for row in table_data
        if visible_start_date <= str(row.get("date") or "")[:10] <= visible_end_date
    ]
    return trimmed or table_data


def analyze_symbol(instrument="AAPL", start_date=None, end_date=None):
    requested_start_date = start_date or recent_start_date_iso()
    requested_end_date = end_date or recent_end_date_iso()
    result = engine_run_analysis(
        instrument=instrument,
        start_date=indicator_warmup_start_date_iso(requested_start_date),
        end_date=requested_end_date,
    )
    if isinstance(result, dict) and "error" not in result:
        result["chart_data"] = _trim_chart_data(result.get("chart_data") or {}, requested_start_date, requested_end_date)
        result["table_data"] = _trim_table_data(result.get("table_data") or [], requested_start_date, requested_end_date)
        result["start_date"] = requested_start_date
        result["end_date"] = requested_end_date
    result = enhance_signal(result)
    return result
