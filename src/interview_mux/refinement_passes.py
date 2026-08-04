"""Refinement stage runners — recompose, apply, and stub refine passes."""

from __future__ import annotations

import copy
from typing import Any

from interview_mux.refinement_accept import accept_gap_recompose
from interview_mux.refinement_champion import seed_champion
from interview_mux.refinement_evidence import build_evidence_packet
from interview_mux.refinement_flow_integrity import (
    DRAFT_REL,
    FINAL_REL,
    dual_write_draft_from_compose,
    ensure_gap_report_authoritative,
    skip_copy_draft_to_final,
)
from interview_mux.refinement_gate import decide_pass, freeze_inputs
from interview_mux.refinement_identity import cfi_for_pass
from interview_mux.refinement_ledger import record_call
from interview_mux.refinement_outcome import append_listener_outcome
from interview_mux.refinement_shadow import maybe_write_shadow_score
from interview_mux.run_context import RunContext


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
    """Post-ranking gap VO recompose — or skip-copy for flow integrity."""
    dual_write_draft_from_compose(ctx)
    if ctx.artifact_exists(FINAL_REL) and not ctx.artifact_exists(DRAFT_REL):
        dual_write_draft_from_compose(ctx)

    decision = decide_pass(ctx, "gap_framing_recompose")
    if decision.get("status") != "activate":
        skip_copy_draft_to_final(ctx, reason=str(decision.get("reason_code") or "skipped"))
        maybe_write_shadow_score(ctx, "gap_framing_recompose")
        append_listener_outcome(ctx, "gap_recompose_skipped", decision)
        after_gap_recompose_or_skip(ctx)
        if not ctx.is_done("gap_framing_recompose"):
            ctx.mark_done("gap_framing_recompose", force=True)
        return

    row_paths = [
        DRAFT_REL if ctx.artifact_exists(DRAFT_REL) else FINAL_REL,
        "master/selection.json",
        "master/narrative_plan.json",
        "master/coverage_audit.json",
    ]
    row_paths = [p for p in row_paths if ctx.artifact_exists(p) or p.endswith("gap_report")]
    digest = freeze_inputs(ctx, "gap_framing_recompose", [p for p in row_paths if ctx.artifact_exists(p)])
    packet = build_evidence_packet(ctx, "gap_framing_recompose")

    draft = packet.get("artifacts", {}).get("draft_gap_report") or {}
    if not isinstance(draft, dict):
        draft = ctx.read_json(DRAFT_REL) if ctx.artifact_exists(DRAFT_REL) else ensure_gap_report_authoritative(ctx)

    ordered = []
    sel = packet.get("artifacts", {}).get("selection")
    if isinstance(sel, dict):
        ordered = [str(x) for x in (sel.get("ordered_segment_ids") or [])]

    # Deterministic recompose: drop lines targeting non-kept segments; keep operator pins
    # Long tapes: process by act/chapter shards inside one CFI (mid-pass).
    from interview_mux.refinement_midpass import run_sharded

    chapters = None
    narr = packet.get("artifacts", {}).get("narrative_plan")
    if isinstance(narr, dict):
        chapters = narr.get("chapters") if isinstance(narr.get("chapters"), list) else None

    def _process_shard(shard: list[dict[str, Any]], _idx: int) -> dict[str, Any]:
        kept: list[dict[str, Any]] = []
        shard_decisions: list[dict[str, Any]] = []
        for line in shard:
            if not isinstance(line, dict):
                continue
            lid = str(line.get("line_id") or "")
            tid = str(line.get("targets_segment_id") or "")
            origin = str(line.get("origin") or "draft")
            cat = str(line.get("line_category") or "")
            if origin == "operator":
                kept.append({**line, "origin": "operator", "recompose_action": "kept"})
                shard_decisions.append({"line_id": lid, "action": "kept", "reason": "operator_pin"})
                continue
            if cat in ("episode_preface",) or line.get("cold_open"):
                kept.append({**line, "origin": "recompose", "recompose_action": "kept"})
                shard_decisions.append({"line_id": lid, "action": "kept", "reason": "preface_or_open"})
                continue
            if oset is not None and tid and tid not in oset:
                supports = [str(s) for s in (line.get("supports_segment_ids") or [])]
                if not any(s in oset for s in supports):
                    shard_decisions.append({"line_id": lid, "action": "dropped", "reason": "target_not_in_selection"})
                    continue
            kept.append({**line, "origin": "recompose", "recompose_action": "kept"})
            shard_decisions.append({"line_id": lid, "action": "kept", "reason": "supports_kept_order"})
        return {"ok": True, "accepted": True, "lines": kept, "decisions": shard_decisions}

    candidate = copy.deepcopy(draft) if isinstance(draft, dict) else {"interviewer_lines": []}
    lines_in = list(candidate.get("interviewer_lines") or [])
    oset = set(ordered) if ordered else None
    sharded = run_sharded(lines_in, _process_shard, chapters=chapters)
    if sharded.get("quarantine"):
        skip_copy_draft_to_final(ctx, reason=str(sharded.get("reason_code") or "shard_fail"))
        append_listener_outcome(ctx, "gap_recompose_quarantine", sharded)
        after_gap_recompose_or_skip(ctx)
        if not ctx.is_done("gap_framing_recompose"):
            ctx.mark_done("gap_framing_recompose", force=True)
        return

    kept_lines = list(sharded.get("lines") or [])
    decisions: list[dict[str, Any]] = []
    for sr in sharded.get("shard_results") or []:
        if isinstance(sr, dict):
            decisions.extend(list(sr.get("decisions") or []))

    candidate["interviewer_lines"] = kept_lines
    try:
        from interview_mux.gap_vo_prior_context import (
            stamp_lines_prior_provenance,
            write_gap_vo_context_audit,
            courtesy_seed_text,
            is_interruptive_opener,
            build_prior_native_context,
            load_ordered_and_segments,
            prior_context_cfg,
        )

        stamped = stamp_lines_prior_provenance(ctx, kept_lines)
        ordered, by_id, chapters = load_ordered_and_segments(ctx)
        settings = prior_context_cfg()
        cleaned: list[dict] = []
        for row in stamped:
            if not isinstance(row, dict):
                continue
            line = dict(row)
            if line.get("prior_impact_beat") and is_interruptive_opener(str(line.get("text") or "")):
                prior = build_prior_native_context(
                    target_segment_id=str(line.get("targets_segment_id") or ""),
                    ordered_ids=ordered,
                    segments_by_id=by_id,
                    chapters=chapters,
                    cfg=settings,
                )
                line["text"] = courtesy_seed_text(
                    prior, category=str(line.get("line_category") or "framing_question")
                )
            cleaned.append(line)
        kept_lines = cleaned
        candidate["interviewer_lines"] = kept_lines
        write_gap_vo_context_audit(ctx, kept_lines)
    except Exception:
        pass
    candidate["_meta"] = {
        "producer": "gap_framing_recompose",
        "producer_stage": "gap_framing_recompose",
        "kill_dull": True,
        "shard_count": sharded.get("shard_count"),
    }
    plan = None
    if ctx.artifact_exists("understanding/gap_framing_plan.json"):
        plan = ctx.read_json("understanding/gap_framing_plan.json")

    result = accept_gap_recompose(ctx, candidate, plan if isinstance(plan, dict) else None)
    ctx.write_json(
        "understanding/gap_framing_recompose.json",
        {"decisions": decisions, "accept": result, "input_hash": digest},
    )
    _record_refinement(
        ctx,
        "gap_framing_recompose",
        "ok" if result.get("accepted") else str(result.get("reason_code") or "rejected"),
        gate=str(decision.get("gate") or "deterministic"),
        input_hash=digest,
        detail={"accept": result.get("reason_code")},
    )
    append_listener_outcome(ctx, "gap_recompose", result)
    after_gap_recompose_or_skip(ctx)
    if not ctx.is_done("gap_framing_recompose"):
        ctx.mark_done("gap_framing_recompose", force=True)


