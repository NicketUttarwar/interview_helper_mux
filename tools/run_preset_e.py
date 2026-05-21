#!/usr/bin/env python3
"""Phase 5: Re-run room and breath polish on an existing master (DSP is also in preset A)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mux_store import (
    connect,
    create_run,
    default_master_wav,
    default_sqlite_path,
    init_db,
    register_asset,
    resolve_active_session_id,
    touch_run,
)
from pipeline.common import assets_root, repo_root
from pipeline.dsp.room_polish import apply_room_polish


def main() -> int:
    root = repo_root()

    p = argparse.ArgumentParser(description="Preset E: denoise + room polish on a single timeline.")
    p.add_argument(
        "--input",
        default=None,
        help="Master or reel WAV (default: active session processed/room_polish_master.wav or master/)",
    )
    p.add_argument("--db", default=None)
    args = p.parse_args()

    conn = connect(args.db or str(default_sqlite_path(root)))
    init_db(conn)
    try:
        session_id = resolve_active_session_id(root, conn)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.input:
        inp = Path(args.input).resolve()
    else:
        polished = default_master_wav(root, session_id)
        master = assets_root(root) / session_id / "master" / "highlight_master.wav"
        inp = polished if polished.is_file() else master

    if not inp.is_file():
        print(f"Input not found: {inp}. Run tools/run_preset_a.py first.", file=sys.stderr)
        return 1

    run_id = create_run(conn, status="running", orchestration_slug="preset_e_room_polish")

    out = assets_root(root) / session_id / "processed" / "room_polish_master.wav"
    apply_room_polish(inp, out, conn=conn)
    register_asset(
        conn,
        storage_uri=str(out),
        kind="audio_master_polished",
        run_id=run_id,
        interview_id=session_id,
        mime_type="audio/wav",
        meta={"preset": "E"},
    )
    touch_run(conn, run_id, status="completed")
    print(f"session_id={session_id} output={out}")
    print("COMPLETED Phase 5 preset E.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
