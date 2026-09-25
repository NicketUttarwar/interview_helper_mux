"""Slim Pass-2: L0 agenda + gap recompose + framing apply.

Retired ``*_refine`` ghosts are **non-dispatchable** (F-06 / DEEP-REFINE-GHOST).
Import shims raise ``StageRetired``; they are absent from ``DELIVERY_ORDER`` and
pipeline runners. Live Pass-2 path:

``refinement_agenda`` → ``gap_framing_recompose`` → ``selection_framing_apply``
"""

from __future__ import annotations

from typing import Any, Iterable

from interview_mux.refinement_champion import seed_champion
from interview_mux.refinement_flow_integrity import (
    DRAFT_REL,
    FINAL_REL,
    dual_write_draft_from_compose,
    ensure_gap_report_authoritative,
    skip_copy_draft_to_final,
)
from interview_mux.refinement_gate import decide_pass
from interview_mux.refinement_identity import cfi_for_pass
from interview_mux.refinement_ledger import record_call
from interview_mux.refinement_outcome import append_listener_outcome
from interview_mux.refinement_shadow import maybe_write_shadow_score
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_refuse_mark

RECOMPOSE_REL = "understanding/gap_framing_recompose.json"
APPLY_REL = "understanding/selection_framing_apply.json"

# F-06 SSOT — not in DELIVERY_ORDER / runners / STAGE_BY_ID; sfx_prompt_refine stays live.
RETIRED_REFINE_GHOSTS: frozenset[str] = frozenset(
    {
        "ranking_refine",
        "narrative_arc_refine",
        "transitions_refine",
        "sdp_intent_refine",
        "edl_narrative_refine",
    }
)


def persist_pass2_skip_stub(ctx: RunContext, stage: str, *, skip_reason: str) -> None:
    """HF-1: freeze/skip write a skip stub so force-mark is not hollow."""
    rel = {
        "gap_framing_recompose": RECOMPOSE_REL,
        "selection_framing_apply": APPLY_REL,
    }.get(str(stage or "").strip())
    if not rel:
        return
    ctx.write_json(
        rel,
        {"skipped": True, "refused": False, "skip_reason": str(skip_reason or "skipped")},
        skip_handoff=True,
        stage_key=str(stage),
    )


def persist_apply_refuse_stub(ctx: RunContext, *, reason: str) -> None:
    """HF-1 / SFA-B2: missing/invalid selection is not apply-complete (no heal)."""
    ctx.write_json(
        APPLY_REL,
        {"skipped": False, "refused": True, "reason": str(reason or "refused")},
        skip_handoff=True,
        stage_key="selection_framing_apply",
    )


def persist_pass2_refuse_stub(
    ctx: RunContext, stage: str, *, reason: str, errors: list[str] | None = None
) -> None:
    """HF-5: Pass-2 left gap W1-unsanitary — not seed-complete."""
    rel = {
        "gap_framing_recompose": RECOMPOSE_REL,
        "selection_framing_apply": APPLY_REL,
    }.get(str(stage or "").strip())
    if not rel:
        return
    ctx.write_json(
        rel,
        {
            "skipped": False,
            "refused": True,
            "reason": str(reason or "gap_unsanitary"),
            "errors": [str(e) for e in (errors or [])[:8]],
        },
        skip_handoff=True,
        stage_key=str(stage),
    )


def _heal_pass2(ctx: RunContext, stage: str) -> None:
    if not ctx.is_done(stage):
        heal_or_refuse_mark(ctx, stage, force=True)


def _finish_pass2(ctx: RunContext, stage: str) -> None:
    """Mark Pass-2 only when gap stays W1-sanitary (HF-5). Seat-freeze skip is exempt."""
    sid = str(stage or "").strip()
    rel = {
        "gap_framing_recompose": RECOMPOSE_REL,
        "selection_framing_apply": APPLY_REL,
    }.get(sid)
    if rel and ctx.artifact_exists(rel):
        try:
            doc = ctx.read_json(rel)
        except Exception:
            doc = None
        if isinstance(doc, dict) and doc.get("skipped") is True:
            _heal_pass2(ctx, sid)
            return
    errs: list[str] = []
    if ctx.artifact_exists("understanding/gap_report.json"):
        try:
            from interview_mux.artifact_sanitize.registry import gap_sanitary_errors

            errs = [
                str(e)
                for e in (gap_sanitary_errors(ctx) or [])
                if e and "missing" not in str(e).lower()
            ]
        except Exception:
            errs = []
    if errs:
        persist_pass2_refuse_stub(ctx, sid, reason="gap_unsanitary", errors=errs)
        raise RuntimeError(
            f"gap_unsanitary — resume {sid}: " + "; ".join(errs[:4])
        )
    _heal_pass2(ctx, sid)


