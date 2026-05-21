#!/usr/bin/env python3
"""Phase 5: Preset E room and breath polish (gated DSP)."""

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
    resolve_interview_id,
    touch_run,
)
from pipeline.common import assets_root, repo_root
from pipeline.dsp.room_polish import apply_room_polish


def main() -> int:
    root = repo_root()

    p = argparse.ArgumentParser(description="Preset E: denoise + room polish on a single timeline.")
    p.add_argument(
        "--interview-id",
        default=None,
        help="Interview id (default: INTERVIEW_ID / interview_id in config)",
    )
    p.add_argument(
        "--input",
        default=None,
        help="Master or reel WAV (default: ASSETS/<id>/master/highlight_master.wav)",
    )
    p.add_argument("--approve-dsp", action="store_true", help="Acknowledge high-risk DSP gate")
    p.add_argument("--db", default=None)
    args = p.parse_args()

    try:
        interview_id = resolve_interview_id(root, cli=args.interview_id)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    inp = Path(args.input).resolve() if args.input else default_master_wav(root, interview_id)
    if not inp.is_file():
        print(f"Input not found: {inp}. Run tools/run_preset_a.py first.", file=sys.stderr)
        return 1

    conn = connect(args.db or str(default_sqlite_path(root)))
    init_db(conn)
    run_id = create_run(conn, status="running", orchestration_slug="preset_e_room_polish")

    out = assets_root(root) / interview_id / "processed" / "room_polish_master.wav"
    apply_room_polish(inp, out, conn=conn, approve=args.approve_dsp)
    register_asset(
        conn,
        storage_uri=str(out),
        kind="audio_master_polished",
        run_id=run_id,
        interview_id=interview_id,
        mime_type="audio/wav",
        meta={"preset": "E"},
    )
    touch_run(conn, run_id, status="completed")
    print(f"output={out}")
    print("COMPLETED Phase 5 preset E. Pipeline A–E scaffold is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
