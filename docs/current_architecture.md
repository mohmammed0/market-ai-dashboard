# Current Architecture

## Backend
- FastAPI routes live under `backend/app/api/routes`.
- Route handlers now sit on top of clearer bounded contexts:
  - `backend/app/application/` for orchestration
  - `backend/app/domain/` for typed internal contracts
  - `backend/app/repositories/` for persistence boundaries
  - `backend/app/models/` split by domain instead of one catch-all model file
- Compatibility adapters still exist so older route contracts remain usable while ownership shifts toward the new domains.
- `core/` wraps the existing root engines so business logic stays in one place.
- `backend/app/db/migrations.py` and Alembic now provide the primary schema migration path, with legacy bootstrap support to keep local developer databases usable during the transition.
- A small in-memory cache abstraction in `backend/app/services/cache.py` is the current hook point for future Redis integration.
- `backend/app/services/market_data.py` now provides a local-first market data layer with CSV + `yfinance` fallback, quote snapshots, and persistence hooks.
- `backend/app/services/broker/` now provides a provider boundary for external broker integrations, with Alpaca implemented as a read-only provider behind feature flags and safe defaults.
- `backend/app/services/features.py` centralizes advanced feature engineering on top of the existing technical indicator stack.
- `backend/app/services/ml_lab.py` and `backend/app/services/dl_lab.py` provide baseline ML and GRU-based DL training/inference with local artifact storage.
- `backend/app/services/ensemble.py` combines classic, ML, DL, and regime context into an inspectable ensemble output.
- `backend/app/services/scheduler_runtime.py` adds APScheduler-ready periodic refresh hooks for history and quotes.
- The execution flow now has typed signal, trade-intent, position, and audit-event contracts, plus repositories and application services that reduce the overload previously concentrated in `paper_trading.py`.
- Canonical portfolio exposure now aggregates internal paper and broker state through a portfolio application service instead of assuming simulator positions are the only portfolio source.

## Frontend
- Vite + React web app lives under `frontend/`.
- Shared API access now routes through `frontend/src/api/` domain modules, with `frontend/src/lib/api.js` kept as a compatibility barrel during the transition.
- Shared page/form schemas live in `frontend/src/lib/forms.js`.
- Reusable product UI components live under `frontend/src/components/ui`.
- Shared async resource loading now has a reusable hook at `frontend/src/hooks/useAsyncResource.js` for pages that repeatedly fetch operational state.
- Current UI foundations include migration-ready Tailwind config, Storybook scaffold, Playwright scaffold, TanStack Table, React Hook Form, Zod, Motion, and ECharts integration points.
- Web UI now includes Model Lab, Live Market, and Paper Trading pages layered onto the existing shell, plus smarter Analyze, Dashboard, Backtest, and Settings views.
- Web UI now includes a minimal Broker page so operational account status can surface without mixing broker paper accounts with the internal simulator.

## Desktop
- `main_ui.py` remains intact and continues to use the current Python engine stack directly.
- Desktop behavior should remain preserved while backend/frontend continue to mature toward parity.
