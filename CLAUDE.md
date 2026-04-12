# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Python environment
```powershell
.\venv\Scripts\Activate.ps1
```

### Run servers
```powershell
# Backend (FastAPI)
.\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend (Vite dev server)
cd frontend && $env:VITE_API_BASE_URL="http://127.0.0.1:8000" && npm run dev

# Desktop app (PySide)
.\venv\Scripts\python.exe .\main_ui.py

# Leaders optimizer
.\venv\Scripts\python.exe .\batch_optimize_leaders_light.py
```

### Test / syntax check
```powershell
# Python syntax check (run after any engine/backend change)
.\venv\Scripts\python.exe -m py_compile .\analysis_engine.py .\technical_engine.py .\ranking_engine.py .\backtest_engine.py .\core\analysis_service.py .\backend\app\main.py

# Python smoke tests
.\venv\Scripts\python.exe .\_test_analysis.py
.\venv\Scripts\python.exe .\_test_full_analysis.py

# Frontend component stories
cd frontend && npm run storybook

# Frontend end-to-end
cd frontend && npm run test:e2e
```

### Frontend build
```powershell
cd frontend && $env:VITE_API_BASE_URL="http://127.0.0.1:8000" && npm run build && npm run preview:host
```

## Architecture

### Three-layer structure
The project has three coexisting interfaces sharing the same Python engines and SQLite database (`data/market_ai.db`):

1. **Root engines** — `analysis_engine.py`, `technical_engine.py`, `ranking_engine.py`, `backtest_engine.py`, `live_market_engine.py`, `news_engine.py`. These are the source of truth. Do not rewrite them.
2. **`core/`** — thin service wrappers (`analysis_service.py`, `ranking_service.py`, `backtest_service.py`, etc.) that expose the engines to the backend and desktop app without duplicating logic.
3. **`backend/app/`** — FastAPI application mounted at `http://localhost:8000`. `main.py` wires 30+ routers. Services live in `backend/app/services/`, domain contracts in `backend/app/domain/`, data access in `backend/app/repositories/`.

**Frontend** (`frontend/src/`) is a Vite + React 18 SPA. All pages are lazy-loaded through `App.jsx` via `AppShell`. The UI is in Arabic (RTL). API calls are organized under `frontend/src/api/` by domain.

### Key data flows
- **Ranking**: `ranking_engine.py` reads `leaders_optimizer_best.csv` to set `best_setup` (optimizer-backed). `setup_type` is the separate heuristic label. Both must be preserved.
- **Scheduling**: `APScheduler` is initialized conditionally based on `SERVER_ROLE` env var (`api`, `automation`, or `all`). `backend/app/services/scheduler_runtime.py` manages job lifecycle.
- **ML/DL training**: Runs in a subprocess (not in-process) to avoid blocking the API. Training artifacts land in `model_artifacts/`.
- **Market data**: Local-first with yfinance as fallback. `backend/app/services/market_data.py` owns this.
- **Broker**: Alpaca integration lives in `backend/app/services/broker/`. Runtime credentials are stored in the database (not `.env`).

### Environment & config
- `backend/app/config.py` is the single source for all ~50 env vars. Check it before adding new settings.
- `.env.example` / `.env.production.example` document local vs production defaults.
- Credentials entered via the Settings UI are persisted to the DB via `runtime_settings.py`, not `.env`.

### Database
- SQLite at `data/market_ai.db`. Alembic manages migrations (`backend/alembic/versions/`).
- Run migrations: `.\venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head`

## Durable Rules

- **Do not rewrite** root engines or `main_ui.py` unless a change is strictly necessary.
- **Reuse, don't duplicate**: extend through `core/` wrappers and backend services.
- **Preserve optimizer integration**: `ranking_engine.py` `best_setup` must come from `leaders_optimizer_best.csv`.
- **Minimal patches**: prefer focused changes over broad refactors.
- **Every frontend page** needs loading, error, and empty states.
- **Backend must degrade gracefully** when external news/data sources fail — partial results beat hard errors.
- **Workflow skills** in `.agents/skills/` (backend-route, frontend-page, market-analyze, ranking-workflow, release-check) document the expected implementation patterns for new features.
