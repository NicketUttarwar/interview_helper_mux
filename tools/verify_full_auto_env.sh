#!/usr/bin/env bash
# Assert Full-auto driver env has production parity (no stub/listenability-soft keys).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH="$ROOT/tools/full_auto_daemon_launch.py"

if [[ ! -f "$LAUNCH" ]]; then
  echo "verify_full_auto_env: missing $LAUNCH" >&2
  exit 1
fi

fail=0
for key in MUX_E2E_MUSICGEN_ALLOW_STUB MUX_E2E_SOFT_LISTENABILITY; do
  if grep -q "$key" "$LAUNCH"; then
    echo "verify_full_auto_env: FAIL — $key must not appear in full_auto_daemon_launch.py _driver_env" >&2
    fail=1
  fi
done

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi

echo "verify_full_auto_env: OK — Full-auto env lacks stub/listenability-soft keys"
