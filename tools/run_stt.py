#!/usr/bin/env python3
"""Phase 2: STT → Transcript JSON schema + mux_store."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mux_store import (
    connect,
    create_run,
    default_sqlite_path,
    init_db,
    resolve_active_session_id,
    resolve_s3_uri,
    session_ingest_wav,
)
from pipeline.common import repo_root
from pipeline.transcription.runner import run_stt


def main() -> int:
    root = repo_root()

    p = argparse.ArgumentParser(description="Run STT and persist transcript JSON.")
    p.add_argument("--provider", default="faster-whisper", choices=["faster-whisper", "aws"])
    p.add_argument("--audio", default=None, help="WAV path (default: active session ingest/normalized.wav)")
    p.add_argument(
        "--s3-uri",
        default=None,
        help="For --provider aws (default: AWS_S3_URI or AWS_S3_BUCKET + AWS_S3_INPUT_KEY in secrets.env)",
    )
    p.add_argument("--model-size", default="base")
    p.add_argument("--db", default=None)
    args = p.parse_args()

    conn = connect(args.db or str(default_sqlite_path(root)))
    init_db(conn)
    try:
        session_id = resolve_active_session_id(root, conn)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    audio = Path(args.audio) if args.audio else session_ingest_wav(root, session_id)
    if not audio.is_file():
        print(f"Audio not found: {audio}. Run tools/run_ingest.py first.", file=sys.stderr)
        return 1

    s3_uri: str | None = None
    if args.provider == "aws":
        try:
            s3_uri = resolve_s3_uri(root, cli=args.s3_uri)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1

    create_run(conn, status="running", orchestration_slug="stt")
    doc = run_stt(
        audio,
        session_id=session_id,
        provider=args.provider,
        conn=conn,
        repo_root=root,
        s3_uri=s3_uri,
        model_size=args.model_size,
    )
    print(f"session_id={session_id} revision_id={doc.revision_id} segments={len(doc.segments)}")
    print("COMPLETED Phase 2 STT. Next: python tools/run_preset_a.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
