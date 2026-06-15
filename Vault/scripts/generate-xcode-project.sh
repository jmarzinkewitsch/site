#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v xcodegen >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "xcodegen not found; installing with Homebrew..."
    brew install xcodegen
  else
    echo "ERROR: xcodegen is not installed. Install it with: brew install xcodegen" >&2
    exit 1
  fi
fi

xcodegen generate
open Vault.xcodeproj
