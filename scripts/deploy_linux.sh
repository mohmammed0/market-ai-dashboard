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
API_TOKEN="${API_TOKEN:-}"

mkdir -p data model_artifacts

if [[ ! -f "$ENV_FILE" ]]; then
  cp .env.production.example "$ENV_FILE"
  echo "Created $ENV_FILE from .env.production.example"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

AUTH_HEADER=()

_auth_enabled() {
  case "${MARKET_AI_AUTH_ENABLED:-0}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

_prepare_auth_header() {
  AUTH_HEADER=()
  if ! _auth_enabled; then
    return 0
  fi
  if [[ -n "$API_TOKEN" ]]; then
    AUTH_HEADER=(-H "Authorization: Bearer $API_TOKEN")
    return 0
  fi
  if [[ -z "${MARKET_AI_AUTH_DEFAULT_USERNAME:-}" || -z "${MARKET_AI_AUTH_DEFAULT_PASSWORD:-}" ]]; then
    return 1
  fi
  API_TOKEN="$(
    BACKEND_URL="$BACKEND_URL" \
    MARKET_AI_AUTH_DEFAULT_USERNAME="$MARKET_AI_AUTH_DEFAULT_USERNAME" \
    MARKET_AI_AUTH_DEFAULT_PASSWORD="$MARKET_AI_AUTH_DEFAULT_PASSWORD" \
    python - <<'PY'
import json
import os
import urllib.request

payload = json.dumps(
    {
        "username": os.environ["MARKET_AI_AUTH_DEFAULT_USERNAME"],
        "password": os.environ["MARKET_AI_AUTH_DEFAULT_PASSWORD"],
    }
).encode("utf-8")
request = urllib.request.Request(
    os.environ["BACKEND_URL"].rstrip("/") + "/auth/login",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=15) as response:
    print(json.loads(response.read().decode("utf-8")).get("access_token", ""))
PY
  )"
  API_TOKEN="$(printf '%s' "$API_TOKEN" | tr -d '\r\n')"
  if [[ -z "$API_TOKEN" ]]; then
    return 1
  fi
  AUTH_HEADER=(-H "Authorization: Bearer $API_TOKEN")
}

curl_backend() {
  local path="$1"
  shift || true
  local headers=()
  if [[ "$path" == "/ready" || "$path" == /api/* ]]; then
    if _auth_enabled; then
      _prepare_auth_header || return 1
      headers=("${AUTH_HEADER[@]}")
    fi
  fi
  curl -fsS "${headers[@]}" "$BACKEND_URL$path" "$@"
}

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
  if curl_backend "/ready" >/dev/null 2>&1 || curl -fsS "$BACKEND_URL/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsS "$BACKEND_URL/health" >/dev/null
curl -fsS "$BACKEND_URL/auth/status" >/dev/null
if ! curl_backend "/ready" >/dev/null 2>&1; then
  echo "Skipping /ready smoke check because authenticated access is not available."
fi
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
BACKEND_URL="$BACKEND_URL" FRONTEND_URL="$FRONTEND_URL" API_TOKEN="$API_TOKEN" bash ./scripts/check_stack.sh "$ENV_FILE"

docker compose --env-file "$ENV_FILE" ps
