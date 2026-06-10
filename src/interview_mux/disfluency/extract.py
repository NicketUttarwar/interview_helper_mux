from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.audio_clips import extract_clip
from interview_mux.disfluency.classify import classify_transcript_words, is_filler_text
from interview_mux.disfluency.config import extract_settings
from interview_mux.disfluency.gaps import build_gap_candidates
from interview_mux.disfluency.vad import gap_has_voice_activity
from interview_mux.disfluency.whisper_pass import transcribe_clip, whisper_available
from interview_mux.run_context import RunContext


def _resolve_audio(ctx: RunContext) -> Path:
    for rel in ("preclean/isolated.wav", "ingest/normalized.wav"):
        p = ctx.path(*rel.split("/"))
        if p.is_file():
            return p
    raise FileNotFoundError("No normalized audio for disfluency extract")


def _dedupe_events(events: list[dict[str, Any]], *, min_gap_ms: int = 30) -> list[dict[str, Any]]:
    if not events:
        return []
    ordered = sorted(events, key=lambda e: (int(e["start_ms"]), int(e["end_ms"])))
    out: list[dict[str, Any]] = []
    for ev in ordered:
        if out:
            prev = out[-1]
            if (
                int(ev["start_ms"]) <= int(prev["end_ms"]) + min_gap_ms
                and str(ev.get("text", "")).lower() == str(prev.get("text", "")).lower()
            ):
                prev["end_ms"] = max(int(prev["end_ms"]), int(ev["end_ms"]))
                prev["confidence"] = max(float(prev.get("confidence") or 0), float(ev.get("confidence") or 0))
                continue
        out.append(ev)
    return out


def run_extraction(ctx: RunContext, *, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = extract_settings(cfg)
    full_path = ctx.path("transcript/full.json")
    if not full_path.is_file():
        raise FileNotFoundError(full_path)

    full = ctx.read_json("transcript/full.json")
    words = [w for w in (full.get("words") or []) if isinstance(w, dict)]
    audio = _resolve_audio(ctx)
    lexicon = settings["filler_lexicon"]

    events: list[dict[str, Any]] = list(classify_transcript_words(words, lexicon))
    use_whisper = whisper_available()
    whisper_model = settings["whisper_model"]

    gaps = build_gap_candidates(
        words,
        gap_min_ms=settings["gap_min_ms"],
        gap_max_ms=settings["gap_max_ms"],
        pad_ms=settings["pad_ms"],
    )

    clips_dir = ctx.path("transcript", "disfluency_clips")
    clips_dir.mkdir(parents=True, exist_ok=True)
    for old in clips_dir.glob("*.wav"):
        old.unlink()

    for gap in gaps:
        if len(events) >= settings["max_events"]:
            break
        has_voice, _db = gap_has_voice_activity(
            str(audio),
            int(gap["start_ms"]),
            int(gap["end_ms"]),
            energy_dbfs=settings["vad_energy_dbfs"],
        )
        if not has_voice:
            continue
        if int(gap["end_ms"]) - int(gap["start_ms"]) < settings["min_event_ms"]:
            continue

        text = ""
        confidence = 0.55
        if use_whisper:
            tmp = clips_dir / f"_gap_{gap['gap_index']}.wav"
            extract_clip(audio, tmp, int(gap["start_ms"]), int(gap["end_ms"]))
            try:
                text, confidence = transcribe_clip(
                    tmp,
                    model_name=whisper_model,
                    compute_type=settings["compute_type"],
                    download_root=settings["weights_dir"],
                )
            except Exception as exc:
                ctx.log(
                    f"disfluency_extract: whisper failed on gap {gap['gap_index']}: {exc}",
                    level="warn",
                    stage="disfluency_extract",
                )
            finally:
                if tmp.is_file():
                    tmp.unlink()
        if not is_filler_text(text, lexicon):
            continue
        events.append(
            {
                "start_ms": int(gap["start_ms"]),
                "end_ms": int(gap["end_ms"]),
                "speaker_id": str(gap.get("speaker_id") or ""),
                "text": text,
                "confidence": confidence,
                "source": "vad_gap",
                "label": "filled_pause",
            }
        )

    events = _dedupe_events(events)[: settings["max_events"]]

    for i, ev in enumerate(events, start=1):
        eid = f"fill_{i:04d}"
        ev["event_id"] = eid
        ev["review_status"] = "pending"
        ev["include_in_restore"] = True
        clip_rel = f"transcript/disfluency_clips/{eid}.wav"
        extract_clip(audio, ctx.path(*clip_rel.split("/")), int(ev["start_ms"]), int(ev["end_ms"]))
        ev["clip_path"] = clip_rel

    stats = {
        "total": len(events),
        "pending": len(events),
        "confirmed": 0,
        "rejected": 0,
    }
    return {
        "schema_version": 1,
        "status": "ready",
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "model": {"vad": "energy_rms", "whisper": whisper_model if use_whisper else None},
        "events": events,
        "stats": stats,
    }


def write_skipped_artifact(ctx: RunContext, *, reason: str) -> dict[str, Any]:
    doc = {
        "schema_version": 1,
        "status": "skipped",
        "skip_reason": reason,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "model": {"vad": None, "whisper": None},
        "events": [],
        "stats": {"total": 0, "pending": 0, "confirmed": 0, "rejected": 0},
    }
    ctx.write_json("transcript/disfluencies.json", doc)
    return doc


def load_disfluencies(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("transcript/disfluencies.json"):
        return {"events": [], "stats": {}}
    data = ctx.read_json("transcript/disfluencies.json")
    return data if isinstance(data, dict) else {"events": [], "stats": {}}


def confirmed_events(doc: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in doc.get("events") or []:
        if not isinstance(ev, dict):
            continue
        if str(ev.get("review_status")) != "confirmed":
            continue
        if ev.get("include_in_restore") is False:
            continue
        out.append(ev)
    return out


def recompute_stats(doc: dict[str, Any]) -> dict[str, Any]:
    events = [e for e in (doc.get("events") or []) if isinstance(e, dict)]
    doc["stats"] = {
        "total": len(events),
        "pending": sum(1 for e in events if e.get("review_status") == "pending"),
        "confirmed": sum(1 for e in events if e.get("review_status") == "confirmed"),
        "rejected": sum(1 for e in events if e.get("review_status") == "rejected"),
    }
    return doc
