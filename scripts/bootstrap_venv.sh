#!/usr/bin/env bash
# Create .venv and install all Python deps from requirements.txt.
#
# Apple Silicon: eval "$(/opt/homebrew/bin/brew shellenv)"
#               export PYTHON=/opt/homebrew/bin/python3.12
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PY="$("${REPO_ROOT}/scripts/_pick_python.sh")"

echo "=== bootstrap venv with $PY ($("$PY" --version)) arch=$("$PY" -c 'import platform; print(platform.machine())') ==="
if [[ "$(uname -m)" == "arm64" ]]; then
  mach="$("$PY" -c 'import platform; print(platform.machine())')"
  if [[ "$mach" != "arm64" ]]; then
    echo "ERROR: host is arm64 but Python is $mach — use /opt/homebrew/bin/python3.12 (see SETUP.md Step 0)." >&2
    exit 1
  fi
fi
rm -rf .venv
"$PY" -m venv .venv
# shellcheck source=/dev/null
source .venv/bin/activate
python -m pip install --upgrade pip wheel
pip install --prefer-binary -r requirements.txt
python tools/verify_install.py
