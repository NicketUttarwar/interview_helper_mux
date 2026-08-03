#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options to terraform plan...]

Create an execution plan. Loads config/secrets/secrets.env when present.

Examples:
  $(basename "$0")
  $(basename "$0") -out=tfplan
  $(basename "$0") -destroy
  USE_LATEST_SESSION=1 $(basename "$0")   # restore live state from session backup first
  $(basename "$0") --use-session          # same (strip flag before terraform)
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

tf_log "→ terraform plan (execution plan; use -destroy for destroy preview)"
terraform_common_exec plan "$@"
