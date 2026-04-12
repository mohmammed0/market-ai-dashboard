from analysis_engine import run_analysis as engine_run_analysis
from core.signal_intelligence import enhance_signal


def analyze_symbol(instrument="AAPL", start_date="2024-01-01", end_date="2026-04-02"):
    result = engine_run_analysis(
        instrument=instrument,
        start_date=start_date,
        end_date=end_date,
    )
    result = enhance_signal(result)
    return result
