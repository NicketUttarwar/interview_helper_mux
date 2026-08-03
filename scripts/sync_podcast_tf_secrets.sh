#!/usr/bin/env bash
# Upsert AWS-derived podcast IDs into secrets.env (CloudFront + feed base).
# Bucket name lives in config/app.defaults.json podcast.s3_bucket (committed).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/terraform-common.sh"

SECRETS="${REPO_ROOT}/config/secrets/secrets.env"
EXAMPLE="${REPO_ROOT}/config/templates/secrets.env.example"
APP_DEFAULTS="${REPO_ROOT}/config/app.defaults.json"

usage() {
  cat <<EOF
Usage: $(basename "$0")

Read terraform outputs and upsert into config/secrets/secrets.env:
  AWS_DEFAULT_REGION
  PODCAST_CLOUDFRONT_DISTRIBUTION_ID
  PODCAST_FEED_BASE_URL

Does NOT write the S3 bucket name — that belongs in
  config/app.defaults.json → podcast.s3_bucket
(optional legacy PODCAST_S3_BUCKET in secrets remains an override).

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
OUT_JSON="$(terraform_common_exec output -json)"

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
upsert_secret "PODCAST_CLOUDFRONT_DISTRIBUTION_ID" "$PODCAST_CLOUDFRONT_DISTRIBUTION_ID" "$SECRETS"
upsert_secret "PODCAST_FEED_BASE_URL" "$PODCAST_FEED_BASE_URL" "$SECRETS"

# Warn if app.defaults bucket drifts from Terraform.
if [[ -f "$APP_DEFAULTS" ]]; then
  CFG_BUCKET="$(python3 -c '
import json
from pathlib import Path
p = Path("'"$APP_DEFAULTS"'")
data = json.loads(p.read_text())
print((data.get("podcast") or {}).get("s3_bucket") or "")
')"
  if [[ -n "$CFG_BUCKET" && "$CFG_BUCKET" != "$TF_BUCKET" ]]; then
    tf_warn "app.defaults podcast.s3_bucket=$CFG_BUCKET differs from Terraform bucket=$TF_BUCKET — update app.defaults.json"
  elif [[ -z "$CFG_BUCKET" ]]; then
    tf_warn "Set podcast.s3_bucket=$TF_BUCKET in config/app.defaults.json"
  else
    tf_log "app.defaults podcast.s3_bucket matches Terraform ($TF_BUCKET)"
  fi
fi

tf_log "Updated $SECRETS (derived CF/feed only; bucket stays in app.defaults)"
tf_log "  PODCAST_CLOUDFRONT_DISTRIBUTION_ID=$PODCAST_CLOUDFRONT_DISTRIBUTION_ID"
tf_log "  PODCAST_FEED_BASE_URL=$PODCAST_FEED_BASE_URL"
echo "Feed URL: ${PODCAST_FEED_BASE_URL}/feed.xml"
echo "Bucket (app.defaults): check podcast.s3_bucket == $TF_BUCKET"
