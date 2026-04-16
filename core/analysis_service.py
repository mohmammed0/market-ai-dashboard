from analysis_engine import run_analysis as engine_run_analysis
from core.signal_intelligence import enhance_signal
from backend.app.core.date_defaults import recent_end_date_iso, recent_start_date_iso


def analyze_symbol(instrument="AAPL", start_date=None, end_date=None):
    result = engine_run_analysis(
        instrument=instrument,
        start_date=start_date or recent_start_date_iso(),
        end_date=end_date or recent_end_date_iso(),
    )
    result = enhance_signal(result)
    return result
