#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") <address> <id> [options...]

Import an existing AWS resource into Terraform state. Loads config/secrets/secrets.env when present.

Examples:
  $(basename "$0") 'aws_s3_bucket.site' my-bucket-name
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

tf_log "→ terraform import (bring existing AWS resources into state)"
terraform_common_exec import "$@"
