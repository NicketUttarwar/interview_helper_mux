#!/usr/bin/env bash
# ONE-OFF (do not run casually): archive the live War Room RSS URL, then create a
# brand-new CloudFront feed URL for a future Apple Podcast show.
#
# Assumes S3 + CloudFront are already deployed and tracked in
# terraform/state/terraform.tfstate.
#
# What this does:
#   1) Records the current feed URL / CF ID / bucket under terraform/archives/
#      (old CloudFront URL stays live in AWS as the archive — not destroyed).
#   2) Removes the managed origin stack from Terraform *state only* (orphan),
#      so Terraform will create a fresh S3 bucket + OAC + CloudFront distribution
#      → a NEW dxxxx.cloudfront.net /feed.xml URL.
#   3) Advances project_name / s3_bucket_name in config/terraform.tfvars and
#      podcast.s3_bucket + podcast.podcast_guid in config/app.defaults.json.
#   4) terraform apply → sync secrets → seed empty feed on the new origin.
#
# What this does NOT do:
#   - Destroy or empty the archived bucket / old CloudFront (archive stays up).
#   - Submit anything to Apple — you paste the NEW feed URL later.
#   - Use AWS CLI (wrappers + boto3 seed only).
#
# Usage (later, from repo root):
#   ./scripts/tf-rotate-rss-url.sh
#       → prints preview, then asks yes/no before changing anything
#   ./scripts/tf-rotate-rss-url.sh \
#       --new-project the_war_room_002 \
#       --new-bucket the-war-room-rss-002 \
#       --new-show-title "The War Room"
#
# See terraform/archives/README.md and terraform/README.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

ARCHIVE_DIR="${TF_DIR}/archives"
APP_DEFAULTS="${REPO_ROOT}/config/app.defaults.json"
TFVARS="${REPO_ROOT}/config/terraform.tfvars"
TFVARS_EXAMPLE="${REPO_ROOT}/config/terraform.tfvars.example"

AUTO_CONFIRM=false
NEW_PROJECT=""
NEW_BUCKET=""
NEW_SHOW_TITLE=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Archive the current podcast RSS CloudFront URL (leave it live in AWS), then
create a new S3 + CloudFront stack so Apple Podcasts can be given a fresh feed.

Always prints a preview first, then asks yes/no before making changes.

Options:
  --new-project NAME     Logical Terraform project_name (default: bump _001→_002)
  --new-bucket NAME      New private origin bucket (must match app podcast.s3_bucket)
  --new-show-title TEXT  CloudFront comment / show title (default: keep current)
  -y, --yes              Skip the yes/no prompt (non-interactive)
  -h, --help             Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    --new-project)
      NEW_PROJECT="${2:?--new-project requires a value}"
      shift 2
      ;;
    --new-bucket)
      NEW_BUCKET="${2:?--new-bucket requires a value}"
      shift 2
      ;;
    --new-show-title)
      NEW_SHOW_TITLE="${2:?--new-show-title requires a value}"
      shift 2
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

# --- helpers ---------------------------------------------------------------

_require_file() {
  local path=$1
  if [[ ! -f "$path" ]]; then
    tf_warn "Required file missing: $path"
    exit 1
  fi
}

_tf_raw() {
  "$SCRIPT_DIR/tf-output.sh" -raw "$1" 2>/dev/null || true
}

