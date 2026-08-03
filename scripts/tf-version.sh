#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options to terraform version...]

Print Terraform and provider version requirements. Does not require config/secrets/secrets.env.

Examples:
  $(basename "$0")
  $(basename "$0") -json
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

tf_log "→ terraform version (does not load config/secrets/secrets.env)"
terraform_common_exec_local version "$@"
