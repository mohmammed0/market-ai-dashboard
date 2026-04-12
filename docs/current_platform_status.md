# Current Platform Status

## Working Now
- Desktop PySide app remains intact and uses the existing engines directly.
- Backend FastAPI scaffold is live and reuses `core` wrappers over the current engines.
- Frontend pages now have real connections for:
  - Dashboard
  - Analyze
  - Scan
  - Ranking
  - Backtest
  - Paper Trading
  - Model Lab
  - Live Market
  - Settings
- `best_setup` continues to come from `leaders_optimizer_best.csv` when available.
- `setup_type` remains the heuristic label from the ranking engine.
- Frontend now has a reusable component layer, centralized API helper, form schemas, and product-style pages.
- Backend now includes local-first market data loading, ML/DL training routes, model registry endpoints, intelligence inference, scheduler status, and a live snapshot path.
- Backend now includes local-first paper trading, alert history, signal history, and simulated trade persistence.
- Backend now includes a broker abstraction layer with a safe Alpaca-ready read-only path for account, positions, and orders.
- Backend is now mid-transition to a cleaner domain-oriented architecture with:
  - split model modules
  - typed execution/portfolio/broker/model-lifecycle contracts
  - repository-backed persistence boundaries
  - additive `/api/execution/*` and `/api/model-lifecycle/*` route families
  - Alembic-based migration discipline with legacy bootstrap compatibility

## Resilience Improvement
- Backend analysis now degrades gracefully if external news fetch fails.
- Analyze, Scan, and Ranking can return partial results instead of failing the full request.
- Backend now includes a small cached dashboard summary endpoint and an in-memory cache abstraction that is ready for future Redis replacement.
- Market-data refresh and quote snapshot jobs are scheduler-ready and degrade to local CSV data when remote sources are unavailable.
- Broker status is additive, paper-first, and disabled by default unless explicitly configured.
- Backend now includes a readiness endpoint and structured logging helpers for automation, broker, and execution-domain diagnostics.

## Next Phase
- Complete the remaining route migrations so older namespaces become thin compatibility adapters only.
- Move more direct ORM access out of legacy services like journal/strategy lab into repositories or domain persistence services.
- Replace the legacy bootstrap fallback with migration-only startup once existing developer databases have been normalized.
- Add formal reconciliation flows between internal paper, broker paper, and future live portfolio sources before any execution expansion.
