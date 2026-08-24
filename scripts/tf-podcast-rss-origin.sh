#!/usr/bin/env bash
# Manage podcast RSS origins (S3 private origin + CloudFront feed URL).
#
# Default (--create): stand up a *new* S3 bucket + CloudFront distribution so
# Apple / other directories can be given a fresh feed URL. The previously managed
# stack is archived (left live in AWS, removed from Terraform state only) — it
# is NOT destroyed. App config (app.defaults + secrets) is retargeted to the new
# origin. A registry + local ASSETS binding distinguish old vs new shows.
#
# --delete: retire one specific archived CloudFront distribution (by ID or URL)
# after heavy confirmation. Use this later to free an old Apple feed URL; create
# a replacement with the default mode when you are ready.
#
# --list: print the origin registry (easy copy-paste of distribution IDs / URLs).
#
# Does NOT:
#   - Submit anything to Apple
#   - Use AWS CLI (wrappers + boto3 only)
#   - Destroy the active Terraform-managed origin via --delete (refuse by default)
#
# Usage (from repo root — do not run casually):
#   ./scripts/tf-podcast-rss-origin.sh
#   ./scripts/tf-podcast-rss-origin.sh --create \
#       --new-project the_war_room_002 \
#       --new-bucket the-war-room-rss-002 \
#       --new-show-title "The War Room"
#   ./scripts/tf-podcast-rss-origin.sh --list
#   ./scripts/tf-podcast-rss-origin.sh --delete --distribution-id EXXXXXXXXXXXXX
#   ./scripts/tf-podcast-rss-origin.sh --delete --feed-url https://dxxxx.cloudfront.net/feed.xml
#
# Formerly: scripts/tf-rotate-rss-url.sh
# Same-bucket CloudFront URL only (delete old CF, keep S3):
#   ./scripts/tf-rotate-cloudfront-url.sh
# See terraform/archives/README.md and terraform/README.md.
# Whenever a new feed URL is printed, also print the Apple Podcasts Connect
# pass-through (print_apple_passthrough_notice). Apple still requires ≥1 episode.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

ARCHIVE_DIR="${TF_DIR}/archives"
ORIGINS_REGISTRY="${ARCHIVE_DIR}/podcast-origins.json"
LOCAL_ORIGINS_ROOT="${REPO_ROOT}/ASSETS/podcast_origins"
APP_DEFAULTS="${REPO_ROOT}/config/app.defaults.json"
TFVARS="${REPO_ROOT}/config/terraform.tfvars"
TFVARS_EXAMPLE="${REPO_ROOT}/config/terraform.tfvars.example"

MODE="create" # create | delete | list
AUTO_CONFIRM=false
NEW_PROJECT=""
NEW_BUCKET=""
NEW_SHOW_TITLE=""
DELETE_DIST_ID=""
DELETE_FEED_URL=""
DELETE_ALSO_BUCKET=false
DELETE_ALLOW_ACTIVE=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Manage podcast RSS origins: create a new S3 + CloudFront feed (default), list
known origins, or delete one specific archived CloudFront URL.

Modes:
  (default) / --create   Create a new RSS feed URL + S3 bucket.
                         Archives the previous Terraform-managed stack
                         (left live in AWS; removed from state only).
  --list                 Print terraform/archives/podcast-origins.json
                         (distribution IDs + feed URLs for copy-paste).
  --delete               Delete ONE specific CloudFront distribution
                         (and optionally its S3 bucket). Heavy prompts.

Create options:
  --new-project NAME     Logical Terraform project_name (default: bump _001→_002)
  --new-bucket NAME      New private origin bucket (must match app podcast.s3_bucket)
  --new-show-title TEXT  CloudFront comment / show title (default: keep current)

Delete options (require --delete):
  --distribution-id ID   CloudFront distribution ID (e.g. E2ABCDEFGHIJKL)
                         Prefer this — copy from --list or AWS Console.
  --feed-url URL         Alternative: https://dxxxx.cloudfront.net/feed.xml
                         (resolved via the local origins registry)
  --also-delete-bucket   Also empty + delete the paired S3 bucket from the
                         registry / prompts (default: keep bucket objects)
  --allow-active         Dangerous: allow deleting the currently Terraform-
                         managed / secrets-targeted distribution

Shared:
  -y, --yes              Skip the first yes/no prompt (delete still requires
                         typing the distribution ID)
  -h, --help             Show this help

Local binding (created on --create):
  ASSETS/podcast_origins/<project_name>/origin.json
    Maps this show → s3_bucket + CloudFront feed so each Apple podcast has its
    own origin, distinct from other shows on disk.

