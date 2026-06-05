from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import communicative_salience_score
from interview_mux.operator_snapshots import persist_operator_transcript

MAX_CHUNK_MS = 30_000
MIN_PAUSE_MS = 700
LOW_CONFIDENCE_THRESHOLD = 0.85


def run_transcript_review_build(ctx: RunContext) -> None:
    """Build ranked review queue and pre-cut WAV clips after transcription."""
    full_path = ctx.path("transcript/full.json")
    if not full_path.is_file():
        raise FileNotFoundError(full_path)

    normalized = ctx.path("ingest/normalized.wav")
    if not normalized.is_file():
        raise FileNotFoundError(normalized)

    full = ctx.read_json("transcript/full.json")
    chunks = _build_chunks(full)
    clips_dir = ctx.path("transcript", "review_clips")
    clips_dir.mkdir(parents=True, exist_ok=True)

    for old in clips_dir.glob("*.wav"):
        old.unlink()

    for chunk in chunks:
        clip_path = clips_dir / f"{chunk['chunk_id']}.wav"
        _extract_clip(normalized, clip_path, chunk["start_ms"], chunk["end_ms"])
        chunk["clip_path"] = f"transcript/review_clips/{chunk['chunk_id']}.wav"

    ranked = sorted(
        chunks,
        key=lambda c: (communicative_salience_score(c), -float(c.get("confidence") or 1.0)),
        reverse=True,
    )
    for rank, chunk in enumerate(ranked, start=1):
        chunk["rank"] = rank
        chunk["reviewed"] = False
        chunk["needs_review"] = chunk["confidence"] < LOW_CONFIDENCE_THRESHOLD

    queue = {
        "version": 1,
        "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
        "chunk_count": len(ranked),
        "chunks": ranked,
    }
    from interview_mux.prompt_validation import validate_transcript_review_queue

    q_errors = validate_transcript_review_queue(queue)
    if q_errors:
        ctx.log(
            f"transcript_review_build: review_queue schema failed: {q_errors[:3]}",
            level="error",
            stage="transcript_review_build",
        )
        raise SystemExit(f"review_queue validation failed: {q_errors[0]}")
    ctx.write_json("transcript/review_queue.json", queue)

    corrections_path = ctx.path("transcript/corrections.json")
    if not corrections_path.is_file():
        ctx.write_json("transcript/corrections.json", {"corrections": {}})

    ctx.mark_done("transcript_review_build")


def check_transcript_review_pending(ctx: RunContext) -> bool:
    """True when review queue exists but operator has not signed off."""
    if ctx.is_done("transcript_review"):
        return False
    return ctx.artifact_exists("transcript/review_queue.json")


def mark_transcript_review_complete(ctx: RunContext) -> None:
    """Apply saved corrections to full.json and close the review gate."""
    if not ctx.artifact_exists("transcript/review_queue.json"):
        raise FileNotFoundError("transcript/review_queue.json — run transcript_review_build first.")
    apply_corrections(ctx)
    if ctx.is_done("speaker_roles"):
        from interview_mux.pipeline import ANALYSIS_ORDER

        ctx.clear_from("speaker_roles", ANALYSIS_ORDER)
    queue = ctx.read_json("transcript/review_queue.json")
    for chunk in queue.get("chunks") or []:
        chunk["reviewed"] = True
    ctx.write_json("transcript/review_queue.json", queue)
    ctx.mark_done("transcript_review")
    ctx.log("Transcript review complete — corrections applied to full.json.", level="success", stage="transcript_review")


def apply_corrections(ctx: RunContext) -> None:
    """Merge operator corrections from corrections.json into transcript/full.json."""
    full = ctx.read_json("transcript/full.json")
    queue = ctx.read_json("transcript/review_queue.json")
    corrections = {}
    if ctx.artifact_exists("transcript/corrections.json"):
        corrections = (ctx.read_json("transcript/corrections.json") or {}).get("corrections") or {}

    chunk_by_id = {c["chunk_id"]: c for c in queue.get("chunks") or []}
    words: list[dict[str, Any]] = list(full.get("words") or [])

    for chunk_id, patch in corrections.items():
        chunk = chunk_by_id.get(chunk_id)
        if not chunk:
            continue
        text = (patch.get("text") or "").strip()
        if not text:
            continue
        words = _replace_words_in_range(
            words,
            chunk["start_ms"],
            chunk["end_ms"],
            text,
            chunk.get("speaker_id"),
        )

    words.sort(key=lambda w: w.get("start_ms", 0))
    full["words"] = words
    full["text"] = " ".join(w["text"] for w in words if w.get("text"))
    full["review_applied_at"] = datetime.now(timezone.utc).isoformat()
    ctx.write_json("transcript/full.json", full)
    persist_operator_transcript(ctx, source="review_complete", include_corrections=True)


