#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") <lock-id>

Release a stuck state lock (e.g. after a crashed apply). Use only when no other
Terraform run is active. Loads config/secrets/secrets.env when present.

Examples:
  $(basename "$0") 1234567890
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

tf_log "→ terraform force-unlock $1 (only if no other Terraform holds the lock)"
terraform_common_exec force-unlock "$@"
