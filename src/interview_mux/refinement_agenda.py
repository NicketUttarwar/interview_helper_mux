"""L0 refinement agenda — eligible classes for this tape.

Production seed walk always uses ``phase="confirm"`` (see ``pipeline.py``).
``phase="draft"`` remains for tests that compare draft vs confirm injects only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.refinement_catalog import ELIGIBLE_CLASS_VOCAB
from interview_mux.refinement_identity import cfi_for_pass
from interview_mux.refinement_ledger import record_call
from interview_mux.refinement_policy import detect_tape_character, resolve_policy_pack
from interview_mux.refinement_priors import bias_eligible_classes, priors_enabled
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_refuse_mark

AGENDA_REL = "understanding/refinement_agenda.json"


def load_agenda(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(AGENDA_REL):
        return None
    doc = ctx.read_json(AGENDA_REL)
    return doc if isinstance(doc, dict) else None


def _gap_unsanitary_block(ctx: RunContext) -> None:
    """RA-B2: do not seed agenda while present gap_report is W1-unsanitary.

    Missing gap stays soft (RA-B1); only a dirty present report blocks.
    """
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return
    try:
        from interview_mux.artifact_sanitize.registry import gap_sanitary_errors

        errs = [str(e) for e in (gap_sanitary_errors(ctx) or []) if str(e).strip()]
    except Exception:
        return
    if not errs:
        return
    raise RuntimeError(
        "gap_unsanitary — resume gap_report_sanitize: " + "; ".join(errs[:4])
    )


def run_refinement_agenda(
    ctx: RunContext, *, phase: Literal["draft", "confirm"] = "confirm"
) -> dict[str, Any]:
    """Compile Pass-2 eligible classes. Default ``confirm`` matches production.

    ``draft`` is test-only (no seed-walk caller); keep it for RA-B3 draft/confirm
    contrast — do not use in pipeline dispatch.
    """
    _gap_unsanitary_block(ctx)
    characters = detect_tape_character(ctx)
    pack = resolve_policy_pack(ctx, characters)
    eligible = list(pack.get("eligible_class_defaults") or [])
    prior_bias = False
    if priors_enabled():
        eligible, prior_bias = bias_eligible_classes(characters, eligible)

    if pack.get("simple_tape_override"):
        eligible = []

    # Confirm phase: open ranking if coverage holes exist
    if phase == "confirm" and ctx.artifact_exists("master/coverage_audit.json"):
        cov = ctx.read_json("master/coverage_audit.json")
        holes = []
        if isinstance(cov, dict):
            holes = cov.get("uncovered_topics") or cov.get("gaps") or []
        if holes and "ranking" not in eligible and "ranking" in ELIGIBLE_CLASS_VOCAB:
            eligible.append("ranking")

    mastering_bind: dict[str, Any] | None = None
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        mp = ctx.read_json("mastering/mastering_plan.json")
        if isinstance(mp, dict):
            mastering_bind = {
                "cold_open": mp.get("cold_open"),
                "vo_include": mp.get("vo") or mp.get("include_vo"),
                "mode": "realization_plan_bound",
            }
            if mastering_bind.get("cold_open") and "cold_open" not in eligible:
                eligible.append("cold_open")

    eligible = [c for c in eligible if c in ELIGIBLE_CLASS_VOCAB]
    ineligible = [
        {"class_id": c, "reason": "not_selected_for_tape"}
        for c in sorted(ELIGIBLE_CLASS_VOCAB - set(eligible))
    ]

    succession_hints: list[str] = []
    if "gap_vo" in eligible:
        succession_hints.append("gap_vo_then_transitions")
    if "ranking" in eligible:
        succession_hints.append("post_gap_topic_holes_ranking")

    doc: dict[str, Any] = {
        "run_id": ctx.run_id,
        "schema_version": 1,
        "phase": phase,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "tape_character": characters,
        "eligible_classes": eligible,
        "ineligible_classes": ineligible,
        "succession_hints": succession_hints,
        "policy_pack_id": pack.get("pack_id"),
        "prior_bias_applied": prior_bias,
        "mastering_plan_bind": mastering_bind,
        "north_star_notes": (
            "Best listener outcome for this tape — open only classes that earn airtime."
            if not mastering_bind
            else "Realization plan-bound mode — Pass 2 respects mastering_plan cold_open/VO include."
        ),
    }
    ctx.write_json(AGENDA_REL, doc)
    cfi = cfi_for_pass("refinement_agenda")
    if cfi:
        try:
            record_call(
                ctx,
                cfi_id=cfi.cfi_id,
                human_key=cfi.human_key,
                stage_id="refinement_agenda",
                pass_id="refinement_agenda",
                pass_index=1 if phase == "draft" else 1,
                kind="first_pass",
                outcome="ok",
                gate=phase,
                detail={"eligible_classes": eligible},
            )
        except RuntimeError:
            pass
    ctx.log(
        f"Refinement agenda ({phase}): eligible={eligible} pack={pack.get('pack_id')}",
        level="info",
        stage="refinement_agenda",
        action_id="refinement_agenda",
        detail={"tape_character": characters, "eligible_classes": eligible},
    )
    if not ctx.is_done("refinement_agenda"):
        heal_or_refuse_mark(ctx, "refinement_agenda", force=True)
    return doc
