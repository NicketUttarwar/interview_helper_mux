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

    from mux_store import connect, init_db, sync_markdown_tree

    p = argparse.ArgumentParser(description="Apply schema and sync docs into interview_helper_mux SQLite.")
    p.add_argument(
        "--db",
        default=str(repo / "data" / "interview_mux.sqlite"),
        help="Path to SQLite file (default: data/interview_mux.sqlite under repo root)",
    )
    p.add_argument("--repo", default=str(repo), help="Repository root (default: parent of tools/)")
    args = p.parse_args()

    repo_root = Path(args.repo).resolve()
    conn = connect(args.db)
    init_db(conn)
    n = sync_markdown_tree(conn, repo_root)
    print(f"Synced {n} markdown files into {args.db}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
