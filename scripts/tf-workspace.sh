#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") <list|select|new|delete|show> [args...]

terraform workspace — manage state workspaces (if you use a remote backend that supports them).

Examples:
  $(basename "$0") list
  $(basename "$0") select default
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

tf_log "→ terraform workspace $*"
terraform_common_exec workspace "$@"
