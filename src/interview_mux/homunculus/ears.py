"""Ears: slice + optional STT. QC only — never overwrite Apple VTT."""

from __future__ import annotations

from typing import Any

from interview_mux.homunculus.issues import emit_issue, ingest_catch
from interview_mux.homunculus.source_card import wav_duration_s
from interview_mux.run_context import RunContext


def resolve_ears_wav_rel(ctx: RunContext, rel: str | None = None) -> str:
    """Prefer master.wav; fall back to assembly.wav when the master is not written yet."""
    requested = str(rel or "").strip()
    if requested and ctx.artifact_exists(requested):
        return requested
    if ctx.artifact_exists("master/master.wav"):
        return "master/master.wav"
    if ctx.artifact_exists("master/assembly.wav"):
        return "master/assembly.wav"
    return requested or "master/master.wav"


def _duration_ms(ctx: RunContext, rel: str) -> int:
    path = ctx.path(rel)
    if path.is_file():
        sec = wav_duration_s(path)
        if sec and sec > 0:
            return int(sec * 1000)
    try:
        from interview_mux.interview_duration_policy import transcript_duration_ms

        ms = int(transcript_duration_ms(ctx) or 0)
        if ms > 0:
            return ms
    except Exception:
        pass
    return 0


def _speaker_hinge_ms(ctx: RunContext, duration_ms: int) -> tuple[int, int] | None:
    for rel in ("transcript/full.json", "ingest/transcript.json"):
        if not ctx.artifact_exists(rel):
            continue
        blob = ctx.read_json(rel)
        words = (blob.get("words") if isinstance(blob, dict) else None) or []
        prev = None
        for w in words:
            if not isinstance(w, dict):
                continue
            sp = str(w.get("speaker") or w.get("speaker_id") or "")
            start = int(w.get("start_ms") or w.get("start") or 0)
            if prev and sp and sp != prev and 0 < start < duration_ms:
                end = min(duration_ms, start + max(8000, int(duration_ms * 0.08)))
                return (max(0, start - 2000), end)
            if sp:
                prev = sp
        break
    return None


def plan_ear_windows(ctx: RunContext, duration_ms: int) -> tuple[tuple[str, int, int], ...]:
    """Source-relative QC windows. Short tapes: one window. Never invent past EOF."""
    if duration_ms <= 0:
        return (("opening", 0, 8000),)
    if duration_ms < 20_000:
        return (("full", 0, duration_ms),)
    open_end = max(4000, int(duration_ms * 0.08))
    close_start = max(open_end, int(duration_ms * 0.92))
    panel = False
    try:
        from interview_mux.homunculus.source_card import read_source_card

        card = read_source_card(ctx) or {}
        circ = [str(x).lower() for x in (card.get("circumstances") or [])]
        panel = "panel" in circ or "panel" in str(card.get("topology") or "").lower()
    except Exception:
        panel = False
    mid: tuple[str, int, int]
    if panel:
        hinge = _speaker_hinge_ms(ctx, duration_ms)
        if hinge:
            mid = ("hinge", hinge[0], hinge[1])
        else:
            mid = ("dense", int(duration_ms * 0.40), min(duration_ms, int(duration_ms * 0.50)))
    else:
        mid = ("dense", int(duration_ms * 0.40), min(duration_ms, int(duration_ms * 0.50)))
    return (
        ("opening", 0, min(duration_ms, open_end)),
        mid,
        ("closing", close_start, duration_ms),
    )


def stt_window(
    ctx: RunContext,
    *,
    window_id: str,
    rel: str = "master/master.wav",
    start_ms: int = 0,
    end_ms: int = 8000,
    intended_text: str = "",
) -> dict[str, Any]:
    comparison = {
        "window_id": window_id,
        "rel": rel,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "intended_text": intended_text,
        "heard_text": "",
        "qc_only": True,
        "overwrites_apple_vtt": False,
        "fail_open": False,
    }
    heard = ""
    try:
        resolved = resolve_ears_wav_rel(ctx, rel)
        comparison["rel"] = resolved
        heard = _hear_slice(ctx, resolved, start_ms, end_ms)
    except Exception as exc:
        comparison["fail_open"] = True
        comparison["fail_open_reason"] = f"{type(exc).__name__}: {exc}"[:240]
        ingest_catch(
            ctx,
            kind="ears_stt_unavailable",
            source="ears",
            evidence={"window_id": window_id, "error": comparison["fail_open_reason"]},
        )
        if intended_text:
            heard = intended_text
    comparison["heard_text"] = heard
    ctx.write_json(f"mastering/homunculus/ears/{window_id}/comparison.json", comparison)
    if intended_text and heard and _mismatch(intended_text, heard):
        emit_issue(
            ctx,
            kind="ears_word_mismatch",
            source="ears",
            evidence={"window_id": window_id, "intended": intended_text[:200], "heard": heard[:200]},
        )
    return comparison


def hear_master_windows(ctx: RunContext) -> dict[str, Any]:
    intended = ""
    for rel in ("master/transcript.json", "ingest/transcript.json"):
        if not ctx.artifact_exists(rel):
            continue
        blob = ctx.read_json(rel)
        if isinstance(blob, dict):
            intended = str(blob.get("text") or "")[:4000]
            break
    wav_rel = resolve_ears_wav_rel(ctx)
    windows = plan_ear_windows(ctx, _duration_ms(ctx, wav_rel))
    packets = []
    fail_open = False
    reason = ""
    for wid, start, end in windows:
        row = stt_window(
            ctx,
            window_id=wid,
            rel=wav_rel,
            start_ms=start,
            end_ms=end,
            intended_text=intended[:800],
        )
        packets.append(row)
        if row.get("fail_open"):
            fail_open = True
            reason = str(row.get("fail_open_reason") or "ears_stt_unavailable")
    return {
        "windows": packets,
        "qc_only": True,
        "overwrites_apple_vtt": False,
        "fail_open": fail_open,
        "fail_open_reason": reason or None,
    }


def _hear_slice(ctx: RunContext, rel: str, start_ms: int, end_ms: int) -> str:
    src = ctx.path(rel)
    if not src.is_file():
        raise FileNotFoundError(rel)
    from interview_mux.stt_runner import speech_available, transcribe_audio

    if not speech_available():
        raise RuntimeError("speech venv unavailable")
    from interview_mux.audio_clips import extract_clip

    dest = ctx.path(f"mastering/homunculus/ears/_slice_{start_ms}_{end_ms}.wav")
    dest.parent.mkdir(parents=True, exist_ok=True)
    extract_clip(src, dest, start_ms, end_ms)
    raw = transcribe_audio(ctx, dest)
    if isinstance(raw, dict):
        return str(raw.get("text") or "")
    return ""


def _mismatch(intended: str, heard: str) -> bool:
    a = {w.lower() for w in intended.split() if len(w) > 3}
    b = {w.lower() for w in heard.split() if len(w) > 3}
    if not a:
        return False
    return len(a & b) / max(1, len(a)) < 0.5
