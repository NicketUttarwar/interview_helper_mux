#!/usr/bin/env bash
# One-off: replace the public CloudFront RSS URL. Same S3 bucket.
#
# Deletes the current CloudFront distribution (old dxxxx.cloudfront.net/feed.xml
# dies) and creates a new distribution pointed at the existing private origin.
# S3 objects, prefixes, and catalog stay. App + invalidate_podcast_cf.sh pick
# up the new URL from secrets.env after this script syncs Terraform outputs.
#
# Distinct from tf-podcast-rss-origin.sh, which creates a *new bucket* as well.
#
# Usage (from repo root — do not run casually):
#   ./scripts/tf-rotate-cloudfront-url.sh            # preview, then type CF id
#   ./scripts/tf-rotate-cloudfront-url.sh --yes      # skip prompts (still replaces)
#
# See terraform/README.md and docs/cross-cutting/podcast-rss-hosting.md.
# After a new CloudFront URL, print_apple_passthrough_notice always emits the
# Apple Podcasts Connect pass-through (encoded submitfeed) plus the empty-feed
# notice. Do not submit an empty seed feed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

ARCHIVE_DIR="${TF_DIR}/archives"
CF_ADDR="aws_cloudfront_distribution.podcast"
AUTO_CONFIRM=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Replace the CloudFront distribution so the public RSS URL changes.
Keeps the Terraform-managed S3 bucket and its objects.

  The old https://dxxxx.cloudfront.net/feed.xml is DELETED (not archived).
  A new distribution is created in front of the same bucket.
  secrets.env PODCAST_CLOUDFRONT_DISTRIBUTION_ID + PODCAST_FEED_BASE_URL
  are rewritten so the app and ./scripts/invalidate_podcast_cf.sh target
  the new URL.

Options:
  -y, --yes     Skip the confirmation prompt
  -h, --help    Show this help

CloudFront disable+delete often takes 10–20 minutes. Do not interrupt apply.
EOF
}

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

_python() {
  local py="${REPO_ROOT}/.venv/bin/python"
  if [[ ! -x "$py" ]]; then
    py="$(command -v python3)"
  fi
  echo "$py"
}

_tf_raw() {
  "$SCRIPT_DIR/tf-output.sh" -raw "$1" 2>/dev/null || true
}

terraform_common_source_aws_env
if [[ ! -f "$TF_STATE_LIVE" ]]; then
  tf_warn "Terraform state missing at $TF_STATE_LIVE — run ./scripts/tf-init.sh first"
  exit 1
fi

CUR_BUCKET="$(_tf_raw s3_bucket_id)"
CUR_CF_ID="$(_tf_raw cloudfront_distribution_id)"
CUR_FEED_URL="$(_tf_raw feed_url)"
CUR_FEED_BASE="$(_tf_raw feed_base_url)"
CUR_PROJECT="$(_tf_raw project_name)"

if [[ -z "$CUR_BUCKET" || -z "$CUR_CF_ID" || -z "$CUR_FEED_URL" ]]; then
  tf_warn "Terraform outputs incomplete (bucket/cf/feed). Run ./scripts/tf-output.sh first."
  exit 1
fi

cat <<EOF
[$TF_SCRIPT_NAME] REPLACE CloudFront RSS URL (preview)

  This DELETES the current public feed URL. It is not left live.
  The S3 origin is unchanged.

  KEEP (S3 origin + objects):
    project_name:  ${CUR_PROJECT}
    s3_bucket:     ${CUR_BUCKET}

  DELETE (old RSS URL):
    cloudfront_id: ${CUR_CF_ID}
    feed_url:      ${CUR_FEED_URL}

  CREATE:
    new CloudFront distribution → same bucket → new dxxxx.cloudfront.net/feed.xml

  After success:
    - secrets.env is synced to the new CF id + feed base
    - feed.xml self-link is rewritten to the new URL
    - ./scripts/invalidate_podcast_cf.sh and the app invalidate the NEW url
    - Submit the new feed URL to Apple / Spotify if the show is listed
      (print_apple_passthrough_notice prints the Connect pass-through)

  CloudFront disable+delete often takes 10–20 minutes. Do not interrupt.
EOF

if [[ "$AUTO_CONFIRM" != true ]]; then
  echo >&2
  read -r -p "[$TF_SCRIPT_NAME] Type the current CloudFront distribution ID (${CUR_CF_ID}) to confirm: " reply
  if [[ "$reply" != "$CUR_CF_ID" ]]; then
    tf_log "Confirmation did not match; nothing changed."
    exit 1
  fi
fi

