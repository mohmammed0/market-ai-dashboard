# CLAUDE.md

Repository guidance.

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

# Legacy desktop app
.\venv\Scripts\python.exe .\legacy\ui\main_ui.py

# Legacy optimizer helper
.\venv\Scripts\python.exe .\legacy\scripts\batch_optimize_leaders_light.py
```

### Test / syntax check
```powershell
.\venv\Scripts\python.exe -m py_compile .\legacy\engines\analysis_engine.py .\legacy\engines\technical_engine.py .\legacy\engines\ranking_engine.py .\legacy\engines\backtest_engine.py .\core\analysis_service.py .\backend\app\main.py
```

## Architecture

### Modern live system
1. `backend/` — FastAPI APIs, automation, execution, broker integration, diagnostics, runtime settings.
2. `frontend/` — React/Vite operator UI.
3. `core/` — thin service layer plus explicit adapters for any legacy dependency.

### Legacy boundary
- `legacy/engines/` — preserved analysis/technical/ranking/backtest/news/ML engines.
- `legacy/ui/` — preserved desktop UI.
- `legacy/support/` — old SQLite-era helpers and support modules.
- `legacy/scripts/` — old workers, optimizers, and one-off scripts.

Modern code must not import `legacy/` directly except through `core/legacy_adapters/`.

### Key live boundaries
- App bootstrap lives in `backend/app/bootstrap/`.
- Scheduler ownership is role-based (`automation` owns delegated runs in production).
- Broker-managed execution is the only active execution/account truth source.
- Runtime credentials are stored through backend runtime settings, not committed env files.

## Durable Rules
- Do not rewrite the whole project.
- Keep broker-managed execution as the single live path.
- Do not reintroduce internal paper trading.
- Preserve optimizer integration from `leaders_optimizer_best.csv`.
- Prefer bounded, modular refactors over broad churn.
- Keep diagnostics truthful and degraded-mode safe.
