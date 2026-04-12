#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${1:-.env.production}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:4173}"

docker compose --env-file "$ENV_FILE" ps
echo
echo "GET $BACKEND_URL/health"
curl -fsS "$BACKEND_URL/health"
echo
echo
echo "GET $BACKEND_URL/ready"
curl -fsS "$BACKEND_URL/ready"
echo
echo
echo "GET $BACKEND_URL/api/jobs"
curl -fsS "$BACKEND_URL/api/jobs"
echo
echo
echo "GET $BACKEND_URL/api/paper/portfolio"
curl -fsS "$BACKEND_URL/api/paper/portfolio"
echo
echo
echo "GET $BACKEND_URL/api/automation/status"
curl -fsS "$BACKEND_URL/api/automation/status"
echo
echo
echo "GET $FRONTEND_URL/"
curl -fsSI "$FRONTEND_URL/" | head -n 5
