#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  "$ROOT_DIR/scripts/bootstrap-env.sh"
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

set -a
# shellcheck disable=SC1091
source .env
set +a

export VAULT_CONFIG_PATH="${VAULT_CONFIG_PATH:-$ROOT_DIR/config.json}"
if [[ "$VAULT_CONFIG_PATH" == /data/* ]]; then
  export VAULT_CONFIG_PATH="$ROOT_DIR/config.json"
fi

# .env.example is optimized for Docker Compose, where "redis" is a service name.
# For local development, degrade gracefully without cache unless the user set a
# reachable Redis URL explicitly.
if [[ "${REDIS_URL:-}" == redis://redis:* ]]; then
  unset REDIS_URL
fi

exec uvicorn main:app --reload --host 0.0.0.0 --port 8787
