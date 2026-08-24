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

After terraform output, prints the Apple Podcasts Connect pass-through for
the live feed_url on stderr so ``-raw`` stdout stays machine-readable.

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
set +e
terraform_common_exec output "$@"
ec=$?
set -e
# Always show Apple's pass-through next to the live feed URL (stderr so
# ``-raw feed_url`` stdout remains a single machine-readable line).
# Direct terraform output — do not recurse through this wrapper.
FEED_URL="$(cd "$REPO_ROOT" && terraform -chdir="$TF_DIR" output -raw feed_url 2>/dev/null || true)"
print_apple_passthrough_notice "${FEED_URL}" >&2
exit "$ec"
