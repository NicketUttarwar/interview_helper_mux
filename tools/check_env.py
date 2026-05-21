#!/usr/bin/env python3
"""Step 3 gate: secrets, ASSETS, SQLite doc sync."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mux_secrets import load_repo_config
from mux_store import (
    connect,
    default_assets_path,
    default_sqlite_path,
    init_db,
    resolve_input_audio_path,
    resolve_interview_id,
    sync_markdown_tree,
)
from pipeline.common import repo_root


def main() -> int:
    p = argparse.ArgumentParser(description="Step 3 environment check")
    p.add_argument("--repo", default=None, help="Repository root (default: auto-detect)")
    p.add_argument("--min-docs", type=int, default=50)
    p.add_argument("--sync", action="store_true", default=True, help="Run doc sync (default: on)")
    p.add_argument("--no-sync", action="store_false", dest="sync")
    args = p.parse_args()
    repo = Path(args.repo).resolve() if args.repo else repo_root()

    print("=== Step 3: config and store ===")
    fail = False

    secrets = repo / "config" / "secrets" / "secrets.env"
    if secrets.is_file():
        print(f"  OK   secrets.env exists ({secrets})")
        text = secrets.read_text(encoding="utf-8")
        if "OPENAI_API_KEY=" in text and not text.split("OPENAI_API_KEY=", 1)[1].splitlines()[0].strip():
            print("  OK   OPENAI_API_KEY set (LLM ranking available)")
        else:
            print("  WARN OPENAI_API_KEY empty — use run_preset_a.py --no-llm or fill secrets")
    else:
        print("  FAIL secrets.env missing")
        print("       cp config/templates/secrets.env.example config/secrets/secrets.env")
        fail = True

    assets = default_assets_path(repo)
    assets.mkdir(parents=True, exist_ok=True)
    print(f"  OK   assets root ({assets})")

    load_repo_config(repo)
    try:
        iid = resolve_interview_id(repo)
        print(f"  OK   interview_id={iid}")
    except ValueError as e:
        print(f"  WARN {e}")
    try:
        wav = resolve_input_audio_path(repo)
        print(f"  OK   input_audio_path={wav}")
    except FileNotFoundError as e:
        print(f"  WARN {e}")
    except ValueError as e:
        print(f"  WARN {e}")

    db_path = default_sqlite_path(repo)
    if args.sync:
        conn = connect(str(db_path))
        init_db(conn)
        n = sync_markdown_tree(conn, repo)
        conn.close()
        print(f"  OK   synced {n} markdown files → {db_path}")
    else:
        print(f"  WARN skipped doc sync (--no-sync)")

    conn = connect(str(db_path))
    doc_count = conn.execute("SELECT COUNT(*) FROM doc_source").fetchone()[0]
    conn.close()
    if doc_count >= args.min_docs:
        print(f"  OK   doc_source rows: {doc_count}")
    else:
        print(f"  FAIL doc_source rows: {doc_count} (expected >= {args.min_docs})")
        fail = True

    print("=== Step 3 smoke matrix (run manually) ===")
    print("  python tools/openai_smoke.py     # optional if --no-llm")
    print("  python tools/aws_smoke.py        # only for --provider aws")
    print("  python tools/elevenlabs_smoke.py # not required for A–E")

    print("=== Step 3 complete ===")
    if fail:
        return 1
    print("PASS — proceed to Step 4: pytest -q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