_bump_project() {
  local cur=$1
  if [[ "$cur" =~ ^(.*_)([0-9]+)$ ]]; then
    local prefix="${BASH_REMATCH[1]}"
    local n="${BASH_REMATCH[2]}"
    # strip leading zeros for arithmetic, then zero-pad to same width
    local width=${#n}
    local next=$((10#$n + 1))
    printf "%s%0${width}d" "$prefix" "$next"
    return 0
  fi
  printf "%s_002" "$cur"
}

_hyphenate() {
  echo "${1//_/-}"
}

# --- gather current inventory ---------------------------------------------

terraform_common_source_aws_env
_require_file "$TF_STATE_LIVE"
_require_file "$APP_DEFAULTS"

CUR_PROJECT="$(_tf_raw project_name)"
CUR_BUCKET="$(_tf_raw s3_bucket_id)"
CUR_CF_ID="$(_tf_raw cloudfront_distribution_id)"
CUR_CF_DOMAIN="$(_tf_raw cloudfront_domain_name)"
CUR_FEED_BASE="$(_tf_raw feed_base_url)"
CUR_FEED_URL="$(_tf_raw feed_url)"
CUR_SHOW_TITLE=""
if [[ -f "$TFVARS" ]]; then
  CUR_SHOW_TITLE="$(grep -E '^[[:space:]]*show_title[[:space:]]*=' "$TFVARS" | head -1 | sed -E 's/.*=[[:space:]]*"([^"]*)".*/\1/' || true)"
fi
if [[ -z "$CUR_SHOW_TITLE" ]]; then
  CUR_SHOW_TITLE="The War Room"
fi

if [[ -z "$CUR_BUCKET" || -z "$CUR_CF_ID" || -z "$CUR_FEED_URL" ]]; then
  tf_warn "Terraform outputs incomplete (bucket/cf/feed). Run ./scripts/tf-init.sh && ./scripts/tf-output.sh first."
  exit 1
fi

if [[ -z "$NEW_PROJECT" ]]; then
  NEW_PROJECT="$(_bump_project "${CUR_PROJECT:-the_war_room_001}")"
fi
if [[ -z "$NEW_BUCKET" ]]; then
  NEW_BUCKET="$(_hyphenate "$NEW_PROJECT")-rss-001"
  # Prefer parallel naming: the-war-room-rss-002 when project is the_war_room_002
  if [[ "$NEW_PROJECT" =~ _([0-9]+)$ ]]; then
    local_n="${BASH_REMATCH[1]}"
    NEW_BUCKET="the-war-room-rss-${local_n}"
  fi
fi
if [[ -z "$NEW_SHOW_TITLE" ]]; then
  NEW_SHOW_TITLE="$CUR_SHOW_TITLE"
fi

if [[ "$NEW_BUCKET" == "$CUR_BUCKET" ]]; then
  tf_warn "New bucket must differ from archived bucket ($CUR_BUCKET) so archive objects stay intact."
  exit 1
fi
if [[ "$NEW_PROJECT" == "$CUR_PROJECT" ]]; then
  tf_warn "New project_name must differ from current ($CUR_PROJECT) so OAC/CloudFront names do not collide."
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE_JSON="${ARCHIVE_DIR}/rss-rotate-${STAMP}.json"
NEW_GUID="$(
  PYTHON="${REPO_ROOT}/.venv/bin/python"
  if [[ ! -x "$PYTHON" ]]; then PYTHON="$(command -v python3)"; fi
  "$PYTHON" - <<'PY'
import uuid
print(uuid.uuid4())
PY
)"

cat <<EOF
[$TF_SCRIPT_NAME] RSS URL rotation plan (preview)

  ARCHIVE (left live in AWS, removed from Terraform state):
    project_name:    ${CUR_PROJECT}
    s3_bucket:       ${CUR_BUCKET}
    cloudfront_id:   ${CUR_CF_ID}
    feed_base_url:   ${CUR_FEED_BASE}
    feed_url:        ${CUR_FEED_URL}
    archive_record:  ${ARCHIVE_JSON}

  NEW STACK (created by terraform apply):
    project_name:    ${NEW_PROJECT}
    s3_bucket:       ${NEW_BUCKET}
    show_title:      ${NEW_SHOW_TITLE}
    podcast_guid:    ${NEW_GUID}   (new Apple show identity)

  After success:
    - Old Apple/subscribers keep ${CUR_FEED_URL} (archive).
    - Submit the NEW feed URL from ./scripts/tf-output.sh feed_url to Apple Podcasts.
    - Commit updated terraform/state/terraform.tfstate + archive JSON.
EOF

if [[ "$AUTO_CONFIRM" != true ]]; then
  echo >&2
  read -r -p "[$TF_SCRIPT_NAME] Proceed with rotation? [y/N] " reply
  case "${reply}" in
    y | Y | yes | YES)
      ;;
    *)
      tf_log "Cancelled; nothing changed."
      exit 0
      ;;
  esac
fi

mkdir -p "$ARCHIVE_DIR"

# --- 1) write archive record ----------------------------------------------

PYTHON="${REPO_ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

ARCHIVE_JSON="$ARCHIVE_JSON" \
CUR_PROJECT="$CUR_PROJECT" \
CUR_BUCKET="$CUR_BUCKET" \
CUR_CF_ID="$CUR_CF_ID" \
CUR_CF_DOMAIN="$CUR_CF_DOMAIN" \
CUR_FEED_BASE="$CUR_FEED_BASE" \
CUR_FEED_URL="$CUR_FEED_URL" \
CUR_SHOW_TITLE="$CUR_SHOW_TITLE" \
NEW_PROJECT="$NEW_PROJECT" \
NEW_BUCKET="$NEW_BUCKET" \
NEW_SHOW_TITLE="$NEW_SHOW_TITLE" \
NEW_GUID="$NEW_GUID" \
STAMP="$STAMP" \
"$PYTHON" - <<'PY'
import json
import os
from pathlib import Path

doc = {
    "version": 1,
    "rotated_at": os.environ["STAMP"],
    "purpose": "Archive prior RSS CloudFront URL; new stack for a fresh Apple Podcast feed",
    "archived": {
        "project_name": os.environ["CUR_PROJECT"],
        "s3_bucket": os.environ["CUR_BUCKET"],
        "cloudfront_distribution_id": os.environ["CUR_CF_ID"],
        "cloudfront_domain_name": os.environ["CUR_CF_DOMAIN"],
        "feed_base_url": os.environ["CUR_FEED_BASE"],
        "feed_url": os.environ["CUR_FEED_URL"],
        "show_title": os.environ["CUR_SHOW_TITLE"],
        "note": "Resources remain in AWS; removed from Terraform state so the old URL stays reachable.",
    },
    "replacement": {
        "project_name": os.environ["NEW_PROJECT"],
        "s3_bucket": os.environ["NEW_BUCKET"],
        "show_title": os.environ["NEW_SHOW_TITLE"],
        "podcast_guid": os.environ["NEW_GUID"],
    },
}
path = Path(os.environ["ARCHIVE_JSON"])
path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
print(path)
PY

tf_log "Wrote archive record: $ARCHIVE_JSON"

# --- 2) orphan managed origin stack from state (do not destroy in AWS) ----

# Order: distribution → policy → OAC → bucket satellites → bucket.
# Data sources stay in state; they are re-read on the next apply.
ORPHAN_ADDRS=(
  "aws_cloudfront_distribution.podcast"
  "aws_s3_bucket_policy.origin"
  "aws_cloudfront_origin_access_control.origin"
  "aws_s3_bucket_public_access_block.origin"
  "aws_s3_bucket_ownership_controls.origin"
  "aws_s3_bucket.origin"
)

tf_log "Removing archived resources from Terraform state (AWS objects kept)…"
for addr in "${ORPHAN_ADDRS[@]}"; do
  if "$SCRIPT_DIR/tf-state.sh" list 2>/dev/null | grep -qx "$addr"; then
    tf_log "  state rm $addr"
    "$SCRIPT_DIR/tf-state.sh" rm -lock=false "$addr" >/dev/null
  else
    tf_log "  skip (not in state): $addr"
  fi
done

# --- 3) retarget tfvars + app.defaults ------------------------------------

tf_log "Updating config/terraform.tfvars → project=${NEW_PROJECT} bucket=${NEW_BUCKET}"
if [[ ! -f "$TFVARS" ]]; then
  if [[ -f "$TFVARS_EXAMPLE" ]]; then
    cp "$TFVARS_EXAMPLE" "$TFVARS"
  else
    tf_warn "Missing $TFVARS and example; cannot continue"
    exit 1
  fi
fi

NEW_PROJECT="$NEW_PROJECT" NEW_BUCKET="$NEW_BUCKET" NEW_SHOW_TITLE="$NEW_SHOW_TITLE" \
TFVARS="$TFVARS" "$PYTHON" - <<'PY'
from pathlib import Path
import os
import re

path = Path(os.environ["TFVARS"])
text = path.read_text(encoding="utf-8")
subs = {
    "project_name": os.environ["NEW_PROJECT"],
    "s3_bucket_name": os.environ["NEW_BUCKET"],
    "show_title": os.environ["NEW_SHOW_TITLE"],
}
for key, val in subs.items():
    pat = re.compile(rf'^(\s*{re.escape(key)}\s*=\s*")[^"]*("\s*)$', re.M)
    if pat.search(text):
        text = pat.sub(rf'\1{val}\2', text)
    else:
        text = text.rstrip() + f'\n{key} = "{val}"\n'
path.write_text(text, encoding="utf-8")
PY

tf_log "Updating config/app.defaults.json podcast.s3_bucket + podcast.podcast_guid"
APP_DEFAULTS="$APP_DEFAULTS" NEW_BUCKET="$NEW_BUCKET" NEW_GUID="$NEW_GUID" \
"$PYTHON" - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["APP_DEFAULTS"])
doc = json.loads(path.read_text(encoding="utf-8"))
podcast = doc.setdefault("podcast", {})
podcast["s3_bucket"] = os.environ["NEW_BUCKET"]
podcast["podcast_guid"] = os.environ["NEW_GUID"]
# Keep project_name aligned when present.
if "project_name" in podcast:
    # Derive from bucket the-war-room-rss-NNN → leave explicit project in tfvars;
    # mirror hyphenated logical name if it looks like our convention.
    pass
path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
PY

# Align podcast.project_name when the key exists.
APP_DEFAULTS="$APP_DEFAULTS" NEW_PROJECT="$NEW_PROJECT" "$PYTHON" - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["APP_DEFAULTS"])
doc = json.loads(path.read_text(encoding="utf-8"))
podcast = doc.get("podcast")
if isinstance(podcast, dict) and "project_name" in podcast:
    podcast["project_name"] = os.environ["NEW_PROJECT"]
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
PY

