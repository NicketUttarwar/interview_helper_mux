#!/usr/bin/env python3
"""Phase 4: Preset A highlight reel orchestrator."""

from __future__ import annotations

import argparse
import json
import sys

from mux_store import connect, default_sqlite_path, init_db, resolve_interview_id
from pipeline.common import assets_root, repo_root
from pipeline.orchestrator.preset_a import run_preset_a


def main() -> int:
    root = repo_root()

    p = argparse.ArgumentParser(description="Preset A: STT → rank → crossfade → LUFS.")
    p.add_argument(
        "--interview-id",
        default=None,
        help="Interview id (default: INTERVIEW_ID / interview_id in config)",
    )
    p.add_argument("--top-n", type=int, default=8)
    p.add_argument("--no-llm", action="store_true", help="Heuristic ranking only")
    p.add_argument("--stt-provider", default="faster-whisper")
    p.add_argument("--stt-model-size", default="base")
    p.add_argument(
        "--skip-stt",
        action="store_true",
        help="Reuse latest ASSETS/<id>/transcripts/*.json (run run_stt.py first)",
    )
    p.add_argument(
        "--skip-master-lufs",
        action="store_true",
        help="Copy reel to master without pyloudnorm (if ingest already loudnorm'd)",
    )
    p.add_argument("--db", default=None)
    args = p.parse_args()

    try:
        interview_id = resolve_interview_id(root, cli=args.interview_id)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    wav = assets_root(root) / interview_id / "ingest" / "normalized.wav"
    if not wav.is_file():
        print(f"Missing normalized audio: {wav}. Run tools/run_ingest.py first.", file=sys.stderr)
        return 1

    conn = connect(args.db or str(default_sqlite_path(root)))
    init_db(conn)
    out = run_preset_a(
        interview_id=interview_id,
        normalized_wav=wav,
        conn=conn,
        repo_root=root,
        top_n=args.top_n,
        stt_provider=args.stt_provider,
        use_llm_rank=not args.no_llm,
        skip_stt=args.skip_stt,
        stt_model_size=args.stt_model_size,
        skip_master_lufs=args.skip_master_lufs,
    )
    print(json.dumps(out, indent=2))
    print(
        f"COMPLETED Phase 4 preset A. Next: python tools/run_preset_e.py "
        f"--interview-id {interview_id}"
    )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
