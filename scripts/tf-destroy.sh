#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options to terraform destroy...]

Destroy all resources in this stack. Loads config/secrets/secrets.env when present.

By default Terraform prompts for confirmation. Use -auto-approve only when intended.

For a guided flow (destroy plan file + apply), use: ./scripts/destroy-stack.sh

Examples:
  $(basename "$0")
  $(basename "$0") -auto-approve
  $(basename "$0") -target=aws_s3_bucket.site
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

tf_log "→ terraform destroy (tear down resources; see also ./scripts/destroy-stack.sh)"
terraform_common_exec destroy "$@"
