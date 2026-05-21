from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from pipeline.transcription.schema import TranscriptDocument, TranscriptSegment, TranscriptWord


def _parse_aws_transcript(payload: dict[str, Any], *, session_id: str, job_name: str) -> TranscriptDocument:
    results = payload.get("results", {})
    items = results.get("items", [])
    revision_id = str(uuid.uuid4())
    segments: list[TranscriptSegment] = []
    buf_words: list[TranscriptWord] = []
    buf_text: list[str] = []
    seg_start: int | None = None
    seg_end: int | None = None
    idx = 0

    def flush():
        nonlocal idx, seg_start, seg_end, buf_words, buf_text
        if seg_start is None:
            return
        segments.append(
            TranscriptSegment(
                segment_index=idx,
                start_ms=seg_start,
                end_ms=seg_end or seg_start,
                text=" ".join(buf_text).strip(),
                words=list(buf_words),
            )
        )
        idx += 1
        buf_words = []
        buf_text = []
        seg_start = None
        seg_end = None

    for item in items:
        if item.get("type") != "pronunciation":
            continue
        start_ms = int(float(item["start"]) * 1000)
        end_ms = int(float(item["end"]) * 1000)
        word = item["alternatives"][0]["content"]
        conf = float(item["alternatives"][0].get("confidence", 0))
        if seg_start is None:
            seg_start = start_ms
        seg_end = end_ms
        buf_words.append(TranscriptWord(word=word, start_ms=start_ms, end_ms=end_ms, confidence=conf))
        buf_text.append(word)
    flush()

    return TranscriptDocument(
        session_id=session_id,
        revision_id=revision_id,
        provider="aws-transcribe",
        model_id=job_name,
        language=results.get("language_code", "en-US").split("-")[0],
        segments=segments,
    )


def transcribe_aws_cli(
    audio_path: Path,
    *,
    session_id: str,
    repo_root: Path,
    s3_uri: str | None = None,
    poll_sec: float = 5.0,
    max_wait_sec: float = 3600,
) -> TranscriptDocument:
    """
    Start AWS Transcribe job via CLI, poll, fetch transcript JSON from output URI.
    Requires S3 URI for input unless caller pre-uploaded; pass ``s3_uri`` explicitly.
    """
    from aws_mux import run_aws_cli

    if not s3_uri:
        raise ValueError("aws transcribe requires s3_uri (upload with aws s3 cp first)")

    job_name = f"mux-{session_id}-{uuid.uuid4().hex[:8]}"
    media_format = audio_path.suffix.lstrip(".") or "wav"
    run_aws_cli(
        [
            "transcribe",
            "start-transcription-job",
            "--transcription-job-name",
            job_name,
            "--media",
            f"MediaFileUri={s3_uri}",
            f"MediaFormat={media_format}",
            "--language-code",
            "en-US",
        ],
        repo_root=repo_root,
    )
    deadline = time.time() + max_wait_sec
    status = "IN_PROGRESS"
    transcript_uri = ""
    while time.time() < deadline:
        data = run_aws_cli(
            ["transcribe", "get-transcription-job", "--transcription-job-name", job_name],
            repo_root=repo_root,
        )
        job = data.get("TranscriptionJob", {}) if isinstance(data, dict) else {}
        status = job.get("TranscriptionJobStatus", status)
        if status == "COMPLETED":
            transcript_uri = job.get("Transcript", {}).get("TranscriptFileUri", "")
            break
        if status == "FAILED":
            raise RuntimeError(f"Transcribe job failed: {job.get('FailureReason')}")
        time.sleep(poll_sec)
    if status != "COMPLETED" or not transcript_uri:
        raise TimeoutError(f"Transcribe job {job_name} did not complete in {max_wait_sec}s")

    with urlopen(transcript_uri) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return _parse_aws_transcript(payload, session_id=session_id, job_name=job_name)