# --- 4) create new stack + seed -------------------------------------------

tf_log "Applying new S3 + CloudFront stack…"
"$SCRIPT_DIR/tf-apply.sh" -auto-approve

NEW_FEED_URL="$(_tf_raw feed_url)"
NEW_FEED_BASE="$(_tf_raw feed_base_url)"
NEW_CF_ID="$(_tf_raw cloudfront_distribution_id)"

tf_log "Seeding empty feed on new origin…"
(
  cd "$REPO_ROOT"
  "$PYTHON" scripts/seed_podcast_origin.py
)

# Enrich archive record with post-apply outputs.
ARCHIVE_JSON="$ARCHIVE_JSON" NEW_FEED_URL="$NEW_FEED_URL" NEW_FEED_BASE="$NEW_FEED_BASE" \
NEW_CF_ID="$NEW_CF_ID" NEW_BUCKET="$NEW_BUCKET" "$PYTHON" - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["ARCHIVE_JSON"])
doc = json.loads(path.read_text(encoding="utf-8"))
doc["replacement"]["cloudfront_distribution_id"] = os.environ.get("NEW_CF_ID") or None
doc["replacement"]["feed_base_url"] = os.environ.get("NEW_FEED_BASE") or None
doc["replacement"]["feed_url"] = os.environ.get("NEW_FEED_URL") or None
doc["replacement"]["s3_bucket"] = os.environ.get("NEW_BUCKET") or doc["replacement"].get("s3_bucket")
path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
PY

cat <<EOF
[$TF_SCRIPT_NAME] Rotation complete.

  Archived feed (still live):  ${CUR_FEED_URL}
  New feed (Apple submit):     ${NEW_FEED_URL}
  New CloudFront ID:           ${NEW_CF_ID}
  New S3 bucket:               ${NEW_BUCKET}
  New podcast GUID:            ${NEW_GUID}
  Archive record:              ${ARCHIVE_JSON}

Next:
  1) Commit terraform/state/terraform.tfstate, ${ARCHIVE_JSON}, and config/app.defaults.json
  2) Keep config/terraform.tfvars gitignored but backed up locally
  3) Submit ${NEW_FEED_URL} as a new show in Apple Podcasts Connect
  4) Leave the archived distribution alone unless you intentionally retire it later
EOF
