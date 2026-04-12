# Deployment And Run

## What Changed
- Production containers now default to PostgreSQL through the `db` service in `docker-compose.yml`.
- SQLite remains the local development fallback and still lives at `data/market_ai.db` when you do not override `MARKET_AI_DATABASE_URL`.
- Host persistence still mounts `./data:/app/data` for logs, cache, runtime artifacts, and the settings key.
- Analyze no longer depends on `us_watchlist_source/` existing on the server. It can use tracked seed files, cached files under `data/source_cache`, and on-demand yfinance bootstrap.
- Frontend production traffic now defaults to same-origin and proxies `/api`, `/health`, and `/ready` through nginx to the backend service.
- UI-managed runtime settings are now the normal path for OpenAI and Alpaca credentials. Environment variables remain fallback-only.
- Scheduler ownership is now explicit. By default only the dedicated `automation` role starts APScheduler; the API role stays request-only unless you override `MARKET_AI_SCHEDULER_RUNNER_ROLE`.
- Migration ownership is now explicit. The API container runs Alembic on startup by default; automation and worker processes do not.

## Local Development
Backend:
```powershell
Set-Location C:\Users\fas51\Mohammed\market_dashboard
.\venv\Scripts\Activate.ps1
pip install -r .\backend\requirements.txt
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Optional local PostgreSQL development:
```powershell
$env:MARKET_AI_DATABASE_URL="postgresql+psycopg://market_ai:change-me@127.0.0.1:5432/market_ai"
$env:MARKET_AI_DB_LEGACY_BOOTSTRAP="0"
$env:MARKET_AI_DB_RUN_MIGRATIONS_ON_STARTUP="1"
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Optional single-process scheduler ownership during local development:
```powershell
$env:MARKET_AI_SCHEDULER_RUNNER_ROLE="all"
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:
```powershell
Set-Location C:\Users\fas51\Mohammed\market_dashboard\frontend
npm install
npm run dev
```

Desktop UI:
```powershell
Set-Location C:\Users\fas51\Mohammed\market_dashboard
.\venv\Scripts\Activate.ps1
python .\main_ui.py
```

## Linux Docker Deployment
Clone and prepare:
```bash
git clone <your-repo-url> market_dashboard
cd market_dashboard
cp .env.production.example .env.production
mkdir -p data model_artifacts
```

Build and start:
```bash
docker compose --env-file .env.production up -d --build
```

If `8000` or `4173` are already in use on the host, override these in `.env.production` before you start the stack:
- `MARKET_AI_BACKEND_PUBLISHED_PORT`
- `MARKET_AI_FRONTEND_PUBLISHED_PORT`

Default production-style services:
- `db`: PostgreSQL 16 with persistent named volume `postgres_data`
- `backend`: FastAPI API + Alembic startup migration owner
- `automation`: scheduler / continuous-learning owner using the same PostgreSQL database
- `frontend`: nginx-served web UI

Recommended rollout settings:
- In Docker Compose, keep `MARKET_AI_DB_RUN_MIGRATIONS_ON_STARTUP_API=1` on the primary API service.
- In Docker Compose, keep `MARKET_AI_DB_RUN_MIGRATIONS_ON_STARTUP_AUTOMATION=0` on automation and any secondary worker services.

Bootstrap sample market data after first start:
```bash
docker compose --env-file .env.production exec -T backend python scripts/bootstrap_market_data.py --symbols AAPL,MSFT,NVDA,SPY
```

Health checks:
```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/api/jobs
curl http://127.0.0.1:8000/api/paper/portfolio
curl http://127.0.0.1:8000/api/automation/status
curl -I http://127.0.0.1:4173/
```

Open the web app and add runtime credentials from the Settings page instead of editing `.env`.

## Domain + SSL Readiness
- Production routing is same-origin by default, so the browser talks to the deployed domain and nginx forwards `/api`, `/health`, and `/ready` internally to the backend.
- Set `MARKET_AI_SERVER_NAME`, `MARKET_AI_PUBLIC_WEB_ORIGIN`, and `MARKET_AI_PUBLIC_API_ORIGIN` in `.env.production` to your real domain, for example `https://app.example.com`.
- Keep `MARKET_AI_SCHEDULER_RUNNER_ROLE=automation` in production unless you intentionally want a combined single-process runtime.
- SSL termination is expected at an external reverse proxy such as Nginx, Caddy, Traefik, or a cloud load balancer. Forward these paths to the frontend container:
  - `/`
  - `/api`
  - `/health`
  - `/ready`
