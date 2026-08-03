#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options to terraform output...]

Show output values (DNS, CloudFront IDs, bucket name, etc.).
Loads config/secrets/secrets.env when present.

Examples:
  $(basename "$0")
  $(basename "$0") -json
  $(basename "$0") -raw s3_bucket_id
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

tf_log "→ terraform output (DNS, IDs, bucket name, etc.)"
terraform_common_exec output "$@"
