#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options to terraform console...]

Interactive console to evaluate Terraform expressions. Loads config/secrets/secrets.env when present.
Passes -var-file for config/terraform.tfvars when that file exists (see scripts/lib/terraform-common.sh).

Examples:
  $(basename "$0")
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

tf_log "→ terraform console (interactive expressions)"
terraform_common_exec console "$@"
