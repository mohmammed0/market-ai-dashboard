#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${1:-.env.production}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:4173}"
API_TOKEN="${API_TOKEN:-}"

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

docker compose --env-file "$ENV_FILE" ps
echo
echo "GET $BACKEND_URL/health"
curl -fsS "$BACKEND_URL/health"
echo
echo
echo "GET $BACKEND_URL/ready"
if ! curl_backend "/ready"; then
  echo "skipped"
fi
echo
echo
echo "GET $BACKEND_URL/auth/status"
curl -fsS "$BACKEND_URL/auth/status"
echo
echo
if _prepare_auth_header >/dev/null 2>&1; then
  echo "GET $BACKEND_URL/api/jobs (authenticated)"
  curl -fsS "${AUTH_HEADER[@]}" "$BACKEND_URL/api/jobs"
  echo
  echo
  echo "GET $BACKEND_URL/api/trading/portfolio (authenticated)"
  curl -fsS "${AUTH_HEADER[@]}" "$BACKEND_URL/api/trading/portfolio"
  echo
  echo
  echo "GET $BACKEND_URL/api/automation/status (authenticated)"
  curl -fsS "${AUTH_HEADER[@]}" "$BACKEND_URL/api/automation/status"
  echo
  echo
fi

echo "GET $FRONTEND_URL/"
curl -fsSI "$FRONTEND_URL/" | head -n 5
