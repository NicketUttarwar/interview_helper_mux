#!/usr/bin/env bash
# Upsert AWS-derived podcast destinations into config/podcast/catalog.json.
# For the default Zero Shot show, also upsert PODCAST_* into secrets.env
# (one-release fallback). Bucket + CF id belong in the committed catalog.
#
# After writing a public feed URL, always print the Apple Podcasts Connect
# pass-through (print_apple_passthrough_notice).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

SECRETS="${REPO_ROOT}/config/secrets/secrets.env"
EXAMPLE="${REPO_ROOT}/config/templates/secrets.env.example"
CATALOG="${REPO_ROOT}/config/podcast/catalog.json"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--podcast-id ID]

Read terraform outputs and write destinations into config/podcast/catalog.json
for the selected show (TF_PODCAST_ID / --podcast-id, else catalog default).

Also upserts AWS_DEFAULT_REGION into secrets.env. Singular PODCAST_CLOUDFRONT_*
/ PODCAST_FEED_BASE_URL are written only for the default Zero Shot show
(legacy fallback). The GUI never creates AWS resources.

Loads AWS credentials from secrets.env when present (same as other tf wrappers).
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

upsert_secret() {
  local key="$1" val="$2" file="$3"
  mkdir -p "$(dirname "$file")"
  touch "$file"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    KEY="$key" VAL="$val" FILE="$file" python3 - <<'PY'
from pathlib import Path
import os
key = os.environ["KEY"]
val = os.environ["VAL"]
p = Path(os.environ["FILE"])
lines = p.read_text().splitlines()
out = []
for line in lines:
    if line.startswith(f"{key}="):
        out.append(f"{key}={val}")
    else:
        out.append(line)
p.write_text("\n".join(out) + "\n")
PY
  else
    printf '\n%s=%s\n' "$key" "$val" >> "$file"
  fi
}

tf_log "Reading terraform outputs…"
OUT_JSON="$(terraform_common_exec output -json "$@")"

read -r AWS_DEFAULT_REGION TF_BUCKET PODCAST_CLOUDFRONT_DISTRIBUTION_ID PODCAST_FEED_BASE_URL < <(
  printf '%s' "$OUT_JSON" | python3 -c '
import json, sys
data = json.load(sys.stdin)

def val(key):
    item = data.get(key) or {}
    v = item.get("value")
    if v is None:
        raise SystemExit(f"missing terraform output: {key}")
    return str(v).replace("\n", "").replace(" ", "")

print(
    val("aws_region"),
    val("s3_bucket_id"),
    val("cloudfront_distribution_id"),
    val("feed_base_url"),
)
'
)

if [[ ! -f "$SECRETS" ]]; then
  mkdir -p "$(dirname "$SECRETS")"
  if [[ -f "$EXAMPLE" ]]; then
    cp "$EXAMPLE" "$SECRETS"
    tf_log "Created $SECRETS from template"
  else
    touch "$SECRETS"
  fi
fi

upsert_secret "AWS_DEFAULT_REGION" "$AWS_DEFAULT_REGION" "$SECRETS"

PODCAST_ID="${TF_PODCAST_ID:-zero_shot_podcast_demo}"
DEFAULT_ID="zero_shot_podcast_demo"
if [[ "$PODCAST_ID" == "$DEFAULT_ID" ]]; then
  upsert_secret "PODCAST_CLOUDFRONT_DISTRIBUTION_ID" "$PODCAST_CLOUDFRONT_DISTRIBUTION_ID" "$SECRETS"
  upsert_secret "PODCAST_FEED_BASE_URL" "$PODCAST_FEED_BASE_URL" "$SECRETS"
  tf_log "Updated $SECRETS (default show CF/feed fallback; bucket stays in catalog)"
else
  tf_log "Skipping singular PODCAST_* secrets (non-default podcast-id=$PODCAST_ID)"
fi

CATALOG="$CATALOG" PODCAST_ID="$PODCAST_ID" TF_BUCKET="$TF_BUCKET" \
  DIST_ID="$PODCAST_CLOUDFRONT_DISTRIBUTION_ID" FEED_BASE="$PODCAST_FEED_BASE_URL" \
  REGION="$AWS_DEFAULT_REGION" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["CATALOG"])
pid = os.environ["PODCAST_ID"]
bucket = os.environ["TF_BUCKET"]
dist = os.environ["DIST_ID"]
feed = os.environ["FEED_BASE"].rstrip("/")
region = os.environ["REGION"]
if not path.is_file():
    raise SystemExit(f"catalog missing: {path}")
data = json.loads(path.read_text(encoding="utf-8"))
shows = data.get("shows")
if not isinstance(shows, list):
    raise SystemExit("catalog.json has no shows[]")
found = False
for row in shows:
    if not isinstance(row, dict):
        continue
    if str(row.get("id") or "").strip() != pid:
        continue
    row["s3_bucket"] = bucket
    row["cloudfront_distribution_id"] = dist
    row["feed_base_url"] = feed
    if region:
        row["aws_region"] = region
    found = True
    break
if not found:
    raise SystemExit(f"podcast_id {pid!r} not in {path} — add the show row, then re-run")
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(f"Updated {path} for podcast_id={pid}")
PY

tf_log "  catalog podcast_id=$PODCAST_ID bucket=$TF_BUCKET"
tf_log "  PODCAST_CLOUDFRONT_DISTRIBUTION_ID=$PODCAST_CLOUDFRONT_DISTRIBUTION_ID"
tf_log "  PODCAST_FEED_BASE_URL=$PODCAST_FEED_BASE_URL"
echo "Feed URL: ${PODCAST_FEED_BASE_URL}/feed.xml"
echo "Commit config/podcast/catalog.json (and terraform/state/shows/${PODCAST_ID}/ if this is a new origin)."
# Always print Apple's pass-through next to a new/synced public RSS URL.
print_apple_passthrough_notice "${PODCAST_FEED_BASE_URL}/feed.xml" 0
