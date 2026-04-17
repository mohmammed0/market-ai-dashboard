#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${1:-.env.production}"
BOOTSTRAP_SYMBOLS="${BOOTSTRAP_SYMBOLS:-AAPL,MSFT,NVDA,SPY}"
SKIP_BACKUP="${SKIP_BACKUP:-0}"
SKIP_BOOTSTRAP="${SKIP_BOOTSTRAP:-0}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:4173}"
DEPLOY_TIMEOUT_SECONDS="${DEPLOY_TIMEOUT_SECONDS:-120}"

mkdir -p data model_artifacts

if [[ ! -f "$ENV_FILE" ]]; then
  cp .env.production.example "$ENV_FILE"
  echo "Created $ENV_FILE from .env.production.example"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

echo "Validating docker compose configuration..."
docker compose --env-file "$ENV_FILE" config >/dev/null

if [[ "$SKIP_BACKUP" != "1" ]] && [[ -f "scripts/backup_runtime.py" ]]; then
  echo "Creating safety backup snapshot..."
  python scripts/backup_runtime.py --include-logs >/dev/null
fi

echo "Starting updated services..."
docker compose --env-file "$ENV_FILE" up -d --build --remove-orphans

if docker compose --env-file "$ENV_FILE" config --services | grep -qx "ollama"; then
  case "${OLLAMA_ENABLED:-0}" in
    1|true|TRUE|yes|YES|on|ON)
      for attempt in {1..30}; do
        if docker compose --env-file "$ENV_FILE" exec -T ollama ollama list >/dev/null 2>&1; then
          break
        fi
        sleep 2
      done
      docker compose --env-file "$ENV_FILE" exec -T ollama ollama pull "${OLLAMA_MODEL:-gemma2:2b}" || true
      ;;
  esac
fi

echo "Waiting for readiness..."
for (( attempt=0; attempt<DEPLOY_TIMEOUT_SECONDS; attempt+=2 )); do
  if curl -fsS "$BACKEND_URL/ready" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsS "$BACKEND_URL/health" >/dev/null
curl -fsS "$BACKEND_URL/ready" >/dev/null
curl -fsS "$BACKEND_URL/auth/status" >/dev/null
curl -fsSI "$FRONTEND_URL/" >/dev/null

if [[ "$SKIP_BOOTSTRAP" != "1" ]]; then
  echo "Bootstrapping market data for symbols: $BOOTSTRAP_SYMBOLS"
  docker compose --env-file "$ENV_FILE" exec -T backend python scripts/bootstrap_market_data.py --symbols "$BOOTSTRAP_SYMBOLS"
fi

if docker compose --env-file "$ENV_FILE" config --services | grep -qx "db"; then
  echo "Alembic version:"
  docker compose --env-file "$ENV_FILE" exec -T db psql -U "${MARKET_AI_POSTGRES_USER:-market_ai}" -d "${MARKET_AI_POSTGRES_DB:-market_ai}" -c "select version_num from alembic_version;"
fi

echo "Running post-deploy smoke checks..."
BACKEND_URL="$BACKEND_URL" FRONTEND_URL="$FRONTEND_URL" bash ./scripts/check_stack.sh "$ENV_FILE"

docker compose --env-file "$ENV_FILE" ps
