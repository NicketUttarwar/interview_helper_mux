#!/usr/bin/env bash
# Print the best Python 3.12+ executable for this repo (stdout = path).
# Prefers native arch (arm64 on Apple Silicon) to avoid Rosetta/x86_64 wheel gaps.
#
# Override: export PYTHON=/opt/homebrew/bin/python3.12
set -euo pipefail

HOST_ARCH="$(uname -m)"

_py_ok() {
  local py="$1"
  command -v "$py" >/dev/null 2>&1 \
    && "$py" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null
}

_py_arch() {
  local py="$1"
  "$py" -c 'import platform; print(platform.machine())' 2>/dev/null || echo "unknown"
}

# Higher priority first. On arm64 Macs, skip x86_64 interpreters.
candidates=()
if [[ -n "${PYTHON:-}" ]]; then
  candidates+=("$PYTHON")
fi
for ver in 3.12 3.13; do
  candidates+=("python${ver}")
done
candidates+=(
  "/opt/homebrew/bin/python3.12"
  "/opt/homebrew/bin/python3.13"
  "/usr/local/bin/python3.12"
  "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
  "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
  python3
)

seen=""
for py in "${candidates[@]}"; do
  [[ -z "$py" ]] && continue
  if [[ " $seen " == *" $py "* ]]; then
    continue
  fi
  seen+=" $py"
  if ! _py_ok "$py"; then
    continue
  fi
  mach="$(_py_arch "$py")"
  if [[ "$HOST_ARCH" == "arm64" && "$mach" == "x86_64" ]]; then
    continue
  fi
  printf '%s\n' "$py"
  exit 0
done

echo "No suitable Python 3.12+ found (need native $HOST_ARCH on this machine)." >&2
echo "On Apple Silicon: eval \"\$(/opt/homebrew/bin/brew shellenv)\" && brew install python@3.12" >&2
echo "Then: export PYTHON=/opt/homebrew/bin/python3.12 && ./scripts/bootstrap_venv.sh" >&2
echo "If uname -m is x86_64, disable Rosetta for Terminal (see SETUP.md Step 0)." >&2
exit 1
