from __future__ import annotations

import json
from pathlib import Path

from pipeline.common import assets_root
from pipeline.transcription.schema import TranscriptDocument


def load_latest_transcript(
    session_id: str,
    *,
    repo_root: Path | None = None,
) -> TranscriptDocument:
    """Load the newest transcript JSON for a session from ASSETS."""
    root = assets_root(repo_root)
    tdir = root / session_id / "transcripts"
    if not tdir.is_dir():
        raise FileNotFoundError(f"No transcripts directory: {tdir}")
    files = sorted(tdir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No transcript JSON in {tdir}")
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    return TranscriptDocument.model_validate(data)
