"""0.1.0 phase scheduler: conductor first, logged seed-agenda fallback."""

from __future__ import annotations

from typing import Any

from interview_mux.homunculus.ledger import append_ledger
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

AGENDA_REL = "mastering/homunculus/agenda.json"


def remaining_stages(ctx: RunContext, phase: str) -> list[str]:
    order = ANALYSIS_ORDER if phase == "analysis" else DELIVERY_ORDER
    return [s for s in order if not ctx.is_done(s)]


def write_agenda(ctx: RunContext, phase: str, remaining: list[str], *, source: str) -> dict[str, Any]:
    doc = {
        "phase": phase,
        "remaining": list(remaining),
        "source": source,
        "seed_order": list(ANALYSIS_ORDER if phase == "analysis" else DELIVERY_ORDER),
    }
    ctx.write_json(AGENDA_REL, doc)
    append_ledger(
        ctx,
        {
            "kind": "agenda",
            "identity": "agenda",
            "phase": phase,
            "source": source,
            "remaining": remaining[:40],
        },
    )
    return doc


def walk_seed_agenda(ctx: RunContext, stages: list[str], *, reason: str) -> None:
    """Explicit logged fallback — not a silent linear fall-through."""
    append_ledger(
        ctx,
        {
            "kind": "fallback",
            "identity": "walk_seed_agenda",
            "reason": reason,
            "stages": list(stages)[:80],
        },
    )
    ctx.log(
        f"homunculus seed-agenda fallback ({reason}): {len(stages)} stage(s)",
        level="warning",
        stage="homunculus",
    )
    from interview_mux.gates import check_transcript_review_pending
    from interview_mux.pipeline import run_single_stage

    setattr(ctx, "_homunculus_seed_walk", True)
    try:
        for stage in stages:
            if ctx.is_done(stage):
                continue
            run_single_stage(ctx, stage)
            if stage == "transcript_review_build" and check_transcript_review_pending(ctx):
                break
    finally:
        if hasattr(ctx, "_homunculus_seed_walk"):
            delattr(ctx, "_homunculus_seed_walk")


def run_homunculus_phase(
    ctx: RunContext,
    phase: str,
    remaining: list[str],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    """Conductor selects tools; leftover stages walk the seed order and are ledgered."""
    write_agenda(ctx, phase, remaining, source="conductor")
    from interview_mux.homunculus.persona import write_persona
    from interview_mux.homunculus.speakers import build_speaker_dossier

    write_persona(ctx)
    if ctx.artifact_exists("understanding/speakers.json") or ctx.artifact_exists("ingest/transcript.json"):
        try:
            build_speaker_dossier(ctx)
        except Exception:
            pass
    conductor_out: dict[str, Any] = {"ok": False, "skipped": True}
    if remaining:
        try:
            from interview_mux.homunculus.loop import run_conductor

            msg = (
                f"Complete the {phase} phase for this tape. Remaining stages (seed order): "
                f"{', '.join(remaining)}. Select run_stage_* tools. Admit every output. "
                f"Pack volleys by fact IDs. Cite docs via retrieve_canon. "
                f"Do not invent dialogue. Respect G0. Hard limits apply."
            )
            conductor_out = run_conductor(ctx, user_message=msg, client=client)
        except Exception as exc:
            conductor_out = {"ok": False, "error": type(exc).__name__, "message": str(exc)[:400]}
            append_ledger(
                ctx,
                {
                    "kind": "fallback",
                    "identity": "walk_seed_agenda",
                    "reason": "conductor_error",
                    "error": conductor_out["message"],
                },
            )
    still = remaining_stages(ctx, phase)
    if still:
        walk_seed_agenda(
            ctx,
            still,
            reason="logged_fallback_after_conductor" if remaining else "empty_remaining",
        )
    return {"conductor": conductor_out, "remaining_after": remaining_stages(ctx, phase)}
