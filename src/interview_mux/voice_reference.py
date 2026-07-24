"""Collect, rank, and collate interviewer voice reference clips for Chatterbox."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.gap_framing import gap_vo_cfg
from interview_mux.run_context import RunContext
from interview_mux.source_topology import (
    _find_speaker_sample_ms,
    extract_clip,
    pickup_eligible_speaker_id,
)


def voice_reference_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    block = ((cfg or merged_config()).get("analysis") or {}).get("gap_vo") or {}
    return {
        "max_reference_candidates": int(block.get("max_reference_candidates", 5)),
        "target_reference_sec": float(block.get("target_reference_sec", 10.0)),
        "min_reference_sec": float(block.get("min_reference_sec", 3.0)),
        "min_clip_score": float(block.get("min_clip_score", 0.4)),
    }


def _manifest_rel(speaker_id: str) -> str:
    return f"understanding/voice_reference/{speaker_id}.json"


def _candidates_rel(speaker_id: str) -> str:
    return f"understanding/voice_reference/{speaker_id}_candidates.json"


def collect_reference_candidates(ctx: RunContext, speaker_id: str) -> dict[str, Any]:
    if not ctx.artifact_exists("transcript/full.json"):
        return {"speaker_id": speaker_id, "segments": []}
    transcript = ctx.read_json("transcript/full.json")
    words = transcript.get("words") or []
    turns: list[dict[str, Any]] = []
    turn_start: int | None = None
    turn_end: int | None = None
    turn_words: list[str] = []
    prev_speaker: str | None = None

    def flush() -> None:
        nonlocal turn_start, turn_end, turn_words
        if prev_speaker != speaker_id or turn_start is None or turn_end is None:
            turn_start, turn_end, turn_words = None, None, []
            return
        dur_ms = max(0, turn_end - turn_start)
        if dur_ms < 2000:
            turn_start, turn_end, turn_words = None, None, []
            return
        text = " ".join(turn_words).strip()
        score = 0.5
        if "?" in text:
            score += 0.15
        if 5000 <= dur_ms <= 15000:
            score += 0.25
        elif dur_ms > 15000:
            score += 0.1
        turns.append(
            {
                "start_ms": turn_start,
                "end_ms": min(turn_end, turn_start + 15000),
                "quote": text[:200],
                "score": round(score, 3),
                "selected": False,
            }
        )
        turn_start, turn_end, turn_words = None, None, []

    for w in words:
        if not isinstance(w, dict):
            continue
        sid = str(w.get("speaker_id") or w.get("speaker") or "")
        start = int(float(w.get("start_ms") or w.get("start") or 0))
        end = int(float(w.get("end_ms") or w.get("end") or start))
        text = str(w.get("text") or w.get("word") or "").strip()
        if sid != prev_speaker:
            flush()
            prev_speaker = sid
            turn_start = start
            turn_end = end
            turn_words = [text] if text else []
        else:
            turn_end = end
            if text:
                turn_words.append(text)
    flush()

    turns.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
    max_n = voice_reference_cfg().get("max_reference_candidates", 5)
    segments = turns[:max_n]
    for i, seg in enumerate(segments):
        seg["selected"] = i == 0
    return {"speaker_id": speaker_id, "segments": segments}


def write_candidate_clips(ctx: RunContext, speaker_id: str, candidates: dict[str, Any]) -> dict[str, Any]:
    audio = ctx.read_path("ingest", "normalized.wav")
    if not audio.is_file():
        return candidates
    out_dir = ctx.path("understanding", "voice_reference", "clips", speaker_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, seg in enumerate(candidates.get("segments") or []):
        if not isinstance(seg, dict):
            continue
        start_ms = int(seg.get("start_ms") or 0)
        end_ms = int(seg.get("end_ms") or start_ms)
        clip_path = out_dir / f"candidate_{i:02d}.wav"
        extract_clip(audio, clip_path, start_ms, end_ms)
        seg["clip_path"] = f"understanding/voice_reference/clips/{speaker_id}/candidate_{i:02d}.wav"
    ctx.write_json(_candidates_rel(speaker_id), candidates)
    return candidates


def voice_reference_payload(ctx: RunContext) -> dict[str, Any]:
    speaker_id = pickup_eligible_speaker_id(ctx) or ""
    if not speaker_id:
        return {"speaker_id": None, "segments": [], "approved": False}
    if not ctx.artifact_exists(_candidates_rel(speaker_id)):
        candidates = collect_reference_candidates(ctx, speaker_id)
        write_candidate_clips(ctx, speaker_id, candidates)
    else:
        candidates = ctx.read_json(_candidates_rel(speaker_id))
    manifest = ctx.read_json(_manifest_rel(speaker_id)) if ctx.artifact_exists(_manifest_rel(speaker_id)) else {}
    return {
        "speaker_id": speaker_id,
        "segments": candidates.get("segments") or [],
        "approved": bool(isinstance(manifest, dict) and manifest.get("approved")),
        "manifest": manifest if isinstance(manifest, dict) else {},
        "ref_quality": (manifest.get("ref_quality") if isinstance(manifest, dict) else None),
        "sample_wav": f"understanding/speaker_samples/{speaker_id}.wav",
    }


def update_selected_segments(ctx: RunContext, speaker_id: str, selected_indices: list[int]) -> dict[str, Any]:
    rel = _candidates_rel(speaker_id)
    if not ctx.artifact_exists(rel):
        raise FileNotFoundError("Candidates not built")
    doc = ctx.read_json(rel)
    segments = doc.get("segments") or []
    chosen = set(int(i) for i in selected_indices)
    for i, seg in enumerate(segments):
        if isinstance(seg, dict):
            seg["selected"] = i in chosen
    doc["segments"] = segments
    ctx.write_json(rel, doc)
    return doc


def _concat_clips(ctx: RunContext, clip_paths: list[Path], dest: Path) -> None:
    if not clip_paths:
        raise ValueError("No clips to concatenate")
    if len(clip_paths) == 1:
        dest.write_bytes(clip_paths[0].read_bytes())
        return
    list_file = dest.parent / "_concat_list.txt"
    lines = [f"file '{p.resolve()}'" for p in clip_paths]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    list_file.unlink(missing_ok=True)


def _reference_duration_sec(path: Path) -> float:
    import wave

    try:
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate() or 48000
            return wf.getnframes() / rate
    except Exception:
        return 0.0


def approve_voice_reference(ctx: RunContext, speaker_id: str) -> dict[str, Any]:
    rel = _candidates_rel(speaker_id)
    if not ctx.artifact_exists(rel):
        write_candidate_clips(ctx, speaker_id, collect_reference_candidates(ctx, speaker_id))
    candidates = ctx.read_json(rel)
    segments = [s for s in (candidates.get("segments") or []) if isinstance(s, dict) and s.get("selected")]
    clip_paths: list[Path] = []
    ref_text_parts: list[str] = []
    for seg in segments:
        clip_rel = str(seg.get("clip_path") or "")
        if clip_rel:
            clip_paths.append(ctx.read_path(*clip_rel.split("/")))
        quote = str(seg.get("quote") or "").strip()
        if quote:
            ref_text_parts.append(quote)
    dest_rel = f"understanding/speaker_samples/{speaker_id}.wav"
    dest = ctx.path(*dest_rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if clip_paths:
        _concat_clips(ctx, clip_paths, dest)
    else:
        transcript = ctx.read_json("transcript/full.json")
        sample = _find_speaker_sample_ms(transcript, speaker_id)
        if not sample:
            raise ValueError(f"No reference audio for speaker {speaker_id}")
        extract_clip(ctx.read_path("ingest", "normalized.wav"), dest, sample[0], sample[1])
    cfg = voice_reference_cfg()
    duration_sec = _reference_duration_sec(dest)
    if duration_sec < cfg["min_reference_sec"]:
        raise ValueError(
            f"Voice reference too short ({duration_sec:.1f}s); need at least {cfg['min_reference_sec']:.1f}s"
        )
    avg_score = (
        sum(float(s.get("score") or 0) for s in segments) / len(segments) if segments else 0.0
    )
    ref_quality = {
        "duration_sec": round(duration_sec, 2),
        "avg_clip_score": round(avg_score, 3),
        "clip_count": len(segments),
        "warnings": [],
    }
    if avg_score < cfg["min_clip_score"]:
        ref_quality["warnings"].append("low_clip_score")
    manifest = {
        "speaker_id": speaker_id,
        "approved": True,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "wav": dest_rel,
        "ref_text": " ".join(ref_text_parts).strip(),
        "segments": segments,
        "ref_quality": ref_quality,
    }
    sidecar = ctx.path("understanding", "speaker_samples", f"{speaker_id}.json")
    sidecar.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    ctx.write_json(_manifest_rel(speaker_id), manifest)
    from interview_mux.gap_vo_gates import mark_voice_reference_approved

    mark_voice_reference_approved(ctx, speaker_id)
    return manifest
