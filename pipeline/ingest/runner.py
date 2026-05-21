from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from pipeline.common import assets_root, sha256_file


def _ffmpeg_to_wav(input_path: Path, output_path: Path, *, apply_loudnorm: bool) -> None:
    """Convert to mono 48 kHz WAV; optionally apply EBU R128 loudnorm."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-ac", "1", "-ar", "48000"]
    if apply_loudnorm:
        cmd.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])
    cmd.append(str(output_path))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip() or proc.stdout.strip()}")


def ingest_audio(
    *,
    input_path: Path,
    interview_id: str,
    repo_root: Path,
    conn: Any,
    run_id: str | None = None,
    skip_loudnorm: bool = False,
) -> dict[str, Any]:
    """
    ffmpeg normalize → register normalized WAV in mux_store.
    Returns dict with asset_id, storage_uri, sha256.
    """
    from mux_store import create_run, register_asset, upsert_interview
    from pipeline.ingest.warnings import warn_if_likely_non_speech

    warn_if_likely_non_speech(input_path)
    root = assets_root(repo_root)
    out_dir = root / interview_id / "ingest"
    out_path = out_dir / "normalized.wav"
    _ffmpeg_to_wav(input_path.resolve(), out_path, apply_loudnorm=not skip_loudnorm)
    digest = sha256_file(out_path)
    rid = run_id or create_run(conn, status="running", orchestration_slug="ingest")
    asset_id = register_asset(
        conn,
        storage_uri=str(out_path),
        kind="audio_normalized",
        run_id=rid,
        interview_id=interview_id,
        sha256=digest,
        byte_length=out_path.stat().st_size,
        mime_type="audio/wav",
        meta={
            "source": str(input_path.resolve()),
            "ffmpeg": "mono 48k" + (" + loudnorm" if not skip_loudnorm else ", no loudnorm"),
        },
    )
    upsert_interview(conn, interview_id, title=interview_id)
    return {
        "run_id": rid,
        "asset_id": asset_id,
        "storage_uri": str(out_path),
        "sha256": digest,
        "manifest": json.dumps({"interview_id": interview_id, "normalized": str(out_path)}, indent=2),
    }
