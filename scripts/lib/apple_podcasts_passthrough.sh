#!/usr/bin/env bash
# Print Apple Podcasts Connect pass-through whenever a public RSS URL is shown.
#
# Canonical builder: interview_mux.podcast_rss.settings
#   apple_podcasts_passthrough_url / print_apple_passthrough_notice
#
# Source after REPO_ROOT is set (terraform-common.sh does this). Feed is passed
# via env, not argv interpolation, so shell metacharacters cannot break Python.
#
# Usage:
#   print_apple_passthrough_notice "https://dxxxx.cloudfront.net/feed.xml"
#   apple_podcasts_passthrough_url "https://..."   # URL only (stdout)

_apple_passthrough_python() {
  local py=""
  if [[ -n "${REPO_ROOT:-}" && -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    py="${REPO_ROOT}/.venv/bin/python"
  else
    py="$(command -v python3 || true)"
  fi
  echo "$py"
}

# URL-only (safe https feed → encoded pass-through). Empty stdout if invalid.
apple_podcasts_passthrough_url() {
  local feed="${1:-}"
  local py
  py="$(_apple_passthrough_python)"
  if [[ -z "$py" ]]; then
    return 0
  fi
  REPO_ROOT="${REPO_ROOT:-}" FEED_URL="$feed" "$py" - <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

root = Path(os.environ.get("REPO_ROOT") or ".")
src = root / "src"
if src.is_dir():
    sys.path.insert(0, str(src))
try:
    from interview_mux.podcast_rss.settings import apple_podcasts_passthrough_url as _build
    print(_build(os.environ.get("FEED_URL") or ""), end="")
except Exception:
    text = (os.environ.get("FEED_URL") or "").strip()
    if (not text) or any(ch in text for ch in "\r\n\t \"'<>\\"):
        raise SystemExit(0)
    parsed = urlparse(text)
    if parsed.scheme not in ("https", "http") or parsed.username or parsed.password or not parsed.netloc:
        raise SystemExit(0)
    print(
        "https://podcastsconnect.apple.com/my-podcasts/new-feed?submitfeed="
        + quote(text, safe=""),
        end="",
    )
PY
}

# Full operator block: feed URL, pass-through, then the empty-feed notice.
print_apple_passthrough_notice() {
  local feed="${1:-}"
  local include_feed="${2:-1}"
  local py
  py="$(_apple_passthrough_python)"
  if [[ -z "$py" ]]; then
    echo "Apple Podcasts Connect pass-through: set REPO_ROOT and python3 to print the submit URL" >&2
    return 0
  fi
  REPO_ROOT="${REPO_ROOT:-}" FEED_URL="$feed" INCLUDE_FEED="$include_feed" "$py" - <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

root = Path(os.environ.get("REPO_ROOT") or ".")
src = root / "src"
if src.is_dir():
    sys.path.insert(0, str(src))
include_feed = os.environ.get("INCLUDE_FEED") != "0"
try:
    from interview_mux.podcast_rss.settings import print_apple_passthrough_notice as _print
    _print(os.environ.get("FEED_URL") or "", include_feed=include_feed)
except Exception:
    text = (os.environ.get("FEED_URL") or "").strip()
    if (not text) or any(ch in text for ch in "\r\n\t \"'<>\\"):
        raise SystemExit(0)
    parsed = urlparse(text)
    if parsed.scheme not in ("https", "http") or parsed.username or parsed.password or not parsed.netloc:
        raise SystemExit(0)
    passthrough = (
        "https://podcastsconnect.apple.com/my-podcasts/new-feed?submitfeed="
        + quote(text, safe="")
    )
    if include_feed:
        print(f"RSS feed URL: {text}")
    print("Apple Podcasts Connect pass-through (copy this; pre-fills the RSS field):")
    print(f"  {passthrough}")
    print()
    print(
        "Notice: Apple Podcasts Connect rejects an empty seed feed (no episodes). "
        "Publish at least one episode or a trailer, then open the pass-through URL. "
        "It only pre-fills the RSS field; it does not skip validation."
    )
PY
}
