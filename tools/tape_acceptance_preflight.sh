#!/usr/bin/env bash
# Tape acceptance preflight — residual regress + full-auto env + ownership audit.
# Expected intentional noise on a healthy tape: #29 host_vo_duration, #30 S3
# advisories / G-Publish consent, #31 e2e brief on soft refuse.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "tape_acceptance_preflight: check_residual_regress"
./tools/check_residual_regress.sh

echo "tape_acceptance_preflight: verify_full_auto_env"
./tools/verify_full_auto_env.sh

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

echo "tape_acceptance_preflight: audit_artifact_ownership --write-sites-only"
"$PY" tools/audit_artifact_ownership.py --write-sites-only

cat <<'EOF'

tape_acceptance_preflight: OK

Expected intentional noise on plain Mohan full-auto (MUX_FORENSICS unset):
  #29  host_vo_duration advisory under floor — no auto-thicken
  #30  S3 blocked on quality advisories — G-Publish consent required
  #31  e2e brief on soft/stub refuse — production-parity signal, not ship hole

Do not reopen #29–#31 as product bugs. See docs/cross-cutting/exec-11630-major-errors-status.md.
EOF
