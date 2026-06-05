from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, require_secret
from interview_mux.run_context import RunContext


def _aws(*args: str, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["aws", *args],
        check=True,
        capture_output=capture,
        text=True,
    )


def run_transcribe(ctx: RunContext) -> None:
    cfg = merged_config()
    secrets = cfg.get("secrets") or {}
    bucket = secrets.get("AWS_S3_BUCKET") or require_secret("AWS_S3_BUCKET")
    key = secrets.get("AWS_S3_INPUT_KEY") or f"interview_mux/{ctx.run_id}/normalized.wav"
    region = secrets.get("AWS_DEFAULT_REGION") or secrets.get("AWS_REGION") or "us-east-1"

    normalized = ctx.path("ingest", "normalized.wav")
    if not normalized.is_file():
        raise FileNotFoundError(normalized)

    s3_uri = f"s3://{bucket}/{key}"
    _aws("s3", "cp", str(normalized), s3_uri)

    job_name = f"imux-{ctx.run_id}-{uuid.uuid4().hex[:8]}"
    media_uri = s3_uri
    out_dir = ctx.path("transcript")
    out_dir.mkdir(parents=True, exist_ok=True)

    _aws(
        "transcribe",
        "start-transcription-job",
        "--transcription-job-name",
        job_name,
        "--language-code",
        "en-US",
        "--media-format",
        "wav",
        "--media",
        f"MediaFileUri={media_uri}",
        "--output-bucket-name",
        bucket,
        "--output-key",
        f"interview_mux/{ctx.run_id}/transcribe-output.json",
        "--settings",
        "ShowSpeakerLabels=true,MaxSpeakerLabels=4",
        "--region",
        region,
    )

    status = "IN_PROGRESS"
    while status in ("IN_PROGRESS", "QUEUED"):
        time.sleep(5)
        proc = _aws(
            "transcribe",
            "get-transcription-job",
            "--transcription-job-name",
            job_name,
            "--region",
            region,
        )
        job = json.loads(proc.stdout)["TranscriptionJob"]
        status = job["TranscriptionJobStatus"]
        if status == "FAILED":
            raise RuntimeError(job.get("FailureReason", "Transcribe failed"))

    transcript_uri = job["Transcript"]["TranscriptFileUri"]
    # Download via aws s3 if s3 URI, else curl
    local_out = out_dir / "aws_raw.json"
    if transcript_uri.startswith("s3://"):
        _aws("s3", "cp", transcript_uri, str(local_out))
    else:
        subprocess.run(["curl", "-sL", transcript_uri, "-o", str(local_out)], check=True)

    raw = json.loads(local_out.read_text(encoding="utf-8"))
    full, speakers = _normalize_transcript(raw)
    ctx.write_json("transcript/full.json", full)
    ctx.write_json("transcript/speakers.json", speakers)
    ctx.mark_done("transcribe")


def _normalize_transcript(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    results = raw.get("results") or {}
    items = results.get("items") or []
    segments = results.get("speaker_labels", {}).get("segments") or []
    words: list[dict[str, Any]] = []
    for item in items:
        if item.get("type") != "pronunciation":
            continue
        start = float(item.get("start_time", 0))
        end = float(item.get("end_time", start))
        alt = (item.get("alternatives") or [{}])[0]
        conf_raw = alt.get("confidence")
        confidence = float(conf_raw) if conf_raw is not None else None
        words.append(
            {
                "text": alt.get("content", ""),
                "start_ms": int(start * 1000),
                "end_ms": int(end * 1000),
                "speaker_id": item.get("speaker_label"),
                "confidence": confidence,
            }
        )
    speaker_ids = sorted({w["speaker_id"] for w in words if w.get("speaker_id")})
    speakers = {
        "speakers": [{"id": sid, "role": "unknown"} for sid in speaker_ids],
    }
    full_text = (results.get("transcripts") or [{}])[0].get("transcript", "")
    return {
        "text": full_text,
        "words": words,
        "segments": segments,
    }, speakers
