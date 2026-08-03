#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options to terraform apply...]

Apply changes. Loads config/secrets/secrets.env when present.
On success, upserts PODCAST_* keys into secrets.env via sync_podcast_tf_secrets.sh
(skipped for destroy plan applies).

Examples:
  $(basename "$0")
  $(basename "$0") -auto-approve
  $(basename "$0") tfplan
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

tf_log "→ terraform apply (podcast RSS stack: S3 + CloudFront OAC)"
terraform_common_exec apply "$@"
ec=$?
if [[ $ec -ne 0 ]]; then
  exit "$ec"
fi

# Skip secrets sync when applying a saved destroy plan (destroy-stack.sh).
skip_sync=0
for arg in "$@"; do
  case "$arg" in
    *.tfplan | */.destroy.tfplan | .destroy.tfplan)
      skip_sync=1
      ;;
  esac
done
if [[ "$skip_sync" -eq 1 ]]; then
  tf_log "Skipping PODCAST_* secrets sync (looks like a saved plan / destroy apply)"
  exit 0
fi

if [[ -x "${SCRIPT_DIR}/sync_podcast_tf_secrets.sh" ]]; then
  tf_log "Syncing Terraform outputs → config/secrets/secrets.env"
  "${SCRIPT_DIR}/sync_podcast_tf_secrets.sh"
else
  tf_warn "sync_podcast_tf_secrets.sh missing — PODCAST_* not updated"
fi
