#!/usr/bin/env python3
"""Phase 1: ffmpeg normalize → register asset in mux_store."""

from __future__ import annotations

import argparse
import sys

from mux_store import (
    allocate_session_id,
    connect,
    create_run,
    default_sqlite_path,
    init_db,
    resolve_input_audio_path,
    set_active_session_id,
)
from pipeline.common import repo_root
from pipeline.ingest.runner import ingest_audio


def main() -> int:
    root = repo_root()

    p = argparse.ArgumentParser(description="Ingest and normalize interview audio.")
    p.add_argument(
        "--input",
        default=None,
        help="Source WAV (default: INPUT_AUDIO_PATH / input_audio_path in config)",
    )
    p.add_argument("--db", default=None, help="SQLite path")
    p.add_argument(
        "--skip-ingest-loudnorm",
        action="store_true",
        help="Convert to mono 48k WAV without ffmpeg loudnorm (avoid double-LUFS with master)",
    )
    args = p.parse_args()

    try:
        input_path = resolve_input_audio_path(root, cli=args.input)
    except (ValueError, FileNotFoundError) as e:
        print(str(e), file=sys.stderr)
        return 1

    db_path = args.db or str(default_sqlite_path(root))
    conn = connect(db_path)
    init_db(conn)
    session_id = allocate_session_id(root, conn)
    set_active_session_id(conn, session_id)
    run_id = create_run(conn, status="running", orchestration_slug="ingest")
    result = ingest_audio(
        input_path=input_path,
        session_id=session_id,
        repo_root=root,
        conn=conn,
        run_id=run_id,
        skip_loudnorm=args.skip_ingest_loudnorm,
    )
    print(result["manifest"])
    print(f"session_id={session_id}")
    print("COMPLETED Phase 1 ingest. Next: python tools/run_stt.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
