#!/usr/bin/env bash
# Holistic lightweight simulated test runner — no external API calls, no Playwright E2E.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REPORT_DIR="$ROOT/tests/reports"
REPORT="$REPORT_DIR/holistic_simulated_report.txt"
mkdir -p "$REPORT_DIR"

section() {
  echo "$1" | tee -a "$REPORT"
}

: >"$REPORT"
section "=== Holistic Simulated Test Report ==="
section "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
section ""

# Tier 0 — prerequisites
section "--- Tier 0: Prerequisites ---"
if [[ -f "$ROOT/scripts/bootstrap_venv.sh" ]]; then
  "$ROOT/scripts/bootstrap_venv.sh" >>"$REPORT" 2>&1 || true
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
if "$ROOT/tools/check_prerequisites.sh" >>"$REPORT" 2>&1; then
  section "Prerequisites: PASS"
else
  section "Prerequisites: FAIL (see above)"
  exit 1
fi
python -c "from interview_mux.config import merged_config; merged_config()" >>"$REPORT" 2>&1
section "Config import: PASS"
section ""

# Tier 1 — main pytest suite (network guard via tests/conftest.py)
section "--- Tier 1: Unit / integration (pytest tests/) ---"
PYTEST_OUT="$(mktemp)"
set +e
pytest tests/ -q --tb=line 2>&1 | tee "$PYTEST_OUT"
PYTEST_RC=${PIPESTATUS[0]}
set -e
if [[ "$PYTEST_RC" -eq 0 ]]; then
  COUNT="$(grep -Eo '[0-9]+ passed' "$PYTEST_OUT" | tail -1 || echo 'passed')"
  section "Main suite: PASS ($COUNT)"
else
  FAIL_COUNT="$(grep -Eo '[0-9]+ failed' "$PYTEST_OUT" | tail -1 || echo 'some failures')"
  PASS_COUNT="$(grep -Eo '[0-9]+ passed' "$PYTEST_OUT" | tail -1 || echo '0 passed')"
  section "Main suite: FAIL ($PASS_COUNT, $FAIL_COUNT) — see pytest output above"
  rm -f "$PYTEST_OUT"
  exit 1
fi
rm -f "$PYTEST_OUT"
section ""

# Tier 1b — E2E helper unit tests (not live E2E)
section "--- Tier 1b: E2E helper unit tests ---"
E2E_OUT="$(mktemp)"
if pytest tests/e2e/ -q -k "not live" --tb=line 2>&1 | tee "$E2E_OUT"; then
  section "E2E helpers: PASS"
else
  section "E2E helpers: FAIL"
  cat "$E2E_OUT" >>"$REPORT"
  rm -f "$E2E_OUT"
  exit 1
fi
rm -f "$E2E_OUT"
section ""

# Tier 2 — holistic markers (subset sanity)
section "--- Tier 2: Holistic simulated layer ---"
HOLISTIC_OUT="$(mktemp)"
if pytest tests/test_holistic_simulated_journey.py tests/test_api_contract_sweep.py tests/test_stage_parity.py -q --tb=line 2>&1 | tee "$HOLISTIC_OUT"; then
  section "Holistic layer: PASS"
else
  section "Holistic layer: FAIL"
  cat "$HOLISTIC_OUT" >>"$REPORT"
  rm -f "$HOLISTIC_OUT"
  exit 1
fi
rm -f "$HOLISTIC_OUT"
section ""

# Tier 3 — frontend compile
section "--- Tier 3: Frontend compile (npm run build) ---"
if (cd "$ROOT/frontend" && npm run build) >>"$REPORT" 2>&1; then
  section "Frontend build: PASS"
else
  section "Frontend build: FAIL"
  exit 1
fi
section ""

section "--- Excluded (by design) ---"
section "Skipped: ./scripts/e2e.sh (Playwright + real APIs)"
section "Skipped: E2E_LIVE=1 pytest tests/e2e/test_live.py"
section ""
section "Finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
section "Report: $REPORT"

echo ""
echo "All holistic simulated tiers passed. Report: $REPORT"
