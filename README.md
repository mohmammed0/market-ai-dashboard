# Market AI Dashboard

Modern broker-managed US equities trading platform with a strict legacy boundary.

## Operating Model

The live product is the modern stack under `backend/`, `frontend/`, `core/`, and `scripts/`.

It is designed to:
- analyze and rank US equities
- understand session state and pre-open readiness
- make portfolio-level decisions through the portfolio brain
- route execution through an external broker-managed account
- expose diagnostics and explainability through `/brain` and `/diagnostics/auto-trading`

## Architecture Boundary

### Modern live system
- `backend/`
  FastAPI APIs, automation, execution orchestration, broker integration, diagnostics, readiness, and runtime settings.
- `frontend/`
  React operator UI.
- `core/`
  shared service layer and explicit adapters used by the modern stack.
- `scripts/`
  deployment and operational helpers for the modern stack.

### Legacy layer
- `legacy/engines/`
  legacy analysis, technical, ranking, backtest, news, ML, and live-market engines.
- `legacy/ui/`
  legacy desktop UI.
- `legacy/support/`
  legacy SQLite-era support modules and data helpers.
- `legacy/scripts/`
  old training, worker, optimizer, and maintenance scripts.

The live product must not import legacy modules directly. Any legacy dependency used by the modern stack must pass through explicit adapters in `core/legacy_adapters/`.

## Live Stack

Production services:
- `backend`
- `frontend`
- `automation`
- `db`
- `redis`
- `ollama`

Execution/account/order truth:
- external broker API only
- broker-managed paper/live distinction exists only at the broker environment layer
- internal paper simulation is not an active execution path

## Important Modern Modules

- `backend/app/bootstrap/`
  app factory, router registration, startup/runtime wiring, and HTTP middleware setup.
- `backend/app/services/automation_hub.py`
  trading-cycle orchestration and readiness flow.
- `backend/app/services/portfolio_brain.py`
  portfolio-level decision engine.
- `backend/app/application/execution/service.py`
  broker submission and execution lifecycle logic.
- `backend/app/services/market_session_intelligence.py`
  normalized session model.
- `backend/app/services/analysis_engines.py`
  engine status and contribution visibility.
- `backend/app/services/kronos_intelligence.py`
  Kronos cache/runtime layer.
- `backend/app/services/auto_trading_diagnostics.py`
  cycle artifacts and explainability.

## Adapter Boundary

Modern code reaches legacy logic only through:
- `core/legacy_adapters/analysis.py`
- `core/legacy_adapters/technical.py`
- `core/legacy_adapters/ranking.py`
- `core/legacy_adapters/backtest.py`
- `core/legacy_adapters/news.py`
- `core/legacy_adapters/live_market.py`

## Key Endpoints

- `/health`
- `/ready`
- `/api/portfolio-brain/latest`
- `/api/diagnostics/auto-trading/latest`
- `/api/market-session/status`
- `/api/market-readiness/latest`
- `/api/analysis-engines/status`
- `/api/kronos/status`
- `/api/broker/status`
- `/api/trading/portfolio`


## Configuration Notes

- Default admin credentials can be set via `MARKET_AI_AUTH_DEFAULT_USERNAME` and `MARKET_AI_AUTH_DEFAULT_PASSWORD`.
  When provided, the password hash is persisted in runtime settings (`auth.default_password_hash`) for restarts.
- CORS can be tightened in production with `MARKET_AI_ALLOWED_METHODS` and `MARKET_AI_ALLOWED_HEADERS`.
- Shared date defaults live in `core/date_defaults.py` and are re-exported for backend usage.

## Development Rules

- Preserve broker-managed execution as the single source of execution truth.
- Do not reintroduce internal paper trading.
- Do not let modern modules import `legacy/` directly except through adapters.
- Prefer modular patches over rewrites.
- Keep diagnostics truthful.