Registry (updated on create/delete):
  terraform/archives/podcast-origins.json
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    --create)
      MODE="create"
      shift
      ;;
    --list)
      MODE="list"
      shift
      ;;
    --delete)
      MODE="delete"
      shift
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
    --distribution-id)
      DELETE_DIST_ID="${2:?--distribution-id requires a value}"
      shift 2
      ;;
    --feed-url)
      DELETE_FEED_URL="${2:?--feed-url requires a value}"
      shift 2
      ;;
    --also-delete-bucket)
      DELETE_ALSO_BUCKET=true
      shift
      ;;
    --allow-active)
      DELETE_ALLOW_ACTIVE=true
      shift
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

_bump_project() {
  local cur=$1
  if [[ "$cur" =~ ^(.*_)([0-9]+)$ ]]; then
    local prefix="${BASH_REMATCH[1]}"
    local n="${BASH_REMATCH[2]}"
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

_confirm_yn() {
  local prompt=$1
  if [[ "$AUTO_CONFIRM" == true ]]; then
    return 0
  fi
  echo >&2
  read -r -p "[$TF_SCRIPT_NAME] ${prompt} [y/N] " reply
  case "${reply}" in
    y | Y | yes | YES) return 0 ;;
    *) return 1 ;;
  esac
}

# --- mode: list ------------------------------------------------------------

if [[ "$MODE" == "list" ]]; then
  mkdir -p "$ARCHIVE_DIR"
  if [[ ! -f "$ORIGINS_REGISTRY" ]]; then
    tf_log "No registry yet at ${ORIGINS_REGISTRY}"
    tf_log "Run --create once (or seed from current terraform outputs) to populate it."
    # Best-effort live tip from terraform if present
    if [[ -f "$TF_STATE_LIVE" ]]; then
      terraform_common_source_aws_env
      echo
      echo "Current Terraform-managed stack (not yet in registry):"
      echo "  project_name:  $(_tf_raw project_name)"
      echo "  s3_bucket:     $(_tf_raw s3_bucket_id)"
      echo "  cloudfront_id: $(_tf_raw cloudfront_distribution_id)"
      echo "  feed_url:      $(_tf_raw feed_url)"
      print_apple_passthrough_notice "$(_tf_raw feed_url)"
    fi
    exit 0
  fi
  "$(_python)" - <<PY
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path("${REPO_ROOT}") / "src"))
from interview_mux.podcast_rss.settings import (
    apple_podcasts_passthrough_url,
    format_apple_passthrough_notice,
)
doc = json.loads(Path("${ORIGINS_REGISTRY}").read_text(encoding="utf-8"))
origins = doc.get("origins") or []
print(f"podcast-origins registry ({len(origins)} entries)")
print(f"  file: ${ORIGINS_REGISTRY}")
print()
last_feed = ""
for o in origins:
    status = o.get("status") or "?"
    feed = o.get("feed_url") or ""
    if feed:
        last_feed = feed
    print(f"[{status}] {o.get('project_name') or '?'}")
    print(f"  distribution_id: {o.get('cloudfront_distribution_id') or '—'}")
    print(f"  feed_url:        {feed or '—'}")
    print(f"  apple_passthrough: {apple_podcasts_passthrough_url(feed) or '—'}")
    print(f"  s3_bucket:       {o.get('s3_bucket') or '—'}")
    print(f"  podcast_guid:    {o.get('podcast_guid') or '—'}")
    print(f"  local_binding:   {o.get('local_binding') or '—'}")
    print()
print("Delete example (copy a distribution_id):")
print("  ./scripts/tf-podcast-rss-origin.sh --delete --distribution-id <ID>")
if last_feed:
    print()
    print(format_apple_passthrough_notice(last_feed, include_feed=False))
PY
  exit 0
fi

# --- mode: delete ----------------------------------------------------------

if [[ "$MODE" == "delete" ]]; then
  terraform_common_source_aws_env
  PYTHON="$(_python)"

  # Interactive primer when IDs were not passed on the CLI
  if [[ -z "$DELETE_DIST_ID" && -z "$DELETE_FEED_URL" ]]; then
    cat <<EOF >&2

[$TF_SCRIPT_NAME] DELETE MODE — retire one archived CloudFront RSS URL

  This permanently disables + deletes ONE CloudFront distribution in AWS.
  Apple / listeners still using that feed URL will break.

  Prefer copy-paste of the distribution ID from:
    ./scripts/tf-podcast-rss-origin.sh --list

  Example ID shape:  E2ABCDEFGHIJKL
  Example feed URL:  https://d111111abcdef8.cloudfront.net/feed.xml

EOF
    if [[ -f "$ORIGINS_REGISTRY" ]]; then
      tf_log "Known origins:"
      "$PYTHON" - <<PY
