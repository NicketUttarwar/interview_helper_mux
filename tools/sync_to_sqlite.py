#!/usr/bin/env python3
"""Initialize the canonical SQLite store and sync Markdown from the repository."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    py_path = repo / "db" / "python"
    sys.path.insert(0, str(py_path))

    from mux_store import connect, default_sqlite_path, init_db, sync_markdown_tree

    p = argparse.ArgumentParser(description="Apply schema and sync docs into interview_helper_mux SQLite.")
    p.add_argument("--repo", default=str(repo), help="Repository root (default: parent of tools/)")
    p.add_argument(
        "--db",
        default=None,
        help="Path to SQLite file (default: database_path from config/app.defaults.json)",
    )
    args = p.parse_args()

    repo_root = Path(args.repo).resolve()
    db_path = args.db if args.db else str(default_sqlite_path(repo_root))
    conn = connect(db_path)
    init_db(conn)
    n = sync_markdown_tree(conn, repo_root)
    print(f"Synced {n} markdown files into {db_path}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
