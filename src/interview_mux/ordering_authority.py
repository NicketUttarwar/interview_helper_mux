"""Single authority for delivery ordering exceptions.

Four checks independently decide whether a delivery stage may run before
another is complete: seed order (``homunculus.runtime._seed_prereq_block``),
LLM flow hardening (``llm_flow_hardening.maybe_require_upstream_llm_progress``),
the music epoch lock (``delivery_guardrails.mix_epoch_block``) and the
conductor. Each carried its own copy of the exceptions, the copies drifted,
and the one-hour run deadlocked with mix, junction_snip_qa and the music band
each refusing on a different check (ISSUES entries 61 and 62).

Every ordering check asks :func:`ordering_exempt` instead of encoding an
exception locally. Add a new exception here, once.
"""

from __future__ import annotations

from typing import Any

MUSIC_BEFORE_MIX: tuple[str, ...] = (
    "music_palette_compose",
    "sfx_prompt_craft",
    "mmaudio_sfx",
)


def _junction_recut_precedes_mix(ctx: Any) -> bool:
    try:
        from interview_mux.junction_snip_qa import junction_recut_precedes_mix

        return bool(junction_recut_precedes_mix(ctx))
    except Exception:
        return False


def _beds_deferred_for_mix(ctx: Any) -> bool:
    try:
        from interview_mux.mix_junction_seat import beds_deferred_for_mix

        return bool(beds_deferred_for_mix(ctx))
    except Exception:
        return False


def _speech_first_mix_allowed(ctx: Any) -> bool:
    try:
        from interview_mux.mix_junction_seat import allow_speech_first_mix

        return bool(allow_speech_first_mix(ctx))
    except Exception:
        return False


def ordering_exempt(ctx: Any, stage: str, prerequisite: str | None) -> str | None:
    """Reason ``stage`` may run while ``prerequisite`` is incomplete, else None.

    ``prerequisite=None`` asks about the music epoch lock (no named upstream).
    """
    sid = str(stage or "").strip()
    pre = str(prerequisite or "").strip()
    if sid == "junction_snip_qa" and (not pre or pre == "mix" or pre in MUSIC_BEFORE_MIX):
        # Live incomplete-cut residuals must be recut before the first mix;
        # mix refuses until then, so junction may run ahead of mix and music.
        if _junction_recut_precedes_mix(ctx):
            return "junction_recut_precedes_mix"
    if sid == "mix" and pre in MUSIC_BEFORE_MIX:
        # HAU speech-first: beds are optional for the first seat.
        if _beds_deferred_for_mix(ctx):
            return "speech_first_beds_deferred"
        # Music refuses until an assembly is seated (preview / unseated only),
        # so mix must seat one first even after an earlier music epoch: a
        # re-cut EDL unseats the old assembly (exec_052 remaster, entry 62).
        if _speech_first_mix_allowed(ctx):
            return "assembly_seat_before_music"
    return None