def courtesy_rewrite_lines_if_sanitary(
    ctx: RunContext,
    candidate: dict[str, Any],
    stamped: list[Any],
    *,
    ordered: Any,
    by_id: Any,
    chapters: Any,
    settings: Any,
) -> list[dict[str, Any]]:
    """HF-5 3A: keep courtesy_seed_text only when the candidate stays W1-sanitary."""
    from interview_mux.artifact_sanitize.gap_report import gap_doc_sanitary_errors
    from interview_mux.gap_vo_prior_context import (
        build_prior_native_context,
        courtesy_seed_text,
        is_interruptive_opener,
    )

    rows = [dict(r) for r in stamped if isinstance(r, dict)]
    cleaned: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        line = dict(row)
        if line.get("prior_impact_beat") and is_interruptive_opener(
            str(line.get("text") or "")
        ):
            trial = dict(line)
            prior = build_prior_native_context(
                target_segment_id=str(line.get("targets_segment_id") or ""),
                ordered_ids=ordered,
                segments_by_id=by_id,
                chapters=chapters,
                cfg=settings,
            )
            trial["text"] = courtesy_seed_text(
                prior,
                category=str(line.get("line_category") or "framing_question"),
                target_segment_id=str(line.get("targets_segment_id") or "") or None,
            )
            trial_doc = dict(candidate) if isinstance(candidate, dict) else {}
            trial_doc["interviewer_lines"] = cleaned + [trial] + rows[i + 1 :]
            if not gap_doc_sanitary_errors(ctx, trial_doc):
                line = trial
        cleaned.append(line)
    return cleaned


def _record_refinement(ctx: RunContext, pass_id: str, outcome: str, **extra: Any) -> None:
    cfi = cfi_for_pass(pass_id)
    if not cfi:
        return
    try:
        record_call(
            ctx,
            cfi_id=cfi.cfi_id,
            human_key=cfi.human_key,
            stage_id=pass_id,
            pass_id=pass_id,
            pass_index=2,
            kind="refinement",
            outcome=outcome,
            refines_cfi=cfi.refines_cfi,
            **extra,
        )
    except RuntimeError:
        ctx.log(f"Ledger cap blocked {pass_id}", level="warning", stage=pass_id)


def run_gap_framing_recompose(ctx: RunContext) -> None:
    """Post-ranking gap VO recompose — or skip-copy for flow integrity.

    When the Nugget Layup System owns gap_report, this stage is a thin adapter:
    re-publish layups, ensure orientation, and mark done without dropping recovery lines.
    """
    try:
        from interview_mux.seat_authority import gate_seat_mutation

        if not gate_seat_mutation(
            ctx,
            reason="gap_framing_recompose",
            symptoms=["refinement"],
        ):
            ctx.log(
                "gap_framing_recompose: seat freeze blocked (no-op)",
                level="info",
                stage="gap_framing_recompose",
            )
            persist_pass2_skip_stub(
                ctx, "gap_framing_recompose", skip_reason="seat_freeze"
            )
            _heal_pass2(ctx, "gap_framing_recompose")
            return
    except Exception:
        ctx.log(
            "gap_framing_recompose: seat gate error — fail-closed no-op",
            level="warning",
            stage="gap_framing_recompose",
        )
        persist_pass2_skip_stub(
            ctx, "gap_framing_recompose", skip_reason="seat_gate_error"
        )
        _heal_pass2(ctx, "gap_framing_recompose")
        return
    from interview_mux.nugget_layup import (
        PLAN_REL,
        adopt_layup_plan_to_selection,
        assert_gap_report_layup_authority,
        assert_layup_fresh_vs_selection,
        nugget_layup_cfg,
        nugget_layup_enabled,
        publish_layup_plan_to_gap_report,
    )

    if nugget_layup_enabled() and nugget_layup_cfg().get("authoritative_gap_report"):
        if ctx.artifact_exists(PLAN_REL):
            adopt_layup_plan_to_selection(ctx, persist=True, stage="gap_framing_recompose")
            assert_layup_fresh_vs_selection(ctx, stage="gap_framing_recompose")
            report = publish_layup_plan_to_gap_report(ctx)
            assert_gap_report_layup_authority(
                ctx, report, stage="gap_framing_recompose"
            )
            ctx.write_json(
                "understanding/gap_framing_recompose.json",
                {
                    "decisions": [],
                    "accept": {
                        "accepted": True,
                        "reason_code": "nugget_layup_authority",
                    },
                    "input_hash": None,
                },
            )
            maybe_write_shadow_score(ctx, "gap_framing_recompose")
            append_listener_outcome(ctx, "gap_recompose_nugget_layup", {"status": "authority"})
            after_gap_recompose_or_skip(ctx)
            _finish_pass2(ctx, "gap_framing_recompose")
            return

    # GFR-B3: legacy non-layup activate / deterministic-filter path retired.
    # Full-auto default is layup authority above; otherwise skip-copy only.
    dual_write_draft_from_compose(ctx)
    if ctx.artifact_exists(FINAL_REL) and not ctx.artifact_exists(DRAFT_REL):
        dual_write_draft_from_compose(ctx)

    decision = decide_pass(ctx, "gap_framing_recompose")
    skip_reason = str(decision.get("reason_code") or "skipped")
    if decision.get("status") == "activate":
        skip_reason = "legacy_activate_retired"
        decision = {
            **decision,
            "status": "skip",
            "reason_code": skip_reason,
            "legacy_activate_retired": True,
        }
    skip_copy_draft_to_final(ctx, reason=skip_reason)
    maybe_write_shadow_score(ctx, "gap_framing_recompose")
    append_listener_outcome(ctx, "gap_recompose_skipped", decision)
    after_gap_recompose_or_skip(ctx)
    _finish_pass2(ctx, "gap_framing_recompose")


