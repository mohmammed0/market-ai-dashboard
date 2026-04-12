# Local Live Services

How to run the full live stack locally for development and proving.

## Quick Start

```powershell
# 1. Start services (PostgreSQL, Redis, MLflow)
docker compose -f docker-compose.services.yml up -d

# 2. Activate live environment
copy .env.local-live .env

# 3. Start the backend
.\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# 4. Verify
.\venv\Scripts\python.exe scripts\prove_live_stack.py
```

## Services

### PostgreSQL

| Item | Value |
|------|-------|
| Image | `postgres:16-alpine` |
| Port | `5432` |
| Database | `market_ai` |
| User | `market_ai` |
| Password | `market_ai_dev` |
| Env var | `MARKET_AI_DATABASE_URL=postgresql+psycopg://market_ai:market_ai_dev@127.0.0.1:5432/market_ai` |

Migrations run automatically on startup when `MARKET_AI_DB_RUN_MIGRATIONS_ON_STARTUP=1`.

### Redis

| Item | Value |
|------|-------|
| Image | `redis:7-alpine` |
| Port | `6379` |
| Env var (cache) | `MARKET_AI_REDIS_URL=redis://127.0.0.1:6379/0` |
| Env var (Celery broker) | `CELERY_BROKER_URL=redis://127.0.0.1:6379/1` |
| Env var (Celery backend) | `CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2` |

### MLflow

| Item | Value |
|------|-------|
| Image | `ghcr.io/mlflow/mlflow:v2.21.3` |
| Port | `5000` |
| UI | http://127.0.0.1:5000 |
| Env var | `MLFLOW_TRACKING_URI=http://127.0.0.1:5000` |

### Celery Worker

After services are up:

```powershell
.\venv\Scripts\celery.exe -A backend.app.services.celery_app worker --loglevel=info --pool=solo
```

Tasks registered: `tasks.quote_snapshot`, `tasks.maintenance_reconcile`

### Prefect

Start the local Prefect server (not in Docker Compose — optional):

```powershell
.\venv\Scripts\prefect.exe server start
```

Then set `PREFECT_API_URL=http://127.0.0.1:4200/api` in your environment.

## Switching Back to SQLite (Fallback)

```powershell
copy .env.example .env
# Or just remove MARKET_AI_DATABASE_URL override — defaults to SQLite
```

## Stopping Services

```powershell
docker compose -f docker-compose.services.yml down
# Add -v to also remove volumes (database data)
docker compose -f docker-compose.services.yml down -v
```

## Verifying Stack Status

While the backend is running:

```
GET http://127.0.0.1:8000/api/stack/summary
```

Each subsystem reports: `active`, `fallback`, `unavailable`, or `misconfigured`.

## Environment Variables Reference

| Variable | Purpose | Live value |
|----------|---------|------------|
| `MARKET_AI_DATABASE_URL` | Database connection | `postgresql+psycopg://market_ai:market_ai_dev@127.0.0.1:5432/market_ai` |
| `MARKET_AI_REDIS_URL` | Cache backend | `redis://127.0.0.1:6379/0` |
| `MARKET_AI_REDIS_ENABLED` | Enable Redis cache | `1` |
| `MLFLOW_TRACKING_URI` | Experiment tracking | `http://127.0.0.1:5000` |
| `CELERY_BROKER_URL` | Task broker | `redis://127.0.0.1:6379/1` |
| `CELERY_RESULT_BACKEND` | Task results | `redis://127.0.0.1:6379/2` |
| `PREFECT_API_URL` | Workflow orchestration | `http://127.0.0.1:4200/api` |