def save_chunk_correction(ctx: RunContext, chunk_id: str, text: str, *, reviewed: bool = True) -> dict[str, Any]:
    """Persist a single chunk correction and mirror into the review queue."""
    data = ctx.read_json("transcript/corrections.json") if ctx.artifact_exists("transcript/corrections.json") else {"corrections": {}}
    corrections = data.setdefault("corrections", {})
    corrections[chunk_id] = {"text": text.strip(), "reviewed": reviewed}

    queue = ctx.read_json("transcript/review_queue.json")
    for chunk in queue.get("chunks") or []:
        if chunk.get("chunk_id") == chunk_id:
            chunk["corrected_text"] = text.strip()
            chunk["reviewed"] = reviewed
            break

    ctx.write_json("transcript/corrections.json", data)
    ctx.write_json("transcript/review_queue.json", queue)
    persist_operator_transcript(ctx, source="chunk_save", include_corrections=True)
    return {"ok": True, "chunk_id": chunk_id}


def get_transcript_state(ctx: RunContext) -> dict[str, Any]:
    """Word-level transcript for the dock editor (karaoke sync + inline edits)."""
    if not ctx.artifact_exists("transcript/full.json"):
        return {"ready": False, "words": [], "duration_ms": 0}
    full = ctx.read_json("transcript/full.json")
    words: list[dict[str, Any]] = list(full.get("words") or [])
    duration_ms = max((w.get("end_ms") or 0) for w in words) if words else 0
    speakers: list[dict[str, Any]] = []
    if ctx.artifact_exists("transcript/speakers.json"):
        speakers = (ctx.read_json("transcript/speakers.json") or {}).get("speakers") or []
    audio_path = "ingest/normalized.wav" if ctx.artifact_exists("ingest/normalized.wav") else None
    return {
        "ready": True,
        "text": full.get("text") or "",
        "words": words,
        "duration_ms": duration_ms,
        "speakers": speakers,
        "audio_path": audio_path,
        "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
        "review_applied_at": full.get("review_applied_at"),
    }


