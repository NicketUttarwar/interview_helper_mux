#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") <state subcommand> [args...]

terraform state — list, mv, rm, pull, push, replace-provider, etc.

Examples:
  $(basename "$0") list
  $(basename "$0") show 'aws_s3_bucket.site'
  $(basename "$0") mv OLD_ADDRESS NEW_ADDRESS
EOF
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi
if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

tf_log "→ terraform state ${*:-}"
terraform_common_exec state "$@"
