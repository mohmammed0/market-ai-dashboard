# AGENTS.md

## Project Purpose
- Build and maintain a production-minded Market AI platform while preserving the existing working logic for analysis, technical scoring, ranking, optimizer results, backtesting, and the current PySide desktop app.
- Treat the root Python engines as the source of truth and extend the platform through `core/`, `backend/`, and `frontend/` with focused modular patches.

## Important Directories
- `analysis_engine.py`, `technical_engine.py`, `ranking_engine.py`, `backtest_engine.py`
  Existing business logic and signal pipeline. Preserve these unless a change is truly required.
- `main_ui.py`
  Existing desktop UI. Keep this working.
- `core/`
  Reusable wrappers around the existing engines.
- `backend/`
  FastAPI, SQLAlchemy, Alembic-ready backend scaffold.
- `frontend/`
  Vite web app and reusable frontend components.
- `leaders_optimizer_best.csv`
  Real optimizer-backed `best_setup` source. Do not break this integration.
- `.agents/skills/`
  Repo-local workflow skills for consistent future implementation.

## Python Environment
```powershell
.\venv\Scripts\Activate.ps1
```

## Run Commands
- Desktop UI:

```powershell
.\venv\Scripts\python.exe .\main_ui.py
```

- Backend:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

- Leaders optimizer:

```powershell
.\venv\Scripts\python.exe .\batch_optimize_leaders_light.py
```

- Frontend:

```powershell
Set-Location .\frontend
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

- Production-style frontend preview:

```powershell
Set-Location .\frontend
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run build
npm run preview:host
```

## Compile / Test Commands
- Core and backend syntax check:

```powershell
.\venv\Scripts\python.exe -m py_compile .\analysis_engine.py .\technical_engine.py .\ranking_engine.py .\backtest_engine.py .\core\analysis_service.py .\backend\app\main.py
```

- Existing Python smoke checks:

```powershell
.\venv\Scripts\python.exe -m pytest .\backend\tests\test_engines.py
.\venv\Scripts\python.exe -m pytest .\backend\tests\test_background_jobs.py
```

- Frontend Storybook:

```powershell
Set-Location .\frontend
npm run storybook
```

- Frontend Playwright:

```powershell
Set-Location .\frontend
npm run test:e2e
```

## Durable Repo Rules
- Do not rewrite the project from scratch.
- Preserve desktop app behavior and keep `main_ui.py` working.
- Preserve current analysis, technical, ranking, optimizer, and backtest logic.
- Preserve `ranking_engine.py` optimizer-based `best_setup` sourced from `leaders_optimizer_best.csv` when available.
- Keep `setup_type` as the heuristic ranking label.
- Prefer minimal modular patches over broad architecture churn.
- Every frontend page should have loading, error, and empty states.
- Backend should degrade gracefully when external news fails; partial analysis is better than a hard failure.
- Keep environment variables and startup defaults local-first and explicit through `.env.example` and `backend/app/config.py`.
- Reuse existing engines/services rather than duplicating logic.
