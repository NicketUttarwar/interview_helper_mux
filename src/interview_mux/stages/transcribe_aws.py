from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, require_secret
from interview_mux.operator_subprocess import format_command, run_command, touch_job_message
from interview_mux.operator_trace import log_api_call
from interview_mux.run_context import RunContext


def _aws(ctx: RunContext, *args: str) -> Any:
    cmd = ["aws", *args]
    operation = " ".join(args[:3]) if len(args) >= 3 else " ".join(args)
    log_api_call("AWS", operation, ctx=ctx, stage="transcribe", detail={"cmd": cmd})
    return run_command(cmd, ctx=ctx, stage="transcribe", label=format_command(cmd))


def _read_transcript_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"Transcript download is empty: {path}")
    if text.startswith("<?xml") or text.startswith("<Error"):
        raise RuntimeError(
            "Transcript download failed with an S3 access error. "
            "Verify AWS credentials and bucket permissions for s3:GetObject."
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Transcript file is not valid JSON ({path}): {exc}") from exc


def run_transcribe(ctx: RunContext) -> None:
    cfg = merged_config()
    secrets = cfg.get("secrets") or {}
    bucket = secrets.get("AWS_S3_BUCKET") or require_secret("AWS_S3_BUCKET")
    input_key = secrets.get("AWS_S3_INPUT_KEY") or f"interview_mux/{ctx.run_id}/normalized.wav"
    output_key = f"interview_mux/{ctx.run_id}/transcribe-output.json"
    region = secrets.get("AWS_DEFAULT_REGION") or secrets.get("AWS_REGION") or "us-east-1"

    normalized = ctx.path("ingest", "normalized.wav")
    if not normalized.is_file():
        raise FileNotFoundError(normalized)

    s3_uri = f"s3://{bucket}/{input_key}"
    ctx.log(
        f"Transcribe: uploading normalized audio to {s3_uri}",
        level="action",
        stage="transcribe",
        detail={"journey_kind": "execute"},
    )
    touch_job_message(ctx, "Transcribe: uploading audio…")
    _aws(ctx, "s3", "cp", str(normalized), s3_uri)

    job_name = f"imux-{ctx.run_id}-{uuid.uuid4().hex[:8]}"
    media_uri = s3_uri
    out_dir = ctx.path("transcript")
    out_dir.mkdir(parents=True, exist_ok=True)

    ctx.log(
        f"Transcribe: starting AWS Transcribe job {job_name}",
        level="action",
        stage="transcribe",
        detail={"journey_kind": "execute", "job_name": job_name},
    )
    touch_job_message(ctx, "Transcribe: starting AWS job…")
    _aws(
        ctx,
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
        output_key,
        "--settings",
        "ShowSpeakerLabels=true,MaxSpeakerLabels=4",
        "--region",
        region,
    )

    status = "IN_PROGRESS"
    poll_count = 0
    while status in ("IN_PROGRESS", "QUEUED"):
        time.sleep(5)
        poll_count += 1
        if poll_count == 1 or poll_count % 6 == 0:
            touch_job_message(ctx, f"Transcribe: waiting on AWS ({status.lower()})…")
            ctx.log(
                f"AWS Transcribe job {job_name}: polling ({status})",
                level="info",
                stage="transcribe",
                detail={"journey_kind": "execute", "poll": poll_count},
            )
        proc = _aws(
            ctx,
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

    ctx.log(
        f"Transcribe: downloading result s3://{bucket}/{output_key}",
        level="action",
        stage="transcribe",
        detail={"journey_kind": "execute"},
    )
    touch_job_message(ctx, "Transcribe: downloading result…")
    local_out = out_dir / "aws_raw.json"
    _aws(ctx, "s3", "cp", f"s3://{bucket}/{output_key}", str(local_out))

    raw = _read_transcript_json(local_out)
    full, speakers = _normalize_transcript(raw)
    ctx.write_json("transcript/full.json", full)
    ctx.write_json("transcript/speakers.json", speakers)
    ctx.log(
        f"Transcription complete — {len(full.get('words') or [])} words, "
        f"{len(speakers.get('speakers') or [])} speaker(s).",
        level="success",
        stage="transcribe",
    )
    ctx.mark_done("transcribe")


def _normalize_transcript(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    results = raw.get("results") or {}
    items = results.get("items") or []
    segments = (results.get("speaker_labels") or {}).get("segments") or []
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
