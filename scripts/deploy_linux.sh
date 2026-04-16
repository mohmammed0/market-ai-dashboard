#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${1:-.env.production}"
BOOTSTRAP_SYMBOLS="${BOOTSTRAP_SYMBOLS:-AAPL,MSFT,NVDA,SPY}"

mkdir -p data model_artifacts

if [[ ! -f "$ENV_FILE" ]]; then
  cp .env.production.example "$ENV_FILE"
  echo "Created $ENV_FILE from .env.production.example"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

docker compose --env-file "$ENV_FILE" up -d --build

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

for attempt in {1..45}; do
  if curl -fsS http://127.0.0.1:8000/ready >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

docker compose --env-file "$ENV_FILE" exec -T backend python scripts/bootstrap_market_data.py --symbols "$BOOTSTRAP_SYMBOLS"
docker compose --env-file "$ENV_FILE" ps
