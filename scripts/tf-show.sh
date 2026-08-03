#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [path to plan file or state options...]

terraform show — inspect state or a saved plan file.

Examples:
  $(basename "$0")
  $(basename "$0") tfplan
  $(basename "$0") -json
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

tf_log "→ terraform show (state or saved plan)"
terraform_common_exec show "$@"
