#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options to terraform init...]

Initialize the Terraform working directory (providers, modules, backend).
Loads config/secrets/secrets.env when present.

Examples:
  $(basename "$0")
  $(basename "$0") -upgrade
  $(basename "$0") -reconfigure
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

tf_log "→ terraform init (backend, providers, modules)"
terraform_common_exec init "$@"