import json
from pathlib import Path
doc = json.loads(Path("${ORIGINS_REGISTRY}").read_text(encoding="utf-8"))
for o in doc.get("origins") or []:
    print(
        f"  [{o.get('status')}] "
        f"id={o.get('cloudfront_distribution_id') or '—'}  "
        f"feed={o.get('feed_url') or '—'}  "
        f"bucket={o.get('s3_bucket') or '—'}  "
        f"project={o.get('project_name') or '—'}"
    )
PY
      echo >&2
    fi
    read -r -p "[$TF_SCRIPT_NAME] CloudFront distribution ID (or leave blank to use feed URL): " DELETE_DIST_ID
    if [[ -z "$DELETE_DIST_ID" ]]; then
      read -r -p "[$TF_SCRIPT_NAME] Feed URL (https://d….cloudfront.net/feed.xml): " DELETE_FEED_URL
    fi
    if [[ "$DELETE_ALSO_BUCKET" != true ]]; then
      read -r -p "[$TF_SCRIPT_NAME] Also empty + delete the paired S3 bucket? [y/N] " bucket_reply
      case "${bucket_reply}" in
        y | Y | yes | YES) DELETE_ALSO_BUCKET=true ;;
      esac
    fi
  fi

  if [[ -z "$DELETE_DIST_ID" && -z "$DELETE_FEED_URL" ]]; then
    tf_warn "Need --distribution-id ID or --feed-url URL (or enter one when prompted)."
    exit 1
  fi

  ACTIVE_CF_ID="$(_tf_raw cloudfront_distribution_id)"
  ACTIVE_BUCKET="$(_tf_raw s3_bucket_id)"
  SECRETS_CF_ID=""
  if [[ -f "${REPO_ROOT}/config/secrets/secrets.env" ]]; then
    SECRETS_CF_ID="$(
      grep -E '^[[:space:]]*PODCAST_CLOUDFRONT_DISTRIBUTION_ID=' \
        "${REPO_ROOT}/config/secrets/secrets.env" \
        | head -1 \
        | sed -E 's/^[^=]*=[[:space:]]*//' \
        | tr -d '"' \
        | tr -d "'" \
        || true
    )"
  fi

  # Resolve registry entry + normalize ID
  RESOLVED="$(
    ORIGINS_REGISTRY="$ORIGINS_REGISTRY" \
    DELETE_DIST_ID="$DELETE_DIST_ID" \
    DELETE_FEED_URL="$DELETE_FEED_URL" \
    "$PYTHON" - <<'PY'
import json
import os
import re
import sys
from pathlib import Path

dist = (os.environ.get("DELETE_DIST_ID") or "").strip()
feed = (os.environ.get("DELETE_FEED_URL") or "").strip()
reg_path = Path(os.environ["ORIGINS_REGISTRY"])
origins = []
if reg_path.is_file():
    origins = (json.loads(reg_path.read_text(encoding="utf-8")).get("origins") or [])

match = None
if dist:
    for o in origins:
        if (o.get("cloudfront_distribution_id") or "") == dist:
            match = o
            break
elif feed:
    feed_n = feed.rstrip("/")
    for o in origins:
        fu = (o.get("feed_url") or "").rstrip("/")
        base = (o.get("feed_base_url") or "").rstrip("/")
        domain = (o.get("cloudfront_domain_name") or "").strip()
        if fu == feed_n or base == feed_n or (domain and domain in feed_n):
            match = o
            dist = o.get("cloudfront_distribution_id") or ""
            break
    if not dist:
        # dxxxx.cloudfront.net from URL — still need ID from registry
        print("ERROR: feed URL not found in podcast-origins.json; pass --distribution-id", file=sys.stderr)
        sys.exit(2)

if not dist:
    print("ERROR: empty distribution id", file=sys.stderr)
    sys.exit(2)
if not re.fullmatch(r"E[A-Z0-9]{10,}", dist):
    print(
        f"ERROR: distribution id {dist!r} does not look like a CloudFront ID (E…)",
        file=sys.stderr,
    )
    sys.exit(2)

