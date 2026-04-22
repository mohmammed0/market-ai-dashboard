# AGENTS.md

Canonical architectural intent for this repository.

## Project Purpose
- Maintain the modern production stack as the only live product path.
- Keep the legacy engine/UI layer isolated behind explicit adapters.
- Improve maintainability through modular patches, not rewrites.

## Architecture Rules
- The live product is `backend/`, `frontend/`, `core/`, and `scripts/`.
- Legacy code lives under `legacy/`.
- Modern code must not import `legacy/` directly except through `core/legacy_adapters/`.
- Preserve broker-managed execution as the only active execution/account truth path.
- Do not reintroduce internal paper simulation.

## Important Directories
- `backend/`
  FastAPI application, broker integration, diagnostics, runtime settings, execution orchestration.
- `frontend/`
  React/Vite operator UI.
- `core/`
  shared services and explicit adapters to legacy logic.
- `legacy/`
  isolated old engines, desktop UI, support modules, and one-off scripts.
- `leaders_optimizer_best.csv`
  optimizer-backed ranking input that legacy ranking logic still depends on.

## Python Environment
```powershell
.\venv\Scripts\Activate.ps1
```

## Run Commands
- Backend:
```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```
- Frontend:
```powershell
Set-Location .\frontend
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```
- Legacy desktop UI:
```powershell
.\venv\Scripts\python.exe .\legacy\ui\main_ui.py
```
- Legacy optimizer helper:
```powershell
.\venv\Scripts\python.exe .\legacy\scripts\batch_optimize_leaders_light.py
```

## Compile / Test Commands
- Core and backend syntax check:
```powershell
.\venv\Scripts\python.exe -m py_compile .\legacy\engines\analysis_engine.py .\legacy\engines\technical_engine.py .\legacy\engines\ranking_engine.py .\legacy\engines\backtest_engine.py .\core\analysis_service.py .\backend\app\main.py
```
- Existing Python smoke checks:
```powershell
.\venv\Scripts\python.exe -m pytest .\backend\tests\test_engines.py
.\venv\Scripts\python.exe -m pytest .\backend\tests\test_background_jobs.py
```
- Frontend end-to-end:
```powershell
Set-Location .\frontend
npm run test:e2e
```

## Durable Repo Rules
- Do not rewrite the project from scratch.
- Keep modern live code separate from `legacy/`.
- Preserve optimizer-backed ranking behavior from `leaders_optimizer_best.csv`.
- Prefer focused modular patches over broad architecture churn.
- Every frontend page must keep loading, error, and empty states.
- Backend must degrade gracefully when external data/news sources fail.
- Keep only safe environment templates in Git; runtime secrets stay outside Git.
