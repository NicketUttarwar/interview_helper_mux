from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.audio_clips import extract_clip
from interview_mux.audio_energy import find_silence_valley_ms, rms_at_ms
from interview_mux.audio_timeline import snap_cut_to_word_boundary
from interview_mux.config import merged_config
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import communicative_salience_score
from interview_mux.operator_snapshots import persist_operator_transcript

MAX_CHUNK_MS = 30_000
MIN_PAUSE_MS = 700
LOW_CONFIDENCE_THRESHOLD = 0.85  # fallback; prefer first_try.low_confidence_threshold()


def _low_confidence_threshold() -> float:
    return LOW_CONFIDENCE_THRESHOLD


def _transcribe_pending_full(ctx: RunContext) -> Path | None:
    """G0 dock: unapproved transcribe output lives under pending, not the commit tree."""
    from interview_mux.write_staging import staging_root

    staged = staging_root(ctx, "transcribe") / "transcript" / "full.json"
    return staged if staged.is_file() else None


def _transcript_full_exists(ctx: RunContext) -> bool:
    return ctx.artifact_exists("transcript/full.json") or _transcribe_pending_full(ctx) is not None


def _read_transcript_full(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists("transcript/full.json"):
        doc = ctx.read_json("transcript/full.json")
        return doc if isinstance(doc, dict) else {}
    staged = _transcribe_pending_full(ctx)
    if staged is None:
        raise FileNotFoundError("transcript/full.json — run transcribe first.")
    doc = json.loads(staged.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def _review_sort_mode(cfg: dict[str, Any] | None = None) -> str:
    resolved = cfg if cfg is not None else merged_config()
    mode = str((resolved.get("transcript_review") or {}).get("sort_mode") or "salience").strip().lower()
    return mode if mode in {"salience", "confidence"} else "salience"


def _rank_review_chunks(chunks: list[dict[str, Any]], *, sort_mode: str) -> list[dict[str, Any]]:
    if sort_mode == "confidence":
        return sorted(chunks, key=lambda c: float(c.get("confidence") or 1.0))
    return sorted(
        chunks,
        key=lambda c: (communicative_salience_score(c), -float(c.get("confidence") or 1.0)),
        reverse=True,
    )


def run_transcript_review_build(ctx: RunContext) -> None:
    """Build ranked review queue and pre-cut WAV clips after transcription."""
    ctx.artifact_exists_required(
        "transcript/full.json",
        stage="transcript_review_build",
        label="Transcript from transcribe",
    )
    ctx.artifact_exists_required(
        "ingest/normalized.wav",
        stage="transcript_review_build",
        label="Normalized audio from ingest",
    )

    full = ctx.read_json("transcript/full.json")
    normalized = ctx.read_path("ingest", "normalized.wav")
    with logged_step("transcript_review_build/chunk_queue", ctx=ctx, stage="transcript_review_build"):
        chunks = _build_chunks(full)
        clips_dir = ctx.path("transcript", "review_clips")
        clips_dir.mkdir(parents=True, exist_ok=True)

        for old in clips_dir.glob("*.wav"):
            old.unlink()

        for chunk in chunks:
            _refine_chunk_edges(chunk, full.get("words") or [], normalized)
            clip_start = int(chunk.get("clip_start_ms", chunk["start_ms"]))
            clip_end = int(chunk.get("clip_end_ms", chunk["end_ms"]))
            clip_path = clips_dir / f"{chunk['chunk_id']}.wav"
            extract_clip(normalized, clip_path, clip_start, clip_end)
            chunk["clip_path"] = f"transcript/review_clips/{chunk['chunk_id']}.wav"
            chunk["acoustic_stress_score"] = _acoustic_stress_score(normalized, chunk)

        sort_mode = _review_sort_mode()
        ranked = _rank_review_chunks(chunks, sort_mode=sort_mode)
        threshold = _low_confidence_threshold()
        for rank, chunk in enumerate(ranked, start=1):
            chunk["rank"] = rank
            chunk["reviewed"] = False
            chunk["needs_review"] = chunk["confidence"] < threshold

        queue = {
            "version": 1,
            "low_confidence_threshold": threshold,
            "sort_mode": sort_mode,
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

    stress_scores = [float(c.get("acoustic_stress_score") or 0.0) for c in ranked]
    mean_stress = round(statistics.mean(stress_scores), 4) if stress_scores else 0.0
    top_chunks = [
        {
            "chunk_id": c.get("chunk_id"),
            "salience": communicative_salience_score(c),
            "acoustic_stress_score": c.get("acoustic_stress_score"),
        }
        for c in ranked[:5]
    ]
    ctx.log(
        f"G0 review queue built: sort_mode={sort_mode}, {len(ranked)} chunks",
        level="info",
        stage="transcript_review_build",
        detail=json.dumps(
            {
                "sort_mode": sort_mode,
                "chunk_count": len(ranked),
                "mean_acoustic_stress": mean_stress,
                "top_chunks": top_chunks,
            },
            ensure_ascii=False,
        ),
    )

    corrections_path = ctx.path("transcript/corrections.json")
    if not corrections_path.is_file():
        _write_transcript_json(ctx, "transcript/corrections.json", {"corrections": {}})

    ctx.mark_done("transcript_review_build")
    maybe_auto_complete_transcript_review(ctx)


def maybe_auto_complete_transcript_review(ctx: RunContext) -> bool:
    """v2: operator completes G0 explicitly."""
    return False


def check_transcript_review_pending(ctx: RunContext) -> bool:
    """True when review queue exists but operator has not signed off."""
    from interview_mux.gates import check_transcript_review_pending as _gates_check

    return _gates_check(ctx)


def _write_transcript_json(ctx: RunContext, rel: str, data: Any) -> Path:
    """Persist transcript artifacts so deferred staging cannot hide or clobber edits."""
    from interview_mux.prompt_validation import validate_artifact_write
    from interview_mux.write_staging import write_mirrored_json

    if isinstance(data, dict):
        errors = validate_artifact_write(rel, data)
        if errors:
            raise ValueError(f"{rel}: schema validation failed — " + "; ".join(errors[:6]))
    return write_mirrored_json(ctx, rel, data)


def mark_transcript_review_complete(ctx: RunContext) -> None:
    """Apply saved corrections to full.json and close the review gate."""
    if not ctx.artifact_exists("transcript/review_queue.json"):
        raise FileNotFoundError("transcript/review_queue.json — run transcript_review_build first.")
    # G0 UI + reuse expect corrections.json even when the operator saved no text edits.
    if not ctx.artifact_exists("transcript/corrections.json"):
        _write_transcript_json(ctx, "transcript/corrections.json", {"corrections": {}})
    materialize_transcript(ctx, source="review_complete")
    # DETECTION_ONLY_IS_DONE: invalidate downstream when speaker_roles was stamped
    # (hollow or honest) — review rewrite must not leave stale roles.
    if ctx.is_done("speaker_roles"):
        from interview_mux.pipeline import ANALYSIS_ORDER

        ctx.clear_from("speaker_roles", ANALYSIS_ORDER)
    queue = ctx.read_json("transcript/review_queue.json")
    for chunk in queue.get("chunks") or []:
        chunk["reviewed"] = True
    _write_transcript_json(ctx, "transcript/review_queue.json", queue)
    ctx.mark_done("transcript_review")
    from interview_mux.delivery_guardrails import seed_stage_complete

    if not seed_stage_complete(ctx, "transcript_review"):
        raise RuntimeError(
            "transcript_review mark_done refused — G0 sign-off did not stick "
            "(check authority / stage_outputs_present)."
        )
    try:
        from interview_mux.homunculus.gates import try_set_gate_decision

        try_set_gate_decision(ctx, "transcript_integrity", "complete")
    except Exception:
        pass
    ctx.log("Transcript review complete — corrections applied to full.json.", level="success", stage="transcript_review")


def materialize_transcript(ctx: RunContext, *, source: str = "review_complete") -> None:
    """Merge corrections into full.json and refresh operator transcript snapshots."""
    apply_corrections(ctx)
    persist_operator_transcript(ctx, source=source, include_corrections=True)


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
        words = _apply_correction_to_range(
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
    _write_transcript_json(ctx, "transcript/full.json", full)


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

    _write_transcript_json(ctx, "transcript/corrections.json", data)
    _write_transcript_json(ctx, "transcript/review_queue.json", queue)
    return {"ok": True, "chunk_id": chunk_id}


def get_transcript_state(ctx: RunContext) -> dict[str, Any]:
    """Word-level transcript for the dock editor (karaoke sync + inline edits)."""
    from interview_mux.write_staging import artifact_exists_resolved

    if not _transcript_full_exists(ctx):
        return {"ready": False, "words": [], "duration_ms": 0}
    full = _read_transcript_full(ctx)
    words: list[dict[str, Any]] = list(full.get("words") or [])
    duration_ms = max((w.get("end_ms") or 0) for w in words) if words else 0
    speakers: list[dict[str, Any]] = []
    if ctx.artifact_exists("transcript/speakers.json"):
        speakers = (ctx.read_json("transcript/speakers.json") or {}).get("speakers") or []
    audio_rel = "ingest/normalized.wav"
    audio_path = audio_rel if artifact_exists_resolved(ctx, audio_rel) else None
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
    if not _transcript_full_exists(ctx):
        raise FileNotFoundError("transcript/full.json — run transcribe first.")
    full = _read_transcript_full(ctx)
    words: list[dict[str, Any]] = list(full.get("words") or [])
    applied = 0
    edited_indices: list[int] = []
    for upd in updates:
        idx = upd.get("index")
        text = (upd.get("text") or "").strip()
        if not isinstance(idx, int) or idx < 0 or idx >= len(words) or not text:
            continue
        words[idx]["text"] = text
        words[idx]["corrected"] = True
        edited_indices.append(idx)
        applied += 1

    if applied:
        full["words"] = words
        full["text"] = " ".join(w["text"] for w in words if w.get("text"))
        _write_transcript_json(ctx, "transcript/full.json", full)
        synced_chunks = _sync_review_queue_from_word_edits(ctx, words, edited_indices)
        persist_operator_transcript(ctx, source="dock_edit", include_corrections=True)
        ctx.log(
            f"Transcript dock: saved {applied} word edit(s).",
            level="info",
            stage="transcript_review",
        )
        return {
            "ok": True,
            "updated_count": applied,
            "words": words,
            "text": full.get("text") or "",
            "synced_chunk_ids": synced_chunks,
        }
    return {"ok": True, "updated_count": applied, "words": words, "text": full.get("text") or ""}


def transcript_reuse_pending_edit(ctx: RunContext) -> bool:
    from interview_mux.journey_state import read_run_meta

    return bool(read_run_meta(ctx).get("transcript_reuse_pending_edit"))


def set_transcript_reuse_pending_edit(ctx: RunContext, pending: bool) -> None:
    def _mutate(meta: dict[str, Any]) -> None:
        if pending:
            meta["transcript_reuse_pending_edit"] = True
        else:
            meta.pop("transcript_reuse_pending_edit", None)

    ctx.mutate_run_meta(_mutate)


def _tokenize_transcript_text(text: str) -> list[str]:
    return [tok for tok in text.replace("\r\n", "\n").replace("\r", "\n").split() if tok]


def _remap_words_to_text(
    prior_words: list[dict[str, Any]],
    new_text: str,
) -> list[dict[str, Any]]:
    """Rebuild word rows for edited plain text while preserving timing span."""
    tokens = _tokenize_transcript_text(new_text)
    if not tokens:
        return []
    if prior_words and len(prior_words) == len(tokens):
        out: list[dict[str, Any]] = []
        for old, tok in zip(prior_words, tokens):
            row = dict(old) if isinstance(old, dict) else {}
            row["text"] = tok
            row["corrected"] = True
            out.append(row)
        return out

    start_ms = 0
    end_ms = max(int(w.get("end_ms") or 0) for w in prior_words) if prior_words else max(50 * len(tokens), 1000)
    if prior_words:
        start_ms = int(prior_words[0].get("start_ms") or 0)
        end_ms = max(end_ms, start_ms + 50)
    span = max(end_ms - start_ms, 50 * len(tokens))
    step = span / len(tokens)
    speaker = None
    for w in prior_words:
        if isinstance(w, dict) and w.get("speaker_id"):
            speaker = w.get("speaker_id")
            break
    rebuild: list[dict[str, Any]] = []
    for i, tok in enumerate(tokens):
        w_start = int(start_ms + i * step)
        w_end = int(start_ms + (i + 1) * step)
        if w_end <= w_start:
            w_end = w_start + 40
        row: dict[str, Any] = {
            "text": tok,
            "start_ms": w_start,
            "end_ms": w_end,
            "corrected": True,
        }
        if speaker:
            row["speaker_id"] = speaker
        rebuild.append(row)
    return rebuild


def apply_full_transcript_text(
    ctx: RunContext,
    text: str,
    *,
    source: str = "reuse_edit",
) -> dict[str, Any]:
    """Replace transcript plain text (and remapped words), then refresh operator snapshots."""
    if not ctx.artifact_exists("transcript/full.json"):
        raise FileNotFoundError("transcript/full.json — run transcribe first.")
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        raise ValueError("Transcript text cannot be empty.")
    full = ctx.read_json("transcript/full.json")
    prior_words: list[dict[str, Any]] = list(full.get("words") or [])
    words = _remap_words_to_text(prior_words, cleaned)
    full["words"] = words
    full["text"] = " ".join(w["text"] for w in words if w.get("text"))
    full["operator_text_edit_at"] = datetime.now(timezone.utc).isoformat()
    full["operator_text_edit_source"] = source
    _write_transcript_json(ctx, "transcript/full.json", full)
    persist_operator_transcript(ctx, source=source, include_corrections=True)
    ctx.log(
        f"Transcript full-text edit saved ({len(words)} words, source={source}).",
        level="success",
        stage="transcript_review",
        action_id="gui.transcript_reuse.save_text",
        detail={"source": source, "word_count": len(words)},
    )
    return {"ok": True, "text": full["text"], "word_count": len(words), "words": words}


def prefer_operator_corrected_transcript(ctx: RunContext) -> bool:
    """Overlay operator/transcript_corrected.* onto transcript/full.json when present."""
    if not ctx.artifact_exists("operator/transcript_corrected.json"):
        if ctx.artifact_exists("operator/transcript_corrected.txt"):
            raw = ctx.final_path("operator", "transcript_corrected.txt").read_text(encoding="utf-8")
            if raw.strip():
                apply_full_transcript_text(ctx, raw, source="reuse_operator_overlay_txt")
                return True
        return False
    snap = ctx.read_json("operator/transcript_corrected.json")
    if not isinstance(snap, dict):
        return False
    text = str(snap.get("text") or "").strip()
    if not text:
        return False
    snap_words = snap.get("words")
    if isinstance(snap_words, list) and snap_words:
        full = ctx.read_json("transcript/full.json") if ctx.artifact_exists("transcript/full.json") else {}
        if not isinstance(full, dict):
            full = {}
        full["words"] = snap_words
        full["text"] = text
        if snap.get("review_applied_at"):
            full["review_applied_at"] = snap.get("review_applied_at")
        full["operator_text_edit_at"] = datetime.now(timezone.utc).isoformat()
        full["operator_text_edit_source"] = "reuse_operator_overlay"
        _write_transcript_json(ctx, "transcript/full.json", full)
        persist_operator_transcript(ctx, source="reuse_operator_overlay", include_corrections=True)
        return True
    apply_full_transcript_text(ctx, text, source="reuse_operator_overlay")
    return True


def _finalize_reuse_edit_gate(ctx: RunContext, *, source: str) -> None:
    """Clear reuse pending flag and, when a review queue exists, sign off G0."""
    _write_transcript_json(ctx, "transcript/corrections.json", {"corrections": {}})
    if ctx.artifact_exists("transcript/review_queue.json"):
        queue = ctx.read_json("transcript/review_queue.json")
        for chunk in queue.get("chunks") or []:
            if isinstance(chunk, dict):
                chunk["reviewed"] = True
        _write_transcript_json(ctx, "transcript/review_queue.json", queue)
        persist_operator_transcript(ctx, source=source, include_corrections=True)
        if not ctx.is_done("transcript_review"):
            ctx.mark_done("transcript_review")
            ctx.log(
                "Transcript review complete — reuse edit saved as corrected transcript.",
                level="success",
                stage="transcript_review",
                action_id="gui.transcript_reuse.save_and_continue",
            )
    set_transcript_reuse_pending_edit(ctx, False)


def save_reused_transcript_text(ctx: RunContext, text: str) -> dict[str, Any]:
    """Persist interstitial full-text edits after transcript reuse, then clear pending gate."""
    result = apply_full_transcript_text(ctx, text, source="reuse_edit")
    # Full-text / dock editor is the sign-off source of truth — drop stale chunk patches that
    # would otherwise overwrite on a later materialize_transcript.
    _finalize_reuse_edit_gate(ctx, source="reuse_edit")
    return result


def finalize_reused_transcript_from_disk(ctx: RunContext) -> dict[str, Any]:
    """Complete the reuse interstitial using current on-disk transcript (dock-edited words)."""
    if not ctx.artifact_exists("transcript/full.json"):
        raise FileNotFoundError("transcript/full.json — run transcribe first.")
    full = ctx.read_json("transcript/full.json")
    text = str(full.get("text") or "").strip()
    if not text:
        raise ValueError("Transcript text cannot be empty.")
    persist_operator_transcript(ctx, source="reuse_edit_dock", include_corrections=True)
    _finalize_reuse_edit_gate(ctx, source="reuse_edit_dock")
    words = list(full.get("words") or [])
    return {"ok": True, "text": text, "word_count": len(words), "words": words}


def dismiss_transcript_reuse_edit(ctx: RunContext) -> dict[str, Any]:
    """Skip the one-time reuse edit interstitial; keep copied transcript for normal G0."""
    if not transcript_reuse_pending_edit(ctx):
        return {"ok": True, "pending_edit": False, "dismissed": False}
    set_transcript_reuse_pending_edit(ctx, False)
    ctx.log(
        "Transcript reuse edit skipped — using copied transcript; edit later in STT review.",
        level="info",
        stage="transcript_review",
        action_id="gui.transcript_reuse.dismiss_edit",
    )
    return {"ok": True, "pending_edit": False, "dismissed": True}


def get_review_state(ctx: RunContext) -> dict[str, Any]:
    from interview_mux.write_staging import artifact_exists_resolved

    if not ctx.artifact_exists("transcript/review_queue.json"):
        return {"ready": False, "chunks": [], "complete": ctx.is_done("transcript_review")}
    queue = ctx.read_json("transcript/review_queue.json")
    raw_chunks = list(queue.get("chunks") or [])
    chunks: list[dict[str, Any]] = []
    for raw in raw_chunks:
        if not isinstance(raw, dict):
            continue
        chunk = dict(raw)
        chunk_id = chunk.get("chunk_id")
        clip_rel = chunk.get("clip_path") or (
            f"transcript/review_clips/{chunk_id}.wav" if chunk_id else ""
        )
        clip_ready = bool(clip_rel and artifact_exists_resolved(ctx, clip_rel))
        chunk["clip_ready"] = clip_ready
        if not chunk.get("clip_path") and clip_rel:
            chunk["clip_path"] = clip_rel
        chunks.append(chunk)
    pending = sum(1 for c in chunks if not c.get("reviewed"))
    return {
        "ready": True,
        "complete": ctx.is_done("transcript_review"),
        "low_confidence_threshold": queue.get("low_confidence_threshold", LOW_CONFIDENCE_THRESHOLD),
        "chunk_count": len(chunks),
        "pending_count": pending,
        "chunks": chunks,
    }


def _refine_chunk_edges(
    chunk: dict[str, Any],
    words: list[dict[str, Any]],
    wav_path: Path,
    *,
    playback_pad_ms: int = 80,
) -> None:
    start_ms = int(chunk["start_ms"])
    end_ms = int(chunk["end_ms"])
    start_ms = snap_cut_to_word_boundary(start_ms, words, margin_ms=0, max_shift_ms=400)
    end_ms = snap_cut_to_word_boundary(end_ms, words, margin_ms=50, max_shift_ms=400)
    start_ms = find_silence_valley_ms(wav_path, start_ms, search_ms=200)
    end_ms = find_silence_valley_ms(wav_path, end_ms, search_ms=200)
    if end_ms <= start_ms:
        end_ms = start_ms + 50
    chunk["start_ms"] = start_ms
    chunk["end_ms"] = end_ms
    chunk["clip_start_ms"] = start_ms
    chunk["clip_end_ms"] = min(end_ms + playback_pad_ms, end_ms + 500)


def _acoustic_stress_score(wav_path: Path, chunk: dict[str, Any]) -> float:
    """H-G0-02 proxy: low edge RMS + low confidence → higher stress."""
    start_rms = rms_at_ms(wav_path, int(chunk["start_ms"])) or 0.0
    end_rms = rms_at_ms(wav_path, int(chunk["end_ms"])) or 0.0
    edge_rms = min(start_rms, end_rms)
    confidence = float(chunk.get("confidence") or 1.0)
    low_conf = max(0.0, 1.0 - confidence)
    edge_stress = max(0.0, 0.02 - edge_rms) / 0.02 if edge_rms < 0.02 else 0.0
    return round(min(1.0, low_conf * 0.6 + edge_stress * 0.4), 4)


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
    sid = speaker_id or (span_words[0].get("speaker_id") if span_words else None) or "spk_0"
    return {
        "chunk_id": f"tr_{seq:04d}",
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker_id": sid,
        "text": text,
        "word_count": len(span_words),
        "confidence": confidence,
    }


def _words_overlapping_range(
    words: list[dict[str, Any]], start_ms: int, end_ms: int
) -> list[dict[str, Any]]:
    return [
        w
        for w in words
        if w["start_ms"] < end_ms and w["end_ms"] > start_ms
    ]


def _text_for_word_range(words: list[dict[str, Any]], start_ms: int, end_ms: int) -> str:
    span = _words_overlapping_range(words, start_ms, end_ms)
    return " ".join(w["text"] for w in span if w.get("text"))


def _sync_review_queue_from_word_edits(
    ctx: RunContext,
    words: list[dict[str, Any]],
    edited_indices: list[int],
) -> list[str]:
    """Mirror dock word edits into review queue chunk text and corrections.json."""
    if not ctx.artifact_exists("transcript/review_queue.json"):
        return []

    queue = ctx.read_json("transcript/review_queue.json")
    chunks = list(queue.get("chunks") or [])
    corrections_data = (
        ctx.read_json("transcript/corrections.json")
        if ctx.artifact_exists("transcript/corrections.json")
        else {"corrections": {}}
    )
    corrections = corrections_data.setdefault("corrections", {})

    affected_chunk_ids: set[str] = set()
    for idx in edited_indices:
        if idx < 0 or idx >= len(words):
            continue
        word = words[idx]
        w_start = word.get("start_ms", 0)
        w_end = word.get("end_ms", 0)
        for chunk in chunks:
            if w_start < chunk.get("end_ms", 0) and w_end > chunk.get("start_ms", 0):
                affected_chunk_ids.add(chunk["chunk_id"])

    for chunk_id in sorted(affected_chunk_ids):
        chunk = next((c for c in chunks if c.get("chunk_id") == chunk_id), None)
        if not chunk:
            continue
        synced = _text_for_word_range(words, chunk["start_ms"], chunk["end_ms"])
        chunk["corrected_text"] = synced
        # Dock word edits clear the chunk from the G0 pending queue…
        chunk["reviewed"] = True
        entry = corrections.get(chunk_id) or {}
        entry["text"] = synced
        # …but corrections stay unreviewed until explicit chunk sign-off.
        entry["reviewed"] = False
        corrections[chunk_id] = entry

    queue["chunks"] = chunks
    _write_transcript_json(ctx, "transcript/review_queue.json", queue)
    _write_transcript_json(ctx, "transcript/corrections.json", corrections_data)
    return sorted(affected_chunk_ids)


def _apply_correction_to_range(
    words: list[dict[str, Any]],
    start_ms: int,
    end_ms: int,
    text: str,
    speaker_id: str | None,
) -> list[dict[str, Any]]:
    """Apply chunk correction without destroying dock word-level edits when possible."""
    text = text.strip()
    if not text:
        return words

    span = _words_overlapping_range(words, start_ms, end_ms)
    current = " ".join(w["text"] for w in span if w.get("text"))
    if current == text:
        return words

    tokens = text.split()
    dock_corrected = bool(span) and all(w.get("corrected") for w in span)

    if dock_corrected:
        return words

    if span and len(tokens) == len(span):
        for word, token in zip(span, tokens):
            word["text"] = token
            word["corrected"] = True
        return words

    return _replace_words_in_range(words, start_ms, end_ms, text, speaker_id)


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

