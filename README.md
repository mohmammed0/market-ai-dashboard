# Market AI Dashboard

Production-minded US equities platform with three coexisting surfaces sharing the same core engines:

- Root Python engines (source-of-truth analysis/ranking/backtest logic)
- FastAPI backend (`backend/`)
- React frontend operator console (`frontend/`)

## Architecture At A Glance

- Core engines: `analysis_engine.py`, `technical_engine.py`, `ranking_engine.py`, `backtest_engine.py`
- Desktop app: `main_ui.py`
- Shared wrappers: `core/`
- Backend API: `backend/app/`
- Frontend UI: `frontend/src/`

## Repo Hygiene Docs

- Repo map: `docs/repo_map.md`
- Ownership map: `docs/ownership_map.md`
- Deprecation map: `docs/deprecation_map.md`
- Workflow guides: `docs/dev-workflows/`

## Local Run

### Backend

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
Set-Location .\frontend
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

### Desktop app

```powershell
.\venv\Scripts\python.exe .\main_ui.py
```
