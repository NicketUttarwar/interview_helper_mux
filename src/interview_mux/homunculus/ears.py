"""Ears: slice + optional STT. QC only — never overwrite Apple VTT."""

from __future__ import annotations

from typing import Any

from interview_mux.homunculus.issues import emit_issue, ingest_catch
from interview_mux.run_context import RunContext


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
        heard = _hear_slice(ctx, rel, start_ms, end_ms)
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
    windows = (
        ("opening", 0, 20000),
        ("dense", 30000, 60000),
        ("hinge", 90000, 110000),
    )
    packets = []
    fail_open = False
    reason = ""
    for wid, start, end in windows:
        row = stt_window(
            ctx,
            window_id=wid,
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