out = {
    "distribution_id": dist,
    "s3_bucket": (match or {}).get("s3_bucket"),
    "feed_url": (match or {}).get("feed_url"),
    "project_name": (match or {}).get("project_name"),
    "status": (match or {}).get("status"),
    "oac_id": (match or {}).get("origin_access_control_id"),
    "matched_registry": bool(match),
}
print(json.dumps(out))
PY
  )" || {
    tf_warn "Could not resolve distribution to delete."
    exit 1
  }

  DELETE_DIST_ID="$(
    DELETE_JSON="$RESOLVED" "$PYTHON" -c 'import json,os; print(json.loads(os.environ["DELETE_JSON"])["distribution_id"])'
  )"
  REG_BUCKET="$(
    DELETE_JSON="$RESOLVED" "$PYTHON" -c 'import json,os; print(json.loads(os.environ["DELETE_JSON"]).get("s3_bucket") or "")'
  )"
  REG_FEED="$(
    DELETE_JSON="$RESOLVED" "$PYTHON" -c 'import json,os; print(json.loads(os.environ["DELETE_JSON"]).get("feed_url") or "")'
  )"
  REG_PROJECT="$(
    DELETE_JSON="$RESOLVED" "$PYTHON" -c 'import json,os; print(json.loads(os.environ["DELETE_JSON"]).get("project_name") or "")'
  )"
  REG_STATUS="$(
    DELETE_JSON="$RESOLVED" "$PYTHON" -c 'import json,os; print(json.loads(os.environ["DELETE_JSON"]).get("status") or "")'
  )"
  MATCHED_REGISTRY="$(
    DELETE_JSON="$RESOLVED" "$PYTHON" -c 'import json,os; print(json.loads(os.environ["DELETE_JSON"]).get("matched_registry"))'
  )"

  if [[ "$DELETE_DIST_ID" == "$ACTIVE_CF_ID" || "$DELETE_DIST_ID" == "$SECRETS_CF_ID" ]]; then
    if [[ "$DELETE_ALLOW_ACTIVE" != true ]]; then
      cat <<EOF >&2
[$TF_SCRIPT_NAME] REFUSING to delete the active / app-targeted distribution.

  distribution_id:     ${DELETE_DIST_ID}
  terraform active CF: ${ACTIVE_CF_ID:-—}
  secrets.env CF:      ${SECRETS_CF_ID:-—}

  --delete is for *archived* origins you no longer need.
  To stand up a replacement first, run without --delete (default --create).
  Only if you truly intend to destroy the live show URL, re-run with:
    --delete --distribution-id ${DELETE_DIST_ID} --allow-active
EOF
      exit 1
    fi
    tf_warn " --allow-active set: proceeding against the live/app-targeted distribution."
  fi

  cat <<EOF

[$TF_SCRIPT_NAME] DELETE PLAN (destructive)

  CloudFront distribution ID:  ${DELETE_DIST_ID}
  Feed URL (registry):         ${REG_FEED:-unknown — not in registry}
  Project (registry):          ${REG_PROJECT:-unknown}
  Status (registry):           ${REG_STATUS:-unknown}
  Registry match:              ${MATCHED_REGISTRY}
  Also delete S3 bucket:       ${DELETE_ALSO_BUCKET}  (${REG_BUCKET:-bucket unknown})

  Steps that will run via boto3 (no AWS CLI):
    1) Disable the CloudFront distribution
    2) Wait until it is deployed (disabled)
    3) Delete the CloudFront distribution
    4) Optionally empty + delete the S3 bucket (--also-delete-bucket)
    5) Mark the origin as deleted in ${ORIGINS_REGISTRY}

  This cannot be undone. Apple Podcasts / subscribers on this URL will fail.

EOF

  if ! _confirm_yn "Continue to the typed-ID confirmation for ${DELETE_DIST_ID}?"; then
    tf_log "Cancelled; nothing changed."
    exit 0
  fi

  echo >&2
  read -r -p "[$TF_SCRIPT_NAME] Type the distribution ID exactly to destroy it: " typed_id
  if [[ "$typed_id" != "$DELETE_DIST_ID" ]]; then
    tf_log "Typed ID did not match; nothing deleted."
    exit 1
  fi

  if [[ "$DELETE_ALSO_BUCKET" == true ]]; then
    if [[ -z "$REG_BUCKET" ]]; then
      read -r -p "[$TF_SCRIPT_NAME] S3 bucket name to empty+delete (required): " REG_BUCKET
    fi
    if [[ -z "$REG_BUCKET" ]]; then
      tf_warn "No bucket name; refusing --also-delete-bucket without a bucket."
      exit 1
    fi
    if [[ "$REG_BUCKET" == "$ACTIVE_BUCKET" && "$DELETE_ALLOW_ACTIVE" != true ]]; then
      tf_warn "Bucket ${REG_BUCKET} is the active Terraform origin; refusing without --allow-active."
      exit 1
    fi
    echo >&2
    read -r -p "[$TF_SCRIPT_NAME] Type the S3 bucket name to empty+delete: " typed_bucket
    if [[ "$typed_bucket" != "$REG_BUCKET" ]]; then
      tf_log "Typed bucket did not match; nothing deleted."
      exit 1
    fi
  fi

  tf_log "Deleting CloudFront distribution ${DELETE_DIST_ID}…"
  (
    cd "$REPO_ROOT"
    DELETE_DIST_ID="$DELETE_DIST_ID" \
    DELETE_BUCKET="${REG_BUCKET}" \
    DELETE_ALSO_BUCKET="$DELETE_ALSO_BUCKET" \
    ORIGINS_REGISTRY="$ORIGINS_REGISTRY" \
    "$PYTHON" - <<'PY'
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))

