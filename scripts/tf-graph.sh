#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options to terraform graph...]

Output dependency graph (Graphviz DOT). Loads config/secrets/secrets.env when present.

Examples:
  $(basename "$0") | dot -Tpng >graph.png
  $(basename "$0") -type=apply
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

tf_log "→ terraform graph (dependency graph DOT)"
terraform_common_exec graph "$@"
