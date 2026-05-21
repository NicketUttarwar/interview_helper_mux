from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.common import assets_root
from pipeline.transcription.adapters import transcribe_aws_cli, transcribe_faster_whisper
from pipeline.transcription.schema import TranscriptDocument


def persist_transcript(
    conn: Any,
    doc: TranscriptDocument,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    from mux_store import create_run, register_asset

    root = assets_root()
    out_dir = root / doc.interview_id / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{doc.revision_id}.json"
    out_path.write_text(json.dumps(doc.to_json_dict(), indent=2), encoding="utf-8")
    rid = run_id or create_run(conn, status="running", orchestration_slug="stt")
    conn.execute(
        """
        INSERT INTO transcript_revision (id, interview_id, revision_label, provider, meta_json)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET provider = excluded.provider, meta_json = excluded.meta_json
        """,
        (
            doc.revision_id,
            doc.interview_id,
            doc.model_id,
            doc.provider,
            json.dumps({"language": doc.language, "duration_ms": doc.duration_ms}, sort_keys=True),
        ),
    )
    conn.commit()
    asset_id = register_asset(
        conn,
        storage_uri=str(out_path),
        kind="transcript_json",
        run_id=rid,
        interview_id=doc.interview_id,
        mime_type="application/json",
        meta={"revision_id": doc.revision_id, "provider": doc.provider},
    )
    return {"revision_id": doc.revision_id, "asset_id": asset_id, "path": str(out_path), "run_id": rid}


def run_stt(
    audio_path: Path,
    *,
    interview_id: str,
    provider: str,
    conn: Any,
    repo_root: Path,
    s3_uri: str | None = None,
    model_size: str = "base",
) -> TranscriptDocument:
    if provider == "faster-whisper":
        doc = transcribe_faster_whisper(audio_path, interview_id=interview_id, model_size=model_size)
    elif provider == "aws":
        doc = transcribe_aws_cli(audio_path, interview_id=interview_id, repo_root=repo_root, s3_uri=s3_uri)
    else:
        raise ValueError(f"Unknown STT provider: {provider}")
    persist_transcript(conn, doc)
    return doc
