#!/usr/bin/env bash
# Frontend npm deps + production GUI bundle into src/interview_mux/web/static/
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is required. Install Node.js 20+ (e.g. brew install node@20)." >&2
  exit 1
fi

echo "=== Frontend GUI (npm) ==="
cd "$ROOT/frontend"
if [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi
cd "$ROOT"

bash "$ROOT/scripts/build_gui.sh"
