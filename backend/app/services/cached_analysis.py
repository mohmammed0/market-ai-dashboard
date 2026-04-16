from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from backend.app.services import get_cache
from core.analysis_service import analyze_symbol
from core.ranking_service import rank_analysis


def _cache():
    return get_cache()


def get_base_analysis_result(instrument: str, start_date: str, end_date: str, ttl_seconds: int = 300) -> dict:
    symbol = str(instrument or "").strip().upper()
    cache_key = f"analysis:base:{symbol}:{start_date}:{end_date}"

    def factory():
        return analyze_symbol(instrument=symbol, start_date=start_date, end_date=end_date)

    return _cache().get_or_set(cache_key, factory, ttl_seconds=ttl_seconds)


def get_base_analysis_results_batch(
    symbols: list[str],
    start_date: str,
    end_date: str,
    *,
    ttl_seconds: int = 300,
    max_workers: int = 4,
) -> list[dict]:
    prepared = [str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()]
    if not prepared:
        return []

    def worker(symbol: str) -> dict:
        try:
            return get_base_analysis_result(symbol, start_date, end_date, ttl_seconds=ttl_seconds)
        except Exception as exc:
            return {"instrument": symbol, "signal": "ERROR", "error": str(exc)}

    worker_count = max(1, min(int(max_workers or 1), len(prepared), 8))
    if worker_count == 1:
        return [worker(symbol) for symbol in prepared]

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return list(executor.map(worker, prepared))


def get_ranked_analysis_result(
    instrument: str,
    start_date: str,
    end_date: str,
    *,
    ttl_seconds: int = 300,
    include_ml: bool = True,
    include_dl: bool = False,
) -> dict:
    symbol = str(instrument or "").strip().upper()
    cache_key = f"analysis:ranked:{symbol}:{start_date}:{end_date}:{int(include_ml)}:{int(include_dl)}"

    def factory():
        from backend.app.services.dl_lab import infer_sequence
        from backend.app.services.ensemble import build_ensemble_output
        from backend.app.services.ml_lab import infer_latest

        result = get_base_analysis_result(symbol, start_date, end_date, ttl_seconds=ttl_seconds)
        if "error" in result:
            return result
        ranked = rank_analysis(result)
        ml_output = None
        dl_output = None
        tasks = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            if include_ml:
                tasks.append(("ml", executor.submit(infer_latest, symbol, start_date, end_date)))
            if include_dl:
                tasks.append(("dl", executor.submit(infer_sequence, symbol, start_date, end_date)))
            for label, future in tasks:
                if label == "ml":
                    ml_output = future.result()
                if label == "dl":
                    dl_output = future.result()
        ranked["ml_output"] = ml_output
        ranked["dl_output"] = dl_output
        ranked["ensemble_output"] = build_ensemble_output(ranked, ml_output, dl_output) if include_ml else None
        return ranked

    return _cache().get_or_set(cache_key, factory, ttl_seconds=ttl_seconds)