def run_selection_framing_apply(ctx: RunContext) -> None:
    from interview_mux.framing_coverage_guard import validate_framing_ranking
    from interview_mux.gap_framing import ranking_exclude_segment_ids

    ensure_gap_report_authoritative(ctx)
    if not ctx.artifact_exists("master/selection.json"):
        if not ctx.is_done("selection_framing_apply"):
            ctx.mark_done("selection_framing_apply", force=True)
        return

    decision = decide_pass(ctx, "selection_framing_apply")
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        ctx.mark_done("selection_framing_apply", force=True)
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
            ctx.write_json("master/selection.json", sel)

    if decision.get("status") == "activate":
        _record_refinement(ctx, "selection_framing_apply", "ok")
    if not ctx.is_done("selection_framing_apply"):
        ctx.mark_done("selection_framing_apply", force=True)


def _noop_refine(ctx: RunContext, pass_id: str) -> None:
    decision = decide_pass(ctx, pass_id)
    if decision.get("status") == "activate":
        # Deterministic no-op refine: mark done, ledger once, shadow not needed
        _record_refinement(ctx, pass_id, "ok", gate="deterministic", detail={"mode": "identity_refine"})
        append_listener_outcome(ctx, pass_id, {"status": "identity_ok"})
    else:
        maybe_write_shadow_score(ctx, pass_id)
    if not ctx.is_done(pass_id):
        ctx.mark_done(pass_id, force=True)


def run_narrative_arc_refine(ctx: RunContext) -> None:
    _noop_refine(ctx, "narrative_arc_refine")


def run_ranking_refine(ctx: RunContext) -> None:
    _noop_refine(ctx, "ranking_refine")


def run_transitions_refine(ctx: RunContext) -> None:
    _noop_refine(ctx, "transitions_refine")
    from interview_mux.refinement_ensemble import lint_gap_and_transitions

    lint_gap_and_transitions(ctx)


def run_sdp_intent_refine(ctx: RunContext) -> None:
    _noop_refine(ctx, "sdp_intent_refine")


def run_edl_narrative_refine(ctx: RunContext) -> None:
    _noop_refine(ctx, "edl_narrative_refine")


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
    from interview_mux.refinement_cold_open import build_cold_open_audition

    build_cold_open_audition(ctx)