- When SSL is terminated upstream, keep `MARKET_AI_PROXY_HEADERS_ENABLED=1` so the backend correctly respects forwarded protocol and host headers.
- Example reverse-proxy target:
  - public `https://app.example.com` -> local `http://127.0.0.1:4173`

## One-Command Helpers
Initial deploy or update after `git pull`:
```bash
chmod +x scripts/deploy_linux.sh scripts/check_stack.sh
./scripts/deploy_linux.sh .env.production
```

Recovery / verification:
```bash
./scripts/check_stack.sh .env.production
docker compose --env-file .env.production logs --tail=100 backend
docker compose --env-file .env.production logs --tail=100 automation
docker compose --env-file .env.production exec -T db psql -U "$MARKET_AI_POSTGRES_USER" -d "$MARKET_AI_POSTGRES_DB" -c "select version_num from alembic_version;"
docker compose --env-file .env.production restart backend automation frontend
```

## Logs Monitoring
- Structured runtime events are written to `data/logs/events.jsonl`.
- General application logs are written to `data/logs/app.log`.
- The web UI now exposes a lightweight operations view at `/operations` for:
  - domain and proxy readiness
  - recent structured events
  - a raw tail of `app.log`
  - backup inventory
- Useful production checks:
```bash
docker compose --env-file .env.production logs --tail=150 backend
docker compose --env-file .env.production logs --tail=150 automation
./scripts/check_stack.sh .env.production
```

## Backup And Restore
Create a backup:
```bash
python scripts/backup_runtime.py --include-logs
```

Optional secure variant if you intentionally manage the encryption key within the same secret workflow:
```bash
python scripts/backup_runtime.py --include-logs --include-settings-key
```

Restore into a maintenance workspace:
```bash
python scripts/restore_runtime.py backups/<archive>.tar.gz --force
```

What is covered:
- SQLite database when SQLite is the active runtime
- model artifacts
- source cache
- optional runtime cache
- optional logs

What is excluded by default:
- `data/.settings.key`
- PostgreSQL database contents. Use `pg_dump` or your platform-native PostgreSQL backup workflow separately.

Recommended restore flow:
1. Stop the stack.
2. Restore the archive.
3. Re-provide `data/.settings.key` securely if you intend to decrypt saved runtime secrets.
4. Start the stack again.
5. Check `/health`, `/ready`, and the `/operations` page.

## Runtime Credential Rules
- UI-managed settings stored by the backend take precedence over environment variables.
- Environment variables remain valid as deployment defaults or recovery fallbacks.
- The UI never returns raw saved secrets after storage; it only shows masked values.
- Rotate any key that was previously exposed in a local or server `.env`.

## Analyze Source Data
- Tracked seed CSV files live under `seed_data/source_seed/`.
- Runtime cache writes to `data/source_cache/`.
- If a symbol is missing locally, the app can fetch via yfinance and persist the result into the cache.
- `scripts/bootstrap_market_data.py` can warm the cache on first deploy.

## Storage Paths
- Local SQLite database: `data/market_ai.db`
- Settings encryption key: `data/.settings.key`
- Source cache: `data/source_cache/`
- Runtime cache: `data/runtime_cache/`
- Model artifacts: `model_artifacts/`

## PostgreSQL Rollout Notes
1. Set `MARKET_AI_DATABASE_URL` to the PostgreSQL connection string in `.env.production`.
2. Keep `MARKET_AI_DB_LEGACY_BOOTSTRAP=0` in PostgreSQL environments.
3. Keep `MARKET_AI_DB_RUN_MIGRATIONS_ON_STARTUP_API=1` for the primary backend startup path only, and `MARKET_AI_DB_RUN_MIGRATIONS_ON_STARTUP_AUTOMATION=0` for automation.
4. Confirm `/ready` before letting automation and external traffic hit the API.
5. Verify Alembic state with:
```bash
docker compose --env-file .env.production exec -T db psql -U "$MARKET_AI_POSTGRES_USER" -d "$MARKET_AI_POSTGRES_DB" -c "select version_num from alembic_version;"
```

## Notes
- `leaders_optimizer_best.csv` is still used when present. When it is not available, the app falls back to the tracked seed optimizer snapshot under `seed_data/leaders_optimizer_best.seed.csv`.
- Paper trading remains enabled. Live broker execution remains disabled by default.
