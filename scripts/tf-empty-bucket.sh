#!/usr/bin/env bash
# Empty the Terraform-managed podcast S3 bucket without destroying infrastructure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Delete every current object, object version, and delete marker from the
Terraform-managed podcast S3 bucket. The bucket and CloudFront stack remain.

Options:
  -y, --yes     Skip the destructive confirmation prompt
  -h, --help    Show this help

The bucket name comes from Terraform output s3_bucket_id. AWS credentials are
loaded from config/secrets/secrets.env by the standard Terraform wrapper.
EOF
}

AUTO_CONFIRM=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    -y | --yes)
      AUTO_CONFIRM=true
      shift
      ;;
    *)
      tf_warn "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

terraform_common_source_aws_env
BUCKET="$("$SCRIPT_DIR/tf-output.sh" -raw s3_bucket_id)"
if [[ -z "$BUCKET" ]]; then
  tf_warn "Terraform output s3_bucket_id is empty; refusing to continue"
  exit 1
fi

if [[ "$AUTO_CONFIRM" != true ]]; then
  echo "[$TF_SCRIPT_NAME] This permanently deletes EVERYTHING in s3://${BUCKET}." >&2
  read -r -p "[$TF_SCRIPT_NAME] Type the bucket name to confirm: " reply
  if [[ "$reply" != "$BUCKET" ]]; then
    tf_log "Confirmation did not match; bucket was not changed."
    exit 1
  fi
fi

PYTHON="${REPO_ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

tf_log "Emptying Terraform-managed bucket: s3://${BUCKET}"
(
  cd "$REPO_ROOT"
  export EMPTY_BUCKET_NAME="$BUCKET"
  "$PYTHON" - <<'PY'
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))

from interview_mux.podcast_rss.s3_publish import empty_bucket
from interview_mux.podcast_rss.settings import resolve_publish_targets

bucket = os.environ["EMPTY_BUCKET_NAME"]
region = resolve_publish_targets().get("region") or "us-east-1"
deleted = empty_bucket(bucket, region=region)
print(f"Deleted {deleted} object version(s) and marker(s) from s3://{bucket}")
PY
)
tf_log "Bucket is empty; Terraform infrastructure was preserved."
