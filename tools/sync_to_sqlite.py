#!/usr/bin/env python3
"""Initialize the canonical SQLite store and sync Markdown from the repository."""

from __future__ import annotations

import argparse
from pathlib import Path

from mux_store import connect, default_sqlite_path, init_db, sync_markdown_tree
from pipeline.common import repo_root


def main() -> int:
    p = argparse.ArgumentParser(description="Apply schema and sync docs into interview_helper_mux SQLite.")
    p.add_argument("--repo", default=None, help="Repository root (default: auto-detect)")
    p.add_argument(
        "--db",
        default=None,
        help="Path to SQLite file (default: database_path from config/app.defaults.json)",
    )
    args = p.parse_args()

    repo_root_path = Path(args.repo).resolve() if args.repo else repo_root()
    db_path = args.db if args.db else str(default_sqlite_path(repo_root_path))
    conn = connect(db_path)
    init_db(conn)
    n = sync_markdown_tree(conn, repo_root_path)
    print(f"Synced {n} markdown files into {db_path}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
