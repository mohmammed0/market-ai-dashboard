# Deployment And Run

## What Changed
- The live product is the modern stack under `backend/`, `frontend/`, `core/`, and `scripts/`.
- Legacy engines and desktop tooling now live under `legacy/`.
- Production containers use PostgreSQL via `docker-compose.yml`.
- Runtime secrets are not committed; only safe templates stay in Git.
- Scheduler ownership is explicit: `automation` owns delegated jobs in production.

## Local Development
Backend:
```powershell
Set-Location C:\Users\fas51\Mohammed\market_dashboard
.\venv\Scripts\Activate.ps1
pip install -r .\backend\requirements.txt
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:
```powershell
Set-Location C:\Users\fas51\Mohammed\market_dashboard\frontend
npm install
npm run dev
```

Legacy desktop UI:
```powershell
Set-Location C:\Users\fas51\Mohammed\market_dashboard
.\venv\Scripts\Activate.ps1
python .\legacy\ui\main_ui.py
```

## Linux Docker Deployment
```bash
git clone <your-repo-url> market_dashboard
cd market_dashboard
cp .env.production.example .env.production
mkdir -p data model_artifacts

docker compose --env-file .env.production up -d --build
```

## Health Checks
```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/api/trading/portfolio
curl http://127.0.0.1:8000/api/automation/status
curl -I http://127.0.0.1:4173/
```

## Runtime Credential Rules
- UI-managed settings stored by the backend take precedence over environment variables.
- Environment variables remain fallback defaults only.
- Rotate any credential that was ever stored in a local/server `.env` outside approved secret management.
