#!/usr/bin/env bash
# Invalidate The War Room CloudFront paths (default: /feed.xml).
# Always uses the *live* feed URL from secrets.env (synced by tf-apply /
# tf-rotate-cloudfront-url.sh). Same helper the app calls on G-Publish sync.
# boto3 only — no AWS CLI required.
#
# After invalidation, prints the Apple Podcasts Connect pass-through next to
# the live feed URL (print_apple_passthrough_notice).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/secrets_env.sh"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/apple_podcasts_passthrough.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

  Invalidate CloudFront for the current podcast RSS URL.

  Reads PODCAST_CLOUDFRONT_DISTRIBUTION_ID and PODCAST_FEED_BASE_URL from
  config/secrets/secrets.env (rewritten by ./scripts/tf-apply.sh and
  ./scripts/tf-rotate-cloudfront-url.sh). The app publish path uses the
  same Python helper (invalidate_current_feed).

  Options:
    --paths 'a,b'     Comma-separated paths (default: /feed.xml)
    --all-media       Also invalidate /episodes/* and /show/*
    --wait            Poll until the invalidation completes
    -h, --help        Show help
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
  echo "Run ./scripts/tf-apply.sh or ./scripts/tf-rotate-cloudfront-url.sh" >&2
  exit 1
fi

if [[ -z "${PODCAST_FEED_BASE_URL:-}" ]]; then
  echo "PODCAST_FEED_BASE_URL missing in secrets.env — cannot target the live RSS URL" >&2
  echo "Run ./scripts/tf-apply.sh or ./scripts/tf-rotate-cloudfront-url.sh" >&2
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

from interview_mux.podcast_rss.s3_publish import invalidate_current_feed
from interview_mux.podcast_rss.settings import print_apple_passthrough_notice

raw = os.environ.get("INVALIDATE_PATHS") or "/feed.xml"
paths = [p.strip() for p in raw.split(",") if p.strip()]
result = invalidate_current_feed(
    paths=paths,
    wait=os.environ.get("INVALIDATE_WAIT") == "1",
)
feed = result.get("feed_url") or result.get("feed_base_url") or "—"
print(
    f"Invalidation {result.get('invalidation_id') or '—'} "
    f"for {feed} ({result.get('distribution_id') or '—'}): {result.get('paths') or raw}"
)
if result.get("status"):
    print(f"Status: {result['status']}")
print_apple_passthrough_notice(result.get("feed_url") or "", include_feed=False)
PY