tf_log "Planning CloudFront replacement (S3 must stay)…"
PLAN_TEXT="$("$SCRIPT_DIR/tf-plan.sh" -replace="${CF_ADDR}" -no-color 2>&1 || true)"
printf '%s\n' "$PLAN_TEXT"

if printf '%s' "$PLAN_TEXT" | grep -E '^[[:space:]]*# aws_s3_bucket\.origin ' >/dev/null; then
  tf_warn "Plan touches aws_s3_bucket.origin — refusing so the bucket is not recreated"
  exit 1
fi
if ! printf '%s' "$PLAN_TEXT" | grep -F "aws_cloudfront_distribution.podcast will be replaced" >/dev/null; then
  tf_warn "Plan did not mark ${CF_ADDR} for replacement; refusing"
  exit 1
fi

tf_log "Applying CloudFront replacement…"
"$SCRIPT_DIR/tf-apply.sh" -replace="${CF_ADDR}" -auto-approve
# tf-apply.sh already runs sync_podcast_tf_secrets.sh

NEW_CF_ID="$(_tf_raw cloudfront_distribution_id)"
NEW_FEED_URL="$(_tf_raw feed_url)"
NEW_FEED_BASE="$(_tf_raw feed_base_url)"

if [[ -z "$NEW_CF_ID" || "$NEW_CF_ID" == "$CUR_CF_ID" ]]; then
  tf_warn "CloudFront id did not change after apply (still ${NEW_CF_ID:-empty}). Check terraform output."
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$ARCHIVE_DIR"
ARCHIVE_JSON="${ARCHIVE_DIR}/cf-url-rotate-${STAMP}.json"
CUR_BUCKET="$CUR_BUCKET" CUR_CF_ID="$CUR_CF_ID" CUR_FEED_URL="$CUR_FEED_URL" \
CUR_FEED_BASE="$CUR_FEED_BASE" CUR_PROJECT="$CUR_PROJECT" \
NEW_CF_ID="$NEW_CF_ID" NEW_FEED_URL="$NEW_FEED_URL" NEW_FEED_BASE="$NEW_FEED_BASE" \
STAMP="$STAMP" ARCHIVE_JSON="$ARCHIVE_JSON" \
"$(_python)" - <<'PY'
import json, os
from pathlib import Path
Path(os.environ["ARCHIVE_JSON"]).write_text(
    json.dumps(
        {
            "version": 1,
            "action": "rotate_cloudfront_url",
            "created_at": os.environ["STAMP"],
            "purpose": "Delete old CloudFront RSS URL; create a new distribution on the same S3 bucket",
            "s3_bucket": os.environ["CUR_BUCKET"],
            "project_name": os.environ["CUR_PROJECT"],
            "deleted": {
                "cloudfront_distribution_id": os.environ["CUR_CF_ID"],
                "feed_base_url": os.environ["CUR_FEED_BASE"],
                "feed_url": os.environ["CUR_FEED_URL"],
            },
            "replacement": {
                "cloudfront_distribution_id": os.environ["NEW_CF_ID"],
                "feed_base_url": os.environ["NEW_FEED_BASE"],
                "feed_url": os.environ["NEW_FEED_URL"],
            },
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print(os.environ["ARCHIVE_JSON"])
PY

tf_log "Rewriting feed.xml to the new public URL and invalidating…"
(
  cd "$REPO_ROOT"
  "$(_python)" - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
from interview_mux.podcast_rss.s3_publish import retarget_public_feed

result = retarget_public_feed(invalidate=True)
print(
    "Retargeted feed {feed_url} ({n} episode(s)); invalidation {inv} on {dist}".format(
        feed_url=result.get("feed_url") or "—",
        n=result.get("episodes_retargeted") or 0,
        inv=result.get("invalidation_id") or "—",
        dist=result.get("distribution_id") or "—",
    )
)
from interview_mux.podcast_rss.settings import print_apple_passthrough_notice
print_apple_passthrough_notice(result.get("feed_url") or "", include_feed=False)
PY
)

cat <<EOF
[$TF_SCRIPT_NAME] Done.

  Old feed (deleted): ${CUR_FEED_URL}
  New feed:           ${NEW_FEED_URL}
  S3 bucket (same):   ${CUR_BUCKET}
  Record:             ${ARCHIVE_JSON}

  App publish and ./scripts/invalidate_podcast_cf.sh now target the new URL
  (PODCAST_FEED_BASE_URL / PODCAST_CLOUDFRONT_DISTRIBUTION_ID in secrets.env).
  Restart ./scripts/run.sh if a server was already up, then G-Publish as usual.
EOF
# Always print Apple's pass-through next to the new public RSS URL.
print_apple_passthrough_notice "${NEW_FEED_URL}" 0