def run_selection_framing_apply(ctx: RunContext) -> None:
    """Lattice #6: framing VO-cover excludes + stamp-only gap seat sync.

    SFA-S1–S5: no orientation/layup/clone body heal; no hosted-floor persist;
    no post-apply sanitize thrash; honor decide_pass skip; selection writes
    only via commit_selection_mutation under producer ALLOW.
    """
    try:
        from interview_mux.seat_authority import gate_seat_mutation

        if not gate_seat_mutation(
            ctx,
            reason="selection_framing_apply",
            symptoms=["refinement"],
        ):
            ctx.log(
                "selection_framing_apply: seat freeze blocked (no-op)",
                level="info",
                stage="selection_framing_apply",
            )
            persist_pass2_skip_stub(
                ctx, "selection_framing_apply", skip_reason="seat_freeze"
            )
            _heal_pass2(ctx, "selection_framing_apply")
            return
    except Exception:
        ctx.log(
            "selection_framing_apply: seat gate error — fail-closed no-op",
            level="warning",
            stage="selection_framing_apply",
        )
        persist_pass2_skip_stub(
            ctx, "selection_framing_apply", skip_reason="seat_gate_error"
        )
        _heal_pass2(ctx, "selection_framing_apply")
        return
    from interview_mux.framing_coverage_guard import validate_framing_ranking
    from interview_mux.gap_framing import (
        ranking_exclude_segment_ids,
        stamp_gap_seats_to_selection,
    )

    ensure_gap_report_authoritative(ctx)
    if not ctx.artifact_exists("master/selection.json"):
        persist_apply_refuse_stub(ctx, reason="missing_selection")
        return

    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        persist_apply_refuse_stub(ctx, reason="invalid_selection")
        return

    decision = decide_pass(ctx, "selection_framing_apply")
    # S3: skip means no selection/gap mutate — sidecar only.
    if str(decision.get("status") or "").strip() != "activate":
        skip_reason = str(
            decision.get("reason_code") or decision.get("gate") or "decide_pass_skip"
        )
        persist_pass2_skip_stub(
            ctx, "selection_framing_apply", skip_reason=skip_reason
        )
        _heal_pass2(ctx, "selection_framing_apply")
        return

    covered = ranking_exclude_segment_ids(ctx)
    excluded = list(sel.get("excluded_segment_ids") or [])
    excluded_ids: set[str] = set()
    for ex in excluded:
        if isinstance(ex, dict):
            excluded_ids.add(str(ex.get("segment_id") or ex.get("id") or ""))
        else:
            excluded_ids.add(str(ex))

    ordered = [str(x) for x in (sel.get("ordered_segment_ids") or [])]
    new_excludes: list[dict[str, str]] = []
    for sid in covered:
        if sid and sid not in excluded_ids and sid in ordered:
            new_excludes.append({"segment_id": sid, "reason": "covered_by_framing_vo"})
            ordered = [x for x in ordered if x != sid]

    if new_excludes:
        sel["ordered_segment_ids"] = ordered
        sel["excluded_segment_ids"] = list(excluded) + new_excludes
        issues = validate_framing_ranking(ctx, sel)
        hard = [
            i
            for i in (issues or [])
            if "never_exclude_primary" in str(i) or "surviving" in str(i)
        ]
        if not hard:
            # S2: single commit path (sanitize-inside); producer ALLOW on selection.
            from interview_mux.air_order_boundary import commit_selection_mutation

            commit_selection_mutation(
                ctx,
                sel,
                producer="selection_framing_apply",
                stage_key="selection_framing_apply",
                checkpoint_mode="detect",
            )
            sel = (
                ctx.read_json("master/selection.json")
                if ctx.artifact_exists("master/selection.json")
                else sel
            )

    # S1: stamp-only gap seat sync (retarget / omit) — no body heal chain.
    if ctx.artifact_exists("understanding/gap_report.json"):
        final_ordered = [str(x) for x in (sel.get("ordered_segment_ids") or [])]
        gr = ctx.read_json("understanding/gap_report.json")
        if isinstance(gr, dict) and final_ordered:
            stamped, notes = stamp_gap_seats_to_selection(gr, final_ordered)
            if notes:
                ctx.write_json(
                    "understanding/gap_report.json",
                    stamped,
                    stage_key="selection_framing_apply",
                )
                ctx.log(
                    f"selection_framing_apply stamped {len(notes)} gap VO seat(s)",
                    level="info",
                    stage="selection_framing_apply",
                )

    _record_refinement(ctx, "selection_framing_apply", "ok")
    # S4: hosted VO floor identify lives on layup / framing / VO — not apply.
    ctx.write_json(
        APPLY_REL,
        {
            "skipped": False,
            "refused": False,
            "reason": "applied",
        },
        skip_handoff=True,
        stage_key="selection_framing_apply",
    )
    _finish_pass2(ctx, "selection_framing_apply")


