#!/usr/bin/env bash
# Destroy every resource managed by this repo's Terraform configuration.
# Chains ./scripts/tf-plan.sh (destroy plan) and ./scripts/tf-apply.sh (apply plan).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

PLAN_FILE="${REPO_ROOT}/terraform/.destroy.tfplan"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

  Destroys ALL AWS resources defined in this stack (S3, CloudFront OAC, bucket policy, etc.).

  Flow (uses the same wrappers as normal operations):
    1) ./scripts/tf-plan.sh -destroy -out=<plan>   (preview)
    2) Confirmation (unless -y)
    3) ./scripts/tf-apply.sh <plan>                (apply destroy)

  Options:
    -y, --yes, -auto-approve   Skip the confirmation prompt (plan is still shown)
    --use-session              Restore live state from latest session backup before plan/apply (or USE_LATEST_SESSION=1)
    -h, --help                 Show this help

  Environment:
    TF_QUIET=1    Less [script] logging
    TF_TRACE=1    Shell trace (set -x)

  Use this after a failed apply or when you need to remove everything managed here.
EOF
}

AUTO_CONFIRM=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    -y | --yes | -auto-approve)
      AUTO_CONFIRM=true
      shift
      ;;
    --use-session)
      export USE_LATEST_SESSION=1
      tf_log "USE_LATEST_SESSION=1 (restore from latest session backup before destroy steps)"
      shift
      ;;
    *)
      tf_warn "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

tf_log "======== destroy-stack: tear down all Terraform-managed resources ========"
tf_log "Wrappers: tf-plan.sh (-destroy) → tf-apply.sh (saved plan)"
tf_log "Plan file (gitignored): $PLAN_FILE"

# Empty origin bucket first so destroy is not blocked by objects (even with force_destroy).
OLD_BUCKET="$(
  "$SCRIPT_DIR/tf-output.sh" -raw s3_bucket_id 2>/dev/null || true
)"
if [[ -n "${OLD_BUCKET}" ]]; then
  tf_log "Emptying origin bucket before destroy: ${OLD_BUCKET}"
  PYTHON="${REPO_ROOT}/.venv/bin/python"
  if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(command -v python3)"
  fi
  (
    cd "$REPO_ROOT"
    export EMPTY_BUCKET_NAME="$OLD_BUCKET"
    "$PYTHON" - <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))
from interview_mux.podcast_rss.s3_publish import empty_bucket
from interview_mux.podcast_rss.settings import resolve_publish_targets
bucket = os.environ["EMPTY_BUCKET_NAME"]
region = resolve_publish_targets().get("region") or "us-east-1"
n = empty_bucket(bucket, region=region)
print(f"Deleted {n} object(s) from s3://{bucket}")
PY
  ) || tf_warn "Bucket empty step failed — continuing; force_destroy may still succeed"
fi

rm -f "$PLAN_FILE"

tf_log "Step 1/2: Generating destroy plan (./scripts/tf-plan.sh -destroy -out=...)..."
"$SCRIPT_DIR/tf-plan.sh" -destroy -out="$PLAN_FILE" -input=false

if [[ "$AUTO_CONFIRM" != true ]]; then
  echo "" >&2
  echo "[$TF_SCRIPT_NAME] Review the Terraform plan above." >&2
  echo "[$TF_SCRIPT_NAME] To proceed with destroying all managed resources, type:  yes" >&2
  echo "[$TF_SCRIPT_NAME] To cancel, type anything else or press Ctrl+C." >&2
  read -r -p "[$TF_SCRIPT_NAME] Confirm destroy? [yes/NO]: " reply
  if [[ "${reply:-}" != "yes" ]]; then
    tf_log "Aborted — no changes applied. Removing plan file."
    rm -f "$PLAN_FILE"
    exit 1
  fi
else
  tf_log "Auto-confirm enabled (-y): skipping interactive prompt."
fi

tf_log "Step 2/2: Applying destroy plan (./scripts/tf-apply.sh <planfile>)..."
"$SCRIPT_DIR/tf-apply.sh" "$PLAN_FILE"

rm -f "$PLAN_FILE"
tf_log "Destroy complete. Removed plan file."
tf_log "Tip: ./scripts/tf-output.sh (may be empty if state cleared) or ./scripts/tf-state.sh list"
