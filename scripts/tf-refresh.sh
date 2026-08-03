#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options to terraform apply...]

Update Terraform state to match real infrastructure (terraform apply -refresh-only).
Loads config/secrets/secrets.env when present.

Examples:
  $(basename "$0")
  $(basename "$0") -auto-approve
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

tf_log "→ terraform apply -refresh-only (update state from AWS; no infra change)"
terraform_common_exec apply -refresh-only "$@"