def refuse_retired_refine(pass_id: str) -> None:
    """Raise StageRetired for a ghost refine id (never mark done / fake progress)."""
    raise RuntimeError(
        f"StageRetired: {pass_id} is a no-op refine ghost outside DELIVERY_ORDER; "
        "use ensemble remutate / listen_delight remutate instead"
    )


def remap_retired_refine_pin(ctx: RunContext, pin: str) -> str:
    """Old runs pinned on a ghost → first pending live delivery (or gap recompose)."""
    key = str(pin or "").strip()
    if key not in RETIRED_REFINE_GHOSTS:
        return key
    try:
        from interview_mux.delivery_recovery import first_pending_delivery

        pending = first_pending_delivery(ctx)
        if pending and str(pending) not in RETIRED_REFINE_GHOSTS:
            return str(pending)
    except Exception:
        pass
    return "gap_framing_recompose"


def filter_retired_refine_stages(stages: Iterable[Any]) -> list[str]:
    """Drop ghost refine ids from remutate / remediation allowlists."""
    return [
        str(s)
        for s in (stages or ())
        if str(s).strip() and str(s).strip() not in RETIRED_REFINE_GHOSTS
    ]


def run_narrative_arc_refine(ctx: RunContext) -> None:
    refuse_retired_refine("narrative_arc_refine")


def run_ranking_refine(ctx: RunContext) -> None:
    refuse_retired_refine("ranking_refine")


def run_transitions_refine(ctx: RunContext) -> None:
    refuse_retired_refine("transitions_refine")


def run_sdp_intent_refine(ctx: RunContext) -> None:
    refuse_retired_refine("sdp_intent_refine")


def run_edl_narrative_refine(ctx: RunContext) -> None:
    refuse_retired_refine("edl_narrative_refine")


def after_gap_compose_hook(ctx: RunContext) -> None:
    dual_write_draft_from_compose(ctx)
    seed_champion(
        ctx,
        "gap_vo",
        [FINAL_REL, DRAFT_REL],
        source="draft",
    )


def after_gap_recompose_or_skip(ctx: RunContext) -> None:
    """Post gap-final hooks — cold-open audition plan when preface/open lines exist."""
    if ctx.artifact_exists(FINAL_REL) and ctx.artifact_exists("master/selection.json"):
        from interview_mux.opening_orientation import ensure_episode_orientation

        report = ctx.read_json(FINAL_REL)
        selection = ctx.read_json("master/selection.json")
        ordered = [
            str(x) for x in ((selection or {}).get("ordered_segment_ids") or []) if x
        ]
        if isinstance(report, dict) and ordered:
            report, actions = ensure_episode_orientation(ctx, report, ordered)
            if actions:
                ctx.write_json(FINAL_REL, report)
                ctx.log(
                    f"opening orientation guard applied {len(actions)} action(s)",
                    level="info",
                    stage="gap_framing_recompose",
                    detail=actions,
                )
    try:
        from interview_mux.hosted_vo_authority import identify_hosted_vo_floor

        identify_hosted_vo_floor(ctx, persist=True)
    except Exception:
        pass
    from interview_mux.refinement_cold_open import build_cold_open_audition

    build_cold_open_audition(ctx)
