#!/usr/bin/env python3
"""Phase 3: Segmentation + snippet manifest (requires transcript JSON on disk)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mux_store import connect, default_sqlite_path, init_db, resolve_active_session_id
from pipeline.common import assets_root, repo_root
from pipeline.scoring.rank import rank_segments_for_session
from pipeline.segmentation.segmenter import persist_segments, segment_transcript
from pipeline.snippet_store.manifest import build_snippet_manifest, write_snippet_manifest
from pipeline.transcription.schema import TranscriptDocument


def main() -> int:
    root = repo_root()

    p = argparse.ArgumentParser(description="Segment transcript and build snippet manifest.")
    p.add_argument("--transcript", default=None, help="Path to transcript JSON")
    p.add_argument("--db", default=None)
    args = p.parse_args()

    conn = connect(args.db or str(default_sqlite_path(root)))
    init_db(conn)
    try:
        session_id = resolve_active_session_id(root, conn)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    tdir = assets_root(root) / session_id / "transcripts"
    if args.transcript:
        tpath = Path(args.transcript)
    else:
        files = sorted(tdir.glob("*.json")) if tdir.is_dir() else []
        if not files:
            print("No transcript found. Run tools/run_stt.py first.", file=sys.stderr)
            return 1
        tpath = files[-1]

    doc = TranscriptDocument.model_validate(json.loads(tpath.read_text(encoding="utf-8")))
    segs = segment_transcript(doc)
    n = persist_segments(conn, session_id, segs)
    ordered = rank_segments_for_session(conn, session_id)
    manifest = build_snippet_manifest(session_id, segs, ordered_ids=ordered, transcript_revision_id=doc.revision_id)
    mpath = write_snippet_manifest(manifest)
    print(f"session_id={session_id} segments={n} manifest={mpath}")
    print("COMPLETED Phase 3 segmentation. Next: python tools/run_preset_a.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
