#!/usr/bin/env bash
# Step 1 gate: verify Mac/host tools before pip install.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

FAIL=0
ok() { echo "OK   $*"; }
warn() { echo "WARN $*"; }
bad() { echo "FAIL $*"; FAIL=1; }

echo "=== Step 1: system prerequisites ==="

ARCH="$(uname -m)"
if [[ "$ARCH" == "arm64" ]]; then
  ok "architecture: arm64"
else
  if [[ "$ARCH" == "x86_64" ]]; then
    bad "architecture: x86_64 (Rosetta shell) — use native arm64 terminal (SETUP.md Step 0)"
  else
    warn "architecture: $ARCH (plan targets Apple Silicon arm64)"
  fi
fi

if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PY_CHECK="${REPO_ROOT}/.venv/bin/python"
  vpy_ver="$($PY_CHECK --version 2>&1)"
  vpy_arch="$($PY_CHECK -c 'import platform; print(platform.machine())' 2>/dev/null || echo unknown)"
  if "$PY_CHECK" -c 'import sys; exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    ok "python 3.12+ (venv): $vpy_ver ($PY_CHECK) arch=$vpy_arch"
  else
    bad "venv python too old ($vpy_ver) — rebuild: ./scripts/bootstrap_venv.sh"
  fi
  if [[ "$ARCH" == "arm64" && "$vpy_arch" == "x86_64" ]]; then
    bad "venv is x86_64 on arm64 host — rm -rf .venv && ./scripts/bootstrap_venv.sh"
  fi
elif [[ -x "${REPO_ROOT}/scripts/_pick_python.sh" ]]; then
  if PY_CHECK="$("${REPO_ROOT}/scripts/_pick_python.sh" 2>/dev/null)"; then
    py_arch="$("$PY_CHECK" -c 'import platform; print(platform.machine())' 2>/dev/null || true)"
    ok "python 3.12+ (recommended): $($PY_CHECK --version 2>&1) ($PY_CHECK) arch=$py_arch"
  else
    bad "Python 3.12+ native arm64 not found — brew install python@3.12 (see SETUP.md)"
  fi
else
  bad "Python 3.12+ not found — brew install python@3.12"
fi

if command -v /opt/homebrew/bin/brew >/dev/null 2>&1; then
  ok "homebrew: /opt/homebrew/bin/brew"
elif command -v brew >/dev/null 2>&1; then
  warn "homebrew: $(which brew) (prefer /opt/homebrew on Apple Silicon)"
else
  warn "homebrew not found — brew install python@3.12 ffmpeg"
fi

if [[ -n "${PY_CHECK:-}" ]] && command -v python3.11 >/dev/null 2>&1; then
  py311_arch="$(python3.11 -c 'import platform; print(platform.machine())' 2>/dev/null || true)"
  if [[ "$ARCH" == "arm64" && "$py311_arch" == "x86_64" ]]; then
    warn "python3.11 is x86_64 — use /opt/homebrew/bin/python3.12 for this repo"
  fi
fi

if command -v ffmpeg >/dev/null 2>&1; then
  ok "ffmpeg: $(ffmpeg -version 2>&1 | head -n 1)"
else
  bad "ffmpeg not found — brew install ffmpeg"
fi

if command -v ffprobe >/dev/null 2>&1; then
  ok "ffprobe: $(ffprobe -version 2>&1 | head -n 1)"
else
  bad "ffprobe not found — brew install ffmpeg"
fi

if command -v ffmpeg >/dev/null 2>&1; then
  if ffmpeg -hide_banner -h filter=loudnorm 2>&1 | grep -qE 'loudnorm|EBU R128'; then
    ok "ffmpeg loudnorm filter"
  elif ffmpeg -hide_banner -filters 2>/dev/null | grep -q loudnorm; then
    ok "ffmpeg loudnorm filter"
  else
    bad "ffmpeg missing loudnorm filter"
  fi
fi

if command -v aws >/dev/null 2>&1; then
  ok "aws cli (optional): $(aws --version 2>&1)"
else
  warn "aws cli not found (optional unless --provider aws)"
fi

if command -v npx >/dev/null 2>&1; then
  ok "npx (optional MCP): $(npx --version 2>&1)"
else
  warn "npx not found (optional for Cursor MCP)"
fi

echo "=== Step 1 complete ==="
if [[ "$FAIL" -ne 0 ]]; then
  echo "Fix FAIL items above, then re-run: ./tools/check_prerequisites.sh"
  exit 1
fi
echo "PASS — proceed to Step 2: ./scripts/bootstrap_venv.sh (or ./scripts/install_venv_deps.sh)"
exit 0
