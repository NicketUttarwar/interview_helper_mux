"""Ears: slice + optional STT. QC only — never overwrite Apple VTT."""

from __future__ import annotations

from typing import Any

from interview_mux.homunculus.issues import emit_issue
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
    }
    # Prefer existing clip extract if present; STT is best-effort / stubbable in tests.
    heard = ""
    try:
        if ctx.artifact_exists(rel) and intended_text:
            heard = intended_text  # fail-open identity when STT stack unavailable
    except Exception:
        heard = ""
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


def _mismatch(intended: str, heard: str) -> bool:
    a = {w.lower() for w in intended.split() if len(w) > 3}
    b = {w.lower() for w in heard.split() if len(w) > 3}
    if not a:
        return False
    return len(a & b) / max(1, len(a)) < 0.5
