#!/usr/bin/env bash
# Assert Full-auto driver env has production parity (no stub/listenability-soft /
# last-resort / quality-waiver keys set in _driver_env).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH="$ROOT/tools/full_auto_daemon_launch.py"

if [[ ! -f "$LAUNCH" ]]; then
  echo "verify_full_auto_env: missing $LAUNCH" >&2
  exit 1
fi

# Extract _driver_env function body (next def or EOF).
driver_env_body="$(
  awk '
    /^def _driver_env\(/ { capture=1; next }
    capture && /^def / { exit }
    capture { print }
  ' "$LAUNCH"
)"

if [[ -z "$driver_env_body" ]]; then
  echo "verify_full_auto_env: FAIL — could not extract _driver_env from $LAUNCH" >&2
  exit 1
fi

fail=0

# Hard denylist: these must never appear in _driver_env at all.
for key in MUX_E2E_MUSICGEN_ALLOW_STUB MUX_E2E_SOFT_LISTENABILITY; do
  if printf '%s\n' "$driver_env_body" | grep -q "$key"; then
    echo "verify_full_auto_env: FAIL — $key must not appear in full_auto_daemon_launch.py _driver_env" >&2
    fail=1
  fi
done

# Soft/last-resort keys: must not be set-to-1 inside _driver_env.
# Product callers refuse when set; they are not popped here (absent from body).
for key in INTERVIEW_MUX_E2E_LAST_RESORT_SOFT INTERVIEW_MUX_E2E_QUALITY_WAIVERS; do
  if printf '%s\n' "$driver_env_body" | grep -E -q "[\"']${key}[\"'][[:space:]]*:[[:space:]]*[\"']1[\"']"; then
    echo "verify_full_auto_env: FAIL — $key must not be set to 1 in _driver_env" >&2
    fail=1
  fi
  if printf '%s\n' "$driver_env_body" | grep -E -q "${key}=1|${key}=[\"']1[\"']"; then
    echo "verify_full_auto_env: FAIL — $key must not be set to 1 in _driver_env" >&2
    fail=1
  fi
done

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi

echo "verify_full_auto_env: OK — Full-auto env lacks stub/listenability-soft/last-resort/waiver keys"