from interview_mux.podcast_rss.s3_publish import empty_bucket  # noqa: E402
from interview_mux.podcast_rss.settings import resolve_publish_targets  # noqa: E402
import interview_mux.podcast_rss.s3_publish as sp  # noqa: E402

region = resolve_publish_targets().get("region") or "us-east-1"
cf = sp._client("cloudfront", region=region)
s3 = sp._client("s3", region=region)

dist_id = os.environ["DELETE_DIST_ID"]
also_bucket = os.environ.get("DELETE_ALSO_BUCKET") == "true"
bucket = (os.environ.get("DELETE_BUCKET") or "").strip()

# 1–3: disable, wait, delete distribution
cfg_resp = cf.get_distribution_config(Id=dist_id)
etag = cfg_resp["ETag"]
config = cfg_resp["DistributionConfig"]
oac_id = None
origins = (config.get("Origins") or {}).get("Items") or []
for origin in origins:
    oac = origin.get("OriginAccessControlId") or ""
    if oac:
        oac_id = oac
        break

if config.get("Enabled"):
    print(f"Disabling distribution {dist_id}…", flush=True)
    config["Enabled"] = False
    cf.update_distribution(Id=dist_id, IfMatch=etag, DistributionConfig=config)
else:
    print(f"Distribution {dist_id} already disabled.", flush=True)

print("Waiting for CloudFront deploy (disabled) — can take several minutes…", flush=True)
waiter = cf.get_waiter("distribution_deployed")
waiter.wait(Id=dist_id, WaiterConfig={"Delay": 30, "MaxAttempts": 60})

cfg_resp = cf.get_distribution_config(Id=dist_id)
print(f"Deleting distribution {dist_id}…", flush=True)
cf.delete_distribution(Id=dist_id, IfMatch=cfg_resp["ETag"])
print(f"Deleted CloudFront distribution {dist_id}", flush=True)

if oac_id:
    try:
        oac = cf.get_origin_access_control(Id=oac_id)
        cf.delete_origin_access_control(Id=oac_id, IfMatch=oac["ETag"])
        print(f"Deleted Origin Access Control {oac_id}", flush=True)
    except Exception as exc:  # noqa: BLE001 — best-effort cleanup
        print(f"WARNING: could not delete OAC {oac_id}: {exc}", flush=True)

if also_bucket and bucket:
    print(f"Emptying s3://{bucket}…", flush=True)
    deleted = empty_bucket(bucket, region=region)
    print(f"Removed {deleted} object version(s)/marker(s)", flush=True)
    print(f"Deleting bucket s3://{bucket}…", flush=True)
    # Brief settle for eventual consistency after mass deletes
    time.sleep(2)
    s3.delete_bucket(Bucket=bucket)
    print(f"Deleted bucket s3://{bucket}", flush=True)

# Update registry
reg_path = Path(os.environ["ORIGINS_REGISTRY"])
if reg_path.is_file():
    doc = json.loads(reg_path.read_text(encoding="utf-8"))
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    for o in doc.get("origins") or []:
        if o.get("cloudfront_distribution_id") == dist_id:
            o["status"] = "deleted"
            o["deleted_at"] = stamp
            if also_bucket and bucket:
                o["bucket_deleted"] = True
    reg_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"Updated registry: {reg_path}", flush=True)
PY
  )

  cat <<EOF
[$TF_SCRIPT_NAME] Delete complete for CloudFront ${DELETE_DIST_ID}.

  Registry: ${ORIGINS_REGISTRY}
  Tip: ./scripts/tf-podcast-rss-origin.sh --list
EOF
  exit 0
fi

# --- mode: create (default) ------------------------------------------------

terraform_common_source_aws_env
_require_file "$TF_STATE_LIVE"
_require_file "$APP_DEFAULTS"
PYTHON="$(_python)"

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
ARCHIVE_JSON="${ARCHIVE_DIR}/rss-origin-${STAMP}.json"
LOCAL_BINDING_REL="ASSETS/podcast_origins/${NEW_PROJECT}"
LOCAL_BINDING_DIR="${REPO_ROOT}/${LOCAL_BINDING_REL}"
NEW_GUID="$(
  "$PYTHON" - <<'PY'
