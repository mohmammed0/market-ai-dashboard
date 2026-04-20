# Market AI Dashboard

Production-minded autonomous trading platform for US equities.

This repository contains the live trading stack currently deployed at `/opt/market-ai-dashboard`. It combines market/session intelligence, portfolio decisioning, broker-managed execution, diagnostics, model services, and a retained desktop/engine layer from the original project.

## What The System Does

The platform is designed to behave like an autonomous trading desk rather than a simple signal bot.

It can:
- analyze US equities across a ranked universe
- understand market session state and pre-open readiness
- combine classic, ranking, ML, DL, and Kronos signals
- make portfolio-level decisions such as `OPEN_LONG`, `ADD_LONG`, `HOLD`, `REDUCE_LONG`, `EXIT_LONG`, `QUEUE_FOR_OPEN`, `WAIT_FOR_CONFIRMATION`, and `NO_ACTION`
- route orders through an external broker-managed paper account
- reconcile broker lifecycle states and expose them in diagnostics
- surface explainability through `/brain` and `/diagnostics/auto-trading`

## Current Operating Model

- Asset scope: US equities only
- Core universe: top liquid large-cap names
- Tactical sleeve: listed small caps with tighter constraints
- Execution truth: external broker-managed account
- Internal paper simulator: disabled for active execution truth
- Scheduling model: delegated to the `automation` service

## Live Stack

The production compose stack runs these core services:
- `backend`: FastAPI application and API surface
- `frontend`: operator dashboard UI
- `automation`: delegated scheduler and trading-cycle worker
- `db`: PostgreSQL state store
- `redis`: shared runtime/cache/state channel
- `ollama`: local model runtime support

## Repository Layout

### Root engines retained from the original project
- `analysis_engine.py`
- `technical_engine.py`
- `ranking_engine.py`
- `backtest_engine.py`
- `main_ui.py`

These are preserved because they still provide important analysis and desktop-era logic.

### Core active application areas
- `backend/`
  - FastAPI app, broker integration, orchestration, diagnostics, runtime settings, and APIs
- `frontend/`
  - Vite/React trading desk UI
- `core/`
  - reusable wrappers around legacy engines and market data logic
- `docs/`
  - operational and reference docs
- `scripts/`
  - stack and deployment helper scripts

## Important Backend Modules

- `backend/app/main.py`
  - API entrypoint and router registration
- `backend/app/services/automation_hub.py`
  - automated trading cycles, readiness, and orchestration control
- `backend/app/services/portfolio_brain.py`
  - autonomous trader judgment and portfolio-level decisioning
- `backend/app/application/execution/service.py`
  - execution path and broker submission state handling
- `backend/app/services/market_session_intelligence.py`
  - normalized market session model
- `backend/app/services/market_readiness.py`
  - readiness artifact assembly
- `backend/app/services/analysis_engines.py`
  - engine readiness and contribution visibility
- `backend/app/services/kronos_intelligence.py`
  - Kronos runtime, cache, and signal normalization
- `backend/app/services/auto_trading_diagnostics.py`
  - cycle artifacts, explainability, summaries, and row-level diagnostics

## Main UI Pages

Defined through `frontend/src/App.jsx`, including:
- `/brain`
- `/diagnostics/auto-trading`
- `/broker`
- `/settings`
- `/live-market`
- `/ai-news`
- `/ranking`

## Broker Model

The platform no longer treats an internal simulated paper engine as active truth.

Current truth model:
- broker account source: external broker API
- position source: broker
- order source: broker
- execution source: broker-managed
- environment distinction: external paper vs external live

This keeps trading logic consistent between paper and live at the broker layer.

## Development Notes

- Preserve the root engines unless there is a strong reason to change them.
- Prefer focused patches over rewrites.
- Keep diagnostics truthful.
- Keep broker-managed execution as the single active execution/account truth path.
- Do not reintroduce an internal paper trading engine.

## Typical Production Commands

### Backend
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm run build
npm run preview:host
```

### Production compose
```bash
docker compose --env-file .env.production -f docker-compose.yml up -d
```

## Key Operational Endpoints

- `/health`
- `/ready`
- `/api/portfolio-brain/latest`
- `/api/diagnostics/auto-trading/latest`
- `/api/market-session/status`
- `/api/market-readiness/latest`
- `/api/analysis-engines/status`
- `/api/kronos/status`
- `/api/broker/status`

## Repository Cleanup Policy

Temporary server-side backup artifacts are intentionally not tracked.

Examples:
- `.backup/`
- `.codex_backups/`
- `*.bak.*`

These should stay out of Git unless there is a very specific operational reason to preserve them elsewhere.
