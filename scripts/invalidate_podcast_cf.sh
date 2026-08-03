#!/usr/bin/env bash
# Invalidate The War Room CloudFront paths (default: /feed.xml).
# Uses secrets.env + boto3 via a small Python helper (no AWS CLI required).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/secrets_env.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

  Invalidate CloudFront for the podcast distribution.

  Options:
    --paths 'a,b'     Comma-separated paths (default: /feed.xml)
    --all-media       Also invalidate /episodes/* and /show/*
    --wait            Poll until the invalidation completes
    -h, --help        Show help

  Requires PODCAST_CLOUDFRONT_DISTRIBUTION_ID in config/secrets/secrets.env
  (synced by ./scripts/tf-apply.sh / sync_podcast_tf_secrets.sh).
EOF
}

PATHS="/feed.xml"
WAIT=0
ALL_MEDIA=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    --paths)
      PATHS="${2:-}"
      shift 2
      ;;
    --all-media)
      ALL_MEDIA=1
      shift
      ;;
    --wait)
      WAIT=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

load_secrets_env "${REPO_ROOT}" || true

if [[ -z "${PODCAST_CLOUDFRONT_DISTRIBUTION_ID:-}" ]]; then
  echo "PODCAST_CLOUDFRONT_DISTRIBUTION_ID missing in secrets.env" >&2
  exit 1
fi

if [[ "$ALL_MEDIA" == "1" ]]; then
  PATHS="/feed.xml,/episodes/*,/show/*"
fi

export INVALIDATE_PATHS="$PATHS"
export INVALIDATE_WAIT="$WAIT"

PYTHON="${REPO_ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

cd "$REPO_ROOT"
exec "$PYTHON" - <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.podcast_rss.s3_publish import invalidate_paths, wait_invalidation
from interview_mux.podcast_rss.settings import resolve_publish_targets

targets = resolve_publish_targets()
dist = targets["distribution_id"]
region = targets["region"]
project = targets["project_name"]
raw = os.environ.get("INVALIDATE_PATHS") or "/feed.xml"
paths = [p.strip() for p in raw.split(",") if p.strip()]
inv_id = invalidate_paths(
    distribution_id=dist,
    paths=paths,
    region=region,
    project_name=project,
)
print(f"Invalidation {inv_id} for {dist}: {', '.join(paths)}")
if os.environ.get("INVALIDATE_WAIT") == "1":
    status = wait_invalidation(
        distribution_id=dist,
        invalidation_id=inv_id,
        region=region,
    )
    print(f"Status: {status}")
PY