import uuid
print(uuid.uuid4())
PY
)"

# Current app podcast_guid (for archive record)
CUR_GUID="$(
  APP_DEFAULTS="$APP_DEFAULTS" "$PYTHON" - <<'PY'
import json, os
from pathlib import Path
doc = json.loads(Path(os.environ["APP_DEFAULTS"]).read_text(encoding="utf-8"))
print((doc.get("podcast") or {}).get("podcast_guid") or "")
PY
)"

cat <<EOF
[$TF_SCRIPT_NAME] CREATE new podcast RSS origin (preview)

  This does NOT destroy the previous CloudFront / S3.
  Previous stack is orphaned from Terraform state and left live (archived).

  ARCHIVE (left live in AWS, removed from Terraform state):
    project_name:    ${CUR_PROJECT}
    s3_bucket:       ${CUR_BUCKET}
    cloudfront_id:   ${CUR_CF_ID}
    feed_base_url:   ${CUR_FEED_BASE}
    feed_url:        ${CUR_FEED_URL}
    podcast_guid:    ${CUR_GUID:-—}
    event_record:    ${ARCHIVE_JSON}

  NEW ORIGIN (created by terraform apply — new Apple / directory feed):
    project_name:    ${NEW_PROJECT}
    s3_bucket:       ${NEW_BUCKET}
    show_title:      ${NEW_SHOW_TITLE}
    podcast_guid:    ${NEW_GUID}
    local_binding:   ${LOCAL_BINDING_REL}/origin.json

  After success:
    - Old Apple/subscribers keep ${CUR_FEED_URL} (archive) until you --delete it.
    - App publish targets the NEW bucket / CF via app.defaults + secrets.env.
    - Submit the NEW feed URL from ./scripts/tf-output.sh feed_url to Apple
      (the script prints the Podcasts Connect pass-through after apply).
    - Each show is distinguished by project_name + local_binding + registry.
EOF

if ! _confirm_yn "Proceed with creating the new RSS origin?"; then
  tf_log "Cancelled; nothing changed."
  exit 0
fi

mkdir -p "$ARCHIVE_DIR" "$LOCAL_BINDING_DIR"

# --- 1) write event record + upsert registry / local binding (pre-apply) ---

ARCHIVE_JSON="$ARCHIVE_JSON" \
ORIGINS_REGISTRY="$ORIGINS_REGISTRY" \
LOCAL_BINDING_DIR="$LOCAL_BINDING_DIR" \
LOCAL_BINDING_REL="$LOCAL_BINDING_REL" \
CUR_PROJECT="$CUR_PROJECT" \
CUR_BUCKET="$CUR_BUCKET" \
CUR_CF_ID="$CUR_CF_ID" \
CUR_CF_DOMAIN="$CUR_CF_DOMAIN" \
CUR_FEED_BASE="$CUR_FEED_BASE" \
CUR_FEED_URL="$CUR_FEED_URL" \
CUR_SHOW_TITLE="$CUR_SHOW_TITLE" \
CUR_GUID="$CUR_GUID" \
NEW_PROJECT="$NEW_PROJECT" \
NEW_BUCKET="$NEW_BUCKET" \
NEW_SHOW_TITLE="$NEW_SHOW_TITLE" \
NEW_GUID="$NEW_GUID" \
STAMP="$STAMP" \
"$PYTHON" - <<'PY'
import json
import os
from pathlib import Path

stamp = os.environ["STAMP"]
archived = {
    "project_name": os.environ["CUR_PROJECT"],
    "s3_bucket": os.environ["CUR_BUCKET"],
    "cloudfront_distribution_id": os.environ["CUR_CF_ID"],
    "cloudfront_domain_name": os.environ["CUR_CF_DOMAIN"],
    "feed_base_url": os.environ["CUR_FEED_BASE"],
    "feed_url": os.environ["CUR_FEED_URL"],
    "show_title": os.environ["CUR_SHOW_TITLE"],
    "podcast_guid": os.environ.get("CUR_GUID") or None,
    "status": "archived",
    "local_binding": f"ASSETS/podcast_origins/{os.environ['CUR_PROJECT']}",
    "note": "Resources remain in AWS; removed from Terraform state so the old URL stays reachable.",
}
replacement = {
    "project_name": os.environ["NEW_PROJECT"],
    "s3_bucket": os.environ["NEW_BUCKET"],
    "show_title": os.environ["NEW_SHOW_TITLE"],
    "podcast_guid": os.environ["NEW_GUID"],
    "status": "active",
    "local_binding": os.environ["LOCAL_BINDING_REL"],
}

