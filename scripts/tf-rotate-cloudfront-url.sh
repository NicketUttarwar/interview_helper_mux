#!/usr/bin/env bash
# One-off: CloudFront-only RSS URL replace. NEVER touches the S3 bucket.
#
# Deletes the current CloudFront distribution (old dxxxx.cloudfront.net/feed.xml
# dies) and creates a new distribution pointed at the existing private origin.
# S3 bucket / objects / prefixes / catalog are left alone. Refuses apply if the
# plan would touch aws_s3_bucket.origin.
#
# After success: secrets.env CF id + feed base are synced; feed.xml public URLs
# are rewritten; /feed.xml is invalidated on the NEW distribution. App publish
# and ./scripts/invalidate_podcast_cf.sh then target the new URL.
#
# Distinct from tf-podcast-rss-origin.sh (new bucket + new CF) and
# tf-empty-bucket.sh (S3 wipe only).
#
# Usage (from repo root — do not run casually):
#   ./scripts/tf-rotate-cloudfront-url.sh            # preview, then type CF id
#   ./scripts/tf-rotate-cloudfront-url.sh --yes      # skip prompts (still replaces)
#
# See terraform/README.md and docs/cross-cutting/podcast-rss-hosting.md.
# Prints Apple Podcasts Connect pass-through + empty-feed notice at the end.
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

CloudFront-only: delete the live RSS CloudFront distribution and create a new
one. NEVER empties, deletes, or recreates the S3 bucket.

  DELETE: current CloudFront (old https://dxxxx.cloudfront.net/feed.xml dies)
  KEEP:   S3 bucket + all objects (episodes, feed.xml, show art, catalogs)
  UPDATE: secrets.env PODCAST_CLOUDFRONT_DISTRIBUTION_ID + PODCAST_FEED_BASE_URL
          feed.xml self-link / episode public hosts → new CF
          invalidate /feed.xml on the NEW distribution

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
CUR_CF_DOMAIN="$(_tf_raw cloudfront_domain_name)"
CUR_PROJECT="$(_tf_raw project_name)"

if [[ -z "$CUR_BUCKET" || -z "$CUR_CF_ID" || -z "$CUR_FEED_URL" ]]; then
  tf_warn "Terraform outputs incomplete (bucket/cf/feed). Run ./scripts/tf-output.sh first."
  exit 1
fi

cat <<EOF
[$TF_SCRIPT_NAME] CloudFront-ONLY RSS URL replace (preview)

  Scope: DELETE old CloudFront + CREATE new CloudFront.
  S3:    NEVER touched (no empty, no delete, no recreate).

  KEEP (S3 — not modified):
    project_name:     ${CUR_PROJECT}
    s3_bucket:        ${CUR_BUCKET}

  DELETE (old CloudFront — public RSS URL dies):
    cloudfront_id:    ${CUR_CF_ID}
    cloudfront_domain:${CUR_CF_DOMAIN:-—}
    feed_base_url:    ${CUR_FEED_BASE}
    feed_url:         ${CUR_FEED_URL}

  CREATE:
    new CloudFront distribution → same bucket → new dxxxx.cloudfront.net/feed.xml

  After success this script will:
    1) sync secrets.env (PODCAST_CLOUDFRONT_DISTRIBUTION_ID + PODCAST_FEED_BASE_URL)
    2) rewrite feed.xml self-link / episode hosts to the new CF (S3 keys unchanged)
    3) invalidate /feed.xml on the NEW distribution
    4) print Apple pass-through + Spotify paste URL
    5) write terraform/archives/cf-url-rotate-*.json

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

tf_log "Planning CloudFront replacement (S3 must stay untouched)…"
PLAN_TEXT="$("$SCRIPT_DIR/tf-plan.sh" -replace="${CF_ADDR}" -no-color 2>&1 || true)"
printf '%s\n' "$PLAN_TEXT"

# Hard refuse any plan that would create/destroy/replace the origin bucket.
if printf '%s' "$PLAN_TEXT" | grep -E 'aws_s3_bucket\.origin' >/dev/null; then
  tf_warn "Plan mentions aws_s3_bucket.origin — refusing so S3 is never touched"
  exit 1
fi
if ! printf '%s' "$PLAN_TEXT" | grep -F "aws_cloudfront_distribution.podcast will be replaced" >/dev/null; then
  tf_warn "Plan did not mark ${CF_ADDR} for replacement; refusing"
  exit 1
fi

tf_log "Applying CloudFront replacement (S3 untouched)…"
"$SCRIPT_DIR/tf-apply.sh" -replace="${CF_ADDR}" -auto-approve
# tf-apply.sh already runs sync_podcast_tf_secrets.sh

