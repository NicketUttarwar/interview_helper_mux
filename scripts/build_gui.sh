#!/usr/bin/env bash
# Build React + TypeScript GUI into src/interview_mux/web/static/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$ROOT/frontend"

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is required to build the GUI. Install Node.js 20+." >&2
  exit 1
fi

cd "$FRONTEND"
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run build
echo "GUI built → src/interview_mux/web/static/"
