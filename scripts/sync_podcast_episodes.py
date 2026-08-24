#!/usr/bin/env python3
"""Upload a ready local episode package to S3 (current run by default).

Additive only — never deletes remote objects. Skips executions already listed
in catalog/by_execution_id.json. Skips PutObject when remote size matches.

App paths (GUI / Full-auto) always sync one ``execution_id``. This CLI matches
that default; use ``--all`` only for an explicit bulk of every ready package.

Prints the Apple Podcasts Connect pass-through after the JSON result whenever
a public feed URL is known (see print_apple_passthrough_notice).

Usage:
  python scripts/sync_podcast_episodes.py --execution-id exec_...
  python scripts/sync_podcast_episodes.py --execution-id exec_... --dry-run
  python scripts/sync_podcast_episodes.py --all
  python scripts/sync_podcast_episodes.py --all --force-files
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.podcast_rss.settings import print_apple_passthrough_notice  # noqa: E402
from interview_mux.podcast_rss.sync_assets import sync_ready_packages  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sync a ready ASSETS episode package to The War Room S3/RSS "
            "(never deletes; default is one execution_id)."
        )
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument(
        "--execution-id",
        metavar="ID",
        help="Upload only this execution's complete publish/ package",
    )
    scope.add_argument(
        "--all",
        action="store_true",
        help="Explicit bulk: upload every ready package under ASSETS/executions",
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

    if args.all:
        result = sync_ready_packages(
            dry_run=args.dry_run,
            force_files=args.force_files,
            all_ready=True,
        )
    else:
        result = sync_ready_packages(
            dry_run=args.dry_run,
            force_files=args.force_files,
            execution_id=args.execution_id,
        )
    print(json.dumps(result.to_dict(), indent=2))
    # Always show Apple's pass-through next to the live feed URL.
    print_apple_passthrough_notice(result.feed_url, include_feed=False)
    if result.errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