event = {
    "version": 2,
    "action": "create_origin",
    "created_at": stamp,
    "purpose": "Create a new S3+CloudFront RSS origin for a fresh Apple/podcast feed; archive prior URL",
    "archived": archived,
    "replacement": replacement,
}
Path(os.environ["ARCHIVE_JSON"]).write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")

# Registry: mark prior active → archived; upsert both entries by project_name
reg_path = Path(os.environ["ORIGINS_REGISTRY"])
if reg_path.is_file():
    doc = json.loads(reg_path.read_text(encoding="utf-8"))
else:
    doc = {"version": 1, "origins": []}
origins = doc.setdefault("origins", [])

def upsert(entry: dict) -> None:
    key = entry.get("project_name")
    for i, o in enumerate(origins):
        if o.get("project_name") == key:
            origins[i] = {**o, **entry}
            return
    # Also match by cloudfront id when project missing historically
    cf = entry.get("cloudfront_distribution_id")
    if cf:
        for i, o in enumerate(origins):
            if o.get("cloudfront_distribution_id") == cf:
                origins[i] = {**o, **entry}
                return
    origins.append(entry)

for o in origins:
    if o.get("status") == "active":
        o["status"] = "archived"
        o.setdefault("archived_at", stamp)

archived_entry = {
    **archived,
    "archived_at": stamp,
}
upsert(archived_entry)
upsert({**replacement, "created_at": stamp})
doc["updated_at"] = stamp
reg_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

# Local binding for the NEW origin (and ensure archived binding dir exists)
bind_dir = Path(os.environ["LOCAL_BINDING_DIR"])
bind_dir.mkdir(parents=True, exist_ok=True)
(bind_dir / "publish").mkdir(exist_ok=True)
binding = {
    "version": 1,
    "project_name": os.environ["NEW_PROJECT"],
    "s3_bucket": os.environ["NEW_BUCKET"],
    "podcast_guid": os.environ["NEW_GUID"],
    "show_title": os.environ["NEW_SHOW_TITLE"],
    "status": "pending_apply",
    "created_at": stamp,
    "purpose": (
        "Identifies which local show origin the app should treat as the "
        "active S3/CloudFront publish target. Episode packages still live "
        "under ASSETS/executions/<exec_id>/publish/; this folder tags the "
        "podcast *show* (Apple feed) those uploads belong to."
    ),
    "app_config": {
        "podcast.project_name": os.environ["NEW_PROJECT"],
        "podcast.s3_bucket": os.environ["NEW_BUCKET"],
        "podcast.podcast_guid": os.environ["NEW_GUID"],
        "secrets.PODCAST_FEED_BASE_URL": "(set after terraform apply)",
        "secrets.PODCAST_CLOUDFRONT_DISTRIBUTION_ID": "(set after terraform apply)",
    },
}
(bind_dir / "origin.json").write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")

# Archived local binding (metadata only — does not move old publish files)
arch_dir = Path("ASSETS/podcast_origins") / os.environ["CUR_PROJECT"]
# Use absolute under repo via local binding parent
arch_dir = bind_dir.parent / os.environ["CUR_PROJECT"]
arch_dir.mkdir(parents=True, exist_ok=True)
(arch_dir / "publish").mkdir(exist_ok=True)
arch_binding = {
    "version": 1,
    "project_name": os.environ["CUR_PROJECT"],
    "s3_bucket": os.environ["CUR_BUCKET"],
    "cloudfront_distribution_id": os.environ["CUR_CF_ID"],
    "cloudfront_domain_name": os.environ["CUR_CF_DOMAIN"],
    "feed_base_url": os.environ["CUR_FEED_BASE"],
    "feed_url": os.environ["CUR_FEED_URL"],
    "podcast_guid": os.environ.get("CUR_GUID") or None,
    "show_title": os.environ["CUR_SHOW_TITLE"],
    "status": "archived",
    "archived_at": stamp,
    "purpose": "Archived Apple/podcast feed origin; uploads should not target this bucket unless intentionally republishing the old show.",
}
(arch_dir / "origin.json").write_text(json.dumps(arch_binding, indent=2) + "\n", encoding="utf-8")
print(os.environ["ARCHIVE_JSON"])
PY

tf_log "Wrote event record: $ARCHIVE_JSON"
tf_log "Updated registry: $ORIGINS_REGISTRY"
tf_log "Local bindings under: $LOCAL_ORIGINS_ROOT"

# --- 2) orphan managed origin stack from state (do not destroy in AWS) ----

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