NEW_CF_ID="$(_tf_raw cloudfront_distribution_id)"
NEW_FEED_URL="$(_tf_raw feed_url)"
NEW_FEED_BASE="$(_tf_raw feed_base_url)"
NEW_CF_DOMAIN="$(_tf_raw cloudfront_domain_name)"

if [[ -z "$NEW_CF_ID" || "$NEW_CF_ID" == "$CUR_CF_ID" ]]; then
  tf_warn "CloudFront id did not change after apply (still ${NEW_CF_ID:-empty}). Check terraform output."
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$ARCHIVE_DIR"
ARCHIVE_JSON="${ARCHIVE_DIR}/cf-url-rotate-${STAMP}.json"
CUR_BUCKET="$CUR_BUCKET" CUR_CF_ID="$CUR_CF_ID" CUR_FEED_URL="$CUR_FEED_URL" \
CUR_FEED_BASE="$CUR_FEED_BASE" CUR_CF_DOMAIN="${CUR_CF_DOMAIN:-}" CUR_PROJECT="$CUR_PROJECT" \
NEW_CF_ID="$NEW_CF_ID" NEW_FEED_URL="$NEW_FEED_URL" NEW_FEED_BASE="$NEW_FEED_BASE" \
NEW_CF_DOMAIN="${NEW_CF_DOMAIN:-}" \
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
            "purpose": "CloudFront-only: delete old CF RSS URL; create new CF on the same S3 bucket (S3 never touched)",
            "s3_bucket": os.environ["CUR_BUCKET"],
            "project_name": os.environ["CUR_PROJECT"],
            "s3_untouched": True,
            "deleted": {
                "cloudfront_distribution_id": os.environ["CUR_CF_ID"],
                "cloudfront_domain_name": os.environ.get("CUR_CF_DOMAIN") or None,
                "feed_base_url": os.environ["CUR_FEED_BASE"],
                "feed_url": os.environ["CUR_FEED_URL"],
            },
            "replacement": {
                "cloudfront_distribution_id": os.environ["NEW_CF_ID"],
                "cloudfront_domain_name": os.environ.get("NEW_CF_DOMAIN") or None,
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

tf_log "Rewriting feed.xml public hosts to the new CF URL and invalidating (S3 keys unchanged)…"
(
  cd "$REPO_ROOT"
  "$(_python)" - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
from interview_mux.podcast_rss.s3_publish import retarget_public_feed
from interview_mux.podcast_rss.settings import print_apple_passthrough_notice

result = retarget_public_feed(invalidate=True)
print(
    "Retargeted feed {feed_url} ({n} episode(s)); invalidation {inv} on {dist}".format(
        feed_url=result.get("feed_url") or "—",
        n=result.get("episodes_retargeted") or 0,
        inv=result.get("invalidation_id") or "—",
        dist=result.get("distribution_id") or "—",
    )
)
print_apple_passthrough_notice(result.get("feed_url") or "", include_feed=False)
PY
)

cat <<EOF
[$TF_SCRIPT_NAME] Done — CloudFront replaced; S3 bucket untouched.

  ── DELETED (old CloudFront) ──
  cloudfront_id:     ${CUR_CF_ID}
  cloudfront_domain: ${CUR_CF_DOMAIN:-—}
  feed_base_url:     ${CUR_FEED_BASE}
  feed_url:          ${CUR_FEED_URL}

  ── NEW (live now) ──
  cloudfront_id:     ${NEW_CF_ID}
  cloudfront_domain: ${NEW_CF_DOMAIN:-—}
  feed_base_url:     ${NEW_FEED_BASE}
  feed_url:          ${NEW_FEED_URL}

  ── UNCHANGED ──
  s3_bucket:         ${CUR_BUCKET}  (objects / prefixes / catalog kept)
  project_name:      ${CUR_PROJECT}

  ── SECRETS (synced) ──
  PODCAST_CLOUDFRONT_DISTRIBUTION_ID → ${NEW_CF_ID}
  PODCAST_FEED_BASE_URL              → ${NEW_FEED_BASE}

  ── RECORD ──
  ${ARCHIVE_JSON}

  ── NEXT ──
  1) Restart ./scripts/run.sh if the GUI server was already up (so G-Publish shows the new feed).
  2) App publish / ./scripts/invalidate_podcast_cf.sh now invalidate THIS new CF.
  3) Apple: use the pass-through below (needs ≥1 episode in feed).
  4) Spotify: paste the new feed_url at https://creators.spotify.com/dash/submit
     (no pass-through; plain RSS URL only).
EOF
# Always print Apple's pass-through next to the new public RSS URL.
print_apple_passthrough_notice "${NEW_FEED_URL}" 0
echo
echo "[$TF_SCRIPT_NAME] Spotify submit (plain feed URL, copy/paste):"
echo "  ${NEW_FEED_URL}"
echo "[$TF_SCRIPT_NAME] Spotify portal:"
echo "  https://creators.spotify.com/dash/submit"