#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
EXAMPLE_FILE="$ROOT_DIR/.env.example"

if [[ -f "$ENV_FILE" ]]; then
  echo "OK: $ENV_FILE exists; leaving it unchanged."
else
  cp "$EXAMPLE_FILE" "$ENV_FILE"
  echo "OK: created $ENV_FILE from .env.example."
fi

cat <<MSG

Next steps:
1. Edit $ENV_FILE if you want to bootstrap Jellyfin values.
2. Start the backend with one of:
   - Docker:  $ROOT_DIR/scripts/run-api-docker.sh
   - Local:   $ROOT_DIR/scripts/run-api-local.sh
MSG