tf_log "Updating config/app.defaults.json podcast.s3_bucket + podcast.podcast_guid (+ project_name)"
APP_DEFAULTS="$APP_DEFAULTS" NEW_BUCKET="$NEW_BUCKET" NEW_GUID="$NEW_GUID" \
NEW_PROJECT="$NEW_PROJECT" \
"$PYTHON" - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["APP_DEFAULTS"])
doc = json.loads(path.read_text(encoding="utf-8"))
podcast = doc.setdefault("podcast", {})
podcast["s3_bucket"] = os.environ["NEW_BUCKET"]
podcast["podcast_guid"] = os.environ["NEW_GUID"]
podcast["project_name"] = os.environ["NEW_PROJECT"]
path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
PY

# --- 4) create new stack + seed -------------------------------------------

tf_log "Applying new S3 + CloudFront stack…"
"$SCRIPT_DIR/tf-apply.sh" -auto-approve

NEW_FEED_URL="$(_tf_raw feed_url)"
NEW_FEED_BASE="$(_tf_raw feed_base_url)"
NEW_CF_ID="$(_tf_raw cloudfront_distribution_id)"
NEW_CF_DOMAIN="$(_tf_raw cloudfront_domain_name)"

tf_log "Seeding empty feed on new origin…"
(
  cd "$REPO_ROOT"
  "$PYTHON" scripts/seed_podcast_origin.py
)

# Enrich event + registry + local binding with post-apply outputs.
ARCHIVE_JSON="$ARCHIVE_JSON" \
ORIGINS_REGISTRY="$ORIGINS_REGISTRY" \
LOCAL_BINDING_DIR="$LOCAL_BINDING_DIR" \
NEW_FEED_URL="$NEW_FEED_URL" \
NEW_FEED_BASE="$NEW_FEED_BASE" \
NEW_CF_ID="$NEW_CF_ID" \
NEW_CF_DOMAIN="$NEW_CF_DOMAIN" \
NEW_BUCKET="$NEW_BUCKET" \
NEW_PROJECT="$NEW_PROJECT" \
NEW_GUID="$NEW_GUID" \
"$PYTHON" - <<'PY'
import json
import os
from pathlib import Path

stamp_fields = {
    "cloudfront_distribution_id": os.environ.get("NEW_CF_ID") or None,
    "cloudfront_domain_name": os.environ.get("NEW_CF_DOMAIN") or None,
    "feed_base_url": os.environ.get("NEW_FEED_BASE") or None,
    "feed_url": os.environ.get("NEW_FEED_URL") or None,
    "s3_bucket": os.environ.get("NEW_BUCKET"),
    "status": "active",
}

path = Path(os.environ["ARCHIVE_JSON"])
doc = json.loads(path.read_text(encoding="utf-8"))
doc["replacement"].update(stamp_fields)
path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

reg_path = Path(os.environ["ORIGINS_REGISTRY"])
reg = json.loads(reg_path.read_text(encoding="utf-8"))
for o in reg.get("origins") or []:
    if o.get("project_name") == os.environ["NEW_PROJECT"]:
        o.update(stamp_fields)
        o["podcast_guid"] = os.environ.get("NEW_GUID")
reg_path.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")

bind_path = Path(os.environ["LOCAL_BINDING_DIR"]) / "origin.json"
binding = json.loads(bind_path.read_text(encoding="utf-8"))
binding.update(stamp_fields)
binding["status"] = "active"
app = binding.setdefault("app_config", {})
app["secrets.PODCAST_FEED_BASE_URL"] = os.environ.get("NEW_FEED_BASE")
app["secrets.PODCAST_CLOUDFRONT_DISTRIBUTION_ID"] = os.environ.get("NEW_CF_ID")
bind_path.write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")
PY

cat <<EOF
[$TF_SCRIPT_NAME] New RSS origin ready.

  Archived feed (still live):  ${CUR_FEED_URL}
  New feed (Apple submit):     ${NEW_FEED_URL}
  New CloudFront ID:           ${NEW_CF_ID}
  New S3 bucket:               ${NEW_BUCKET}
  New podcast GUID:            ${NEW_GUID}
  Local binding:               ${LOCAL_BINDING_REL}/origin.json
  Registry:                    ${ORIGINS_REGISTRY}
  Event record:                ${ARCHIVE_JSON}

Next:
  1) Commit terraform/state/terraform.tfstate, ${ORIGINS_REGISTRY}, ${ARCHIVE_JSON}, config/app.defaults.json
  2) Keep config/terraform.tfvars gitignored but backed up locally
  3) Submit ${NEW_FEED_URL} as a new show in Apple Podcasts Connect
     (use the pass-through URL printed below; Apple needs ≥1 episode)
  4) Later, retire an old URL only:
       ./scripts/tf-podcast-rss-origin.sh --list
       ./scripts/tf-podcast-rss-origin.sh --delete --distribution-id <ID>
EOF
print_apple_passthrough_notice "${NEW_FEED_URL}" 0