def patch_transcript_words(ctx: RunContext, updates: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply inline word edits from the dock viewer without interrupting playback."""
    if not ctx.artifact_exists("transcript/full.json"):
        raise FileNotFoundError("transcript/full.json — run transcribe first.")
    full = ctx.read_json("transcript/full.json")
    words: list[dict[str, Any]] = list(full.get("words") or [])
    applied = 0
    for upd in updates:
        idx = upd.get("index")
        text = (upd.get("text") or "").strip()
        if not isinstance(idx, int) or idx < 0 or idx >= len(words) or not text:
            continue
        words[idx]["text"] = text
        words[idx]["corrected"] = True
        applied += 1
    if applied:
        full["words"] = words
        full["text"] = " ".join(w["text"] for w in words if w.get("text"))
        ctx.write_json("transcript/full.json", full)
        persist_operator_transcript(ctx, source="dock_edit")
        ctx.log(
            f"Transcript dock: saved {applied} word edit(s).",
            level="info",
            stage="transcript_review",
        )
    return {"ok": True, "updated_count": applied, "words": words, "text": full.get("text") or ""}


def get_review_state(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("transcript/review_queue.json"):
        return {"ready": False, "chunks": [], "complete": ctx.is_done("transcript_review")}
    queue = ctx.read_json("transcript/review_queue.json")
    chunks = list(queue.get("chunks") or [])
    pending = sum(1 for c in chunks if not c.get("reviewed"))
    return {
        "ready": True,
        "complete": ctx.is_done("transcript_review"),
        "low_confidence_threshold": queue.get("low_confidence_threshold", LOW_CONFIDENCE_THRESHOLD),
        "chunk_count": len(chunks),
        "pending_count": pending,
        "chunks": chunks,
    }


def _build_chunks(full: dict[str, Any]) -> list[dict[str, Any]]:
    words = full.get("words") or []
    raw_segments = full.get("segments") or []
    if raw_segments:
        return _chunks_from_speaker_segments(words, raw_segments)
    return _chunks_from_words(words)


def _chunks_from_speaker_segments(words: list[dict[str, Any]], segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    seq = 0
    for seg in segments:
        start_ms = int(float(seg.get("start_time", 0)) * 1000)
        end_ms = int(float(seg.get("end_time", start_ms / 1000)) * 1000)
        speaker = seg.get("speaker_label")
        span_words = _words_in_range(words, start_ms, end_ms)
        for sub_start, sub_end, sub_words in _split_on_pauses(span_words, start_ms, end_ms):
            seq += 1
            chunks.append(_make_chunk(seq, sub_start, sub_end, speaker, sub_words))
    return chunks


def _chunks_from_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not words:
        return []
    chunks: list[dict[str, Any]] = []
    seq = 0
    bucket: list[dict[str, Any]] = []
    bucket_start = words[0]["start_ms"]
    bucket_speaker = words[0].get("speaker_id")

    for i, w in enumerate(words):
        bucket.append(w)
        pause_after = False
        if i + 1 < len(words):
            pause_after = words[i + 1]["start_ms"] - w["end_ms"] >= MIN_PAUSE_MS
        duration = w["end_ms"] - bucket_start
        if pause_after or duration >= MAX_CHUNK_MS or i == len(words) - 1:
            seq += 1
            chunks.append(
                _make_chunk(seq, bucket_start, w["end_ms"], bucket_speaker, bucket)
            )
            bucket = []
            if i + 1 < len(words):
                bucket_start = words[i + 1]["start_ms"]
                bucket_speaker = words[i + 1].get("speaker_id")

    return chunks


def _split_on_pauses(
    words: list[dict[str, Any]], start_ms: int, end_ms: int
) -> list[tuple[int, int, list[dict[str, Any]]]]:
    if not words:
        return [(start_ms, end_ms, [])]
    if end_ms - start_ms <= MAX_CHUNK_MS:
        return [(start_ms, end_ms, words)]

    spans: list[tuple[int, int, list[dict[str, Any]]]] = []
    bucket: list[dict[str, Any]] = []
    bucket_start = words[0]["start_ms"]

    for i, w in enumerate(words):
        bucket.append(w)
        pause_after = False
        if i + 1 < len(words):
            pause_after = words[i + 1]["start_ms"] - w["end_ms"] >= MIN_PAUSE_MS
        duration = w["end_ms"] - bucket_start
        if pause_after or duration >= MAX_CHUNK_MS or i == len(words) - 1:
            spans.append((bucket_start, w["end_ms"], bucket))
            bucket = []
            if i + 1 < len(words):
                bucket_start = words[i + 1]["start_ms"]

    return spans or [(start_ms, end_ms, words)]


def _words_in_range(words: list[dict[str, Any]], start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    return [w for w in words if w["start_ms"] >= start_ms - 50 and w["end_ms"] <= end_ms + 50]


def _make_chunk(
    seq: int,
    start_ms: int,
    end_ms: int,
    speaker_id: str | None,
    span_words: list[dict[str, Any]],
) -> dict[str, Any]:
    confs = [w["confidence"] for w in span_words if w.get("confidence") is not None]
    confidence = round(sum(confs) / len(confs), 4) if confs else 0.0
    text = " ".join(w["text"] for w in span_words if w.get("text"))
    return {
        "chunk_id": f"tr_{seq:04d}",
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker_id": speaker_id,
        "text": text,
        "word_count": len(span_words),
        "confidence": confidence,
    }


def _replace_words_in_range(
    words: list[dict[str, Any]],
    start_ms: int,
    end_ms: int,
    text: str,
    speaker_id: str | None,
) -> list[dict[str, Any]]:
    kept = [
        w for w in words if not (w["start_ms"] < end_ms and w["end_ms"] > start_ms)
    ]
    kept.append(
        {
            "text": text,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "speaker_id": speaker_id,
            "confidence": 1.0,
            "corrected": True,
        }
    )
    kept.sort(key=lambda w: w.get("start_ms", 0))
    return kept


def _extract_clip(source: Path, dest: Path, start_ms: int, end_ms: int) -> None:
    start_s = start_ms / 1000.0
    duration_s = max((end_ms - start_ms) / 1000.0, 0.05)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_s:.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration_s:.3f}",
        "-ar",
        "48000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
