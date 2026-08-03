#!/usr/bin/env python3
"""Upload all ready local episode packages under ASSETS/executions to S3.

Additive only — never deletes remote objects. Skips executions already listed
in catalog/by_execution_id.json. Skips PutObject when remote size matches.

Usage:
  python scripts/sync_podcast_episodes.py
  python scripts/sync_podcast_episodes.py --dry-run
  python scripts/sync_podcast_episodes.py --force-files
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.podcast_rss.sync_assets import sync_ready_packages  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync ready ASSETS episode packages to The War Room S3/RSS (never deletes)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List packages that would upload / skip without writing to S3",
    )
    parser.add_argument(
        "--force-files",
        action="store_true",
        help="Re-put episode files even when remote size matches (still no new folder for known execution_ids)",
    )
    args = parser.parse_args()

    result = sync_ready_packages(dry_run=args.dry_run, force_files=args.force_files)
    print(json.dumps(result.to_dict(), indent=2))
    if result.errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
