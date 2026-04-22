from legacy.engines.analysis_engine import run_analysis


def analyze_stock(symbol: str, start_date: str | None = None, end_date: str | None = None, **kwargs):
    return run_analysis(instrument=symbol, start_date=start_date, end_date=end_date, **kwargs)


__all__ = ["analyze_stock", "run_analysis"]
