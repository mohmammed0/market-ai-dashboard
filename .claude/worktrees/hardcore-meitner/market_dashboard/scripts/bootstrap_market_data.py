#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.source_data import bootstrap_source_cache


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap cached market source data for common symbols.")
    parser.add_argument("--symbols", default="AAPL,MSFT,NVDA,SPY", help="Comma-separated symbol list.")
    parser.add_argument("--days", type=int, default=400, help="How many calendar days of history to request.")
    parser.add_argument("--start-date", default="", help="Optional explicit start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", default="", help="Optional explicit end date in YYYY-MM-DD format.")
    parser.add_argument("--no-network", action="store_true", help="Do not fetch missing data from yfinance.")
    args = parser.parse_args()

    symbols = [item.strip().upper() for item in str(args.symbols or "").split(",") if item.strip()]
    end_date = args.end_date or date.today().isoformat()
    start_date = args.start_date or (date.today() - timedelta(days=max(args.days, 30))).isoformat()
    result = bootstrap_source_cache(
        symbols,
        start_date=start_date,
        end_date=end_date,
        allow_network=not args.no_network,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
