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

_host_arch="$(uname -m)"
_node_arch="$(node -p "process.arch" 2>/dev/null || echo unknown)"
case "$_host_arch" in
  arm64) _want_node_arch="arm64" ;;
  x86_64 | amd64) _want_node_arch="x64" ;;
  *)
    _want_node_arch="$_host_arch"
    ;;
esac

if [[ "$_node_arch" != "$_want_node_arch" ]]; then
  echo "WARN: Node.js process.arch is ${_node_arch} but uname -m is ${_host_arch} (expected ${_want_node_arch} for native addons)." >&2
  echo "      On Apple Silicon, prefer arm64 Node (brew install node@20) so Rollup installs @rollup/rollup-darwin-arm64." >&2
fi

_install_deps() {
  if [[ -f package-lock.json ]]; then
    npm ci
  else
    npm install
  fi
}

_rollup_ok() {
  node -e "require('rollup')" >/dev/null 2>&1
}

if [[ ! -d node_modules ]] || ! _rollup_ok; then
  if [[ -d node_modules ]]; then
    echo "Repairing frontend/node_modules (missing or wrong-arch Rollup binary) ..."
    rm -rf node_modules
  else
    echo "Installing frontend dependencies ..."
  fi
  _install_deps
fi

if ! _rollup_ok; then
  echo "ERROR: Rollup native module still missing after npm ci." >&2
  echo "From repo root:" >&2
  echo "  cd frontend && rm -rf node_modules && npm ci && cd .. && ./scripts/build_gui.sh" >&2
  exit 1
fi

npm run build
echo "GUI built → src/interview_mux/web/static/"
