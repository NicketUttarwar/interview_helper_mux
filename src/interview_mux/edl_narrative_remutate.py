"""Typed remutate actions for edl_narrative_audit fail (no verdict soft-pass)."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.run_context import RunContext

REMUTATE_REL = "mastering/edl_narrative_remutate.json"
MAX_ATTEMPTS = 2
HOST_REPAIR_PROGRESS_NOTES = frozenset(
    {
        "rewrite_episode_orientation_meta_question",
        "rewrite_meta_question_layup",
        "dedupe_transitions_by_adjacency",
        "dedupe_transitions_for_framing",
        "drop_stale_orientation_wav",
        "reseat_required_recovery_layup",
        "promoted_pending_layup_plan",
        "layup_repair",
        "seed_missing_seated_layup",
        "ensure_adjacency_transition",
        "retarget_orientation",
        "omit_episode_orientation",
        "suppress_opening_layup",
        "drop_orphan_opening_vo",
        "drop_late_intro_reset",
        "drop_post_coda_reverse_jump",
        "prune_stale_transitions",
        "align_selection_chapters",
        "repair_coverage_for_selection",
        "align_narrative_plan",
    }
)

# Orientation-only notes must not short-circuit remutate when the audit fail is
# chapter-cap / duplicate-title overflow (selection.chapters still broken).
CHAPTER_OVERFLOW_MARKERS: tuple[str, ...] = (
    "nine chapters",
    "maximum of eight",
    "authoritative maximum",
    "duplicate chapter title",
    "chapter assignment is not aligned",
    "exceeding the authoritative",
    "unsupported duplicate chapter",
)
CHAPTER_FIX_PROGRESS_NOTES = frozenset(
    {
        "align_selection_chapters",
        "align_narrative_plan",
        "merge_duplicate_chapter_titles",
        "clamp_chapters_to_budget",
    }
)

# Allowlisted issue → action classifiers (substring match on lowered text).
# align_plan is checked before transitions so "transition" mentions inside a
# chapter/plan mismatch do not rewind spoken bridges.
_CLASSIFIERS: list[tuple[str, tuple[str, ...]]] = [
    (
        "rerank",
        (
            "rerank",
            "full_master_ranking",
            "reorder",
            "selection order",
            "ordered_segment",
            "finale",
            "leftover",
            "appear after",
            "early-chapter",
            "early-story",
            "nine chapters",
            "maximum of eight",
            "authoritative maximum",
            "duplicate chapter title",
            "chapter assignment is not aligned",
            "exceeding the authoritative",
        ),
    ),
    (
        "align_plan",
        (
            "narrative plan",
            "narrative_plan",
            "align narrative",
            "chapter sequence",
            "chapter membership",
            "selected chapter",
            "air order",
            "practical-payoff",
            "adoption-hurdle",
            "adoption chapter",
            "chapter-plan",
            "chapter plan",
            "align narrative_plan",
            "revised chapter",
        ),
    ),
    (
        "transitions",
        (
            "transition",
            "bridge",
            "seam",
            "hinge",
            "chapter join",
        ),
    ),
    (
        "rebase_gap_vo",
        (
            "gap vo",
            "gap_report",
            "vo pickup",
            "missing_question",
            "interviewer line",
            "layup",
            "framing line",
            "orientation",
            "meta-question",
            "episode framing",
        ),
    ),
    (
        "drop_blank",
        (
            "blank segment",
            "unusable segment",
            "empty segment",
            "near-silence",
        ),
    ),
]

_METADATA_ALIGN_ACTIONS = frozenset({"align_plan", "operator"})

_ACTION_STAGES: dict[str, list[str]] = {
    "rerank": ["full_master_ranking", "edl_narrative_audit"],
    # Metadata heal + re-audit only — do not rewind transitions/VO seats.
    "align_plan": ["edl_narrative_audit"],
    "transitions": ["transitions", "edl_narrative_audit"],
    "rebase_gap_vo": [
        "selection_framing_apply",
        "nugget_layup_compose",
        "vo_line_adjudicate",
        "vo_synthesize",
        "edl_narrative_audit",
    ],
    "drop_blank": ["full_master_ranking", "edl_narrative_audit"],
    "operator": [],
}

_SEATED_LAYUP_RE = re.compile(
    r"layup for (seg_\d+)\s+is seated but missing",
    re.IGNORECASE,
)
_ADJACENCY_RE = re.compile(
    r"adjacency from (seg_\d+) to (seg_\d+)",
    re.IGNORECASE,
)


def _audit_issue_blobs(audit: dict[str, Any] | None) -> list[str]:
    blobs: list[str] = []
    if not isinstance(audit, dict):
        return blobs
    for issue in audit.get("blocking_issues") or []:
        if isinstance(issue, dict):
            blobs.append(
                " ".join(
                    str(issue.get(k) or "")
                    for k in ("issue", "summary", "reason", "recommended_action")
                )
            )
        else:
            blobs.append(str(issue or ""))
    for raw in audit.get("recommended_actions") or []:
        blobs.append(str(raw or ""))
    return [b for b in blobs if b.strip()]


def seed_missing_seated_layups(ctx: RunContext) -> tuple[list[str], list[tuple[str, str]]]:
    """Insert VO + adjacency transition when audit says a seated layup is missing.

    Orientation retarget / mid-episode VO dedupe cannot cover a high-severity
    native that the audit already seated but never received a targeting line.
    """
    notes: list[str] = []
    audit = (
        ctx.read_json("master/edl_narrative_audit.json")
        if ctx.artifact_exists("master/edl_narrative_audit.json")
        else {}
    )
    blobs = _audit_issue_blobs(audit if isinstance(audit, dict) else {})
    if not blobs:
        job = (
            ctx.read_json("gui_job.json") if ctx.artifact_exists("gui_job.json") else {}
        )
        if isinstance(job, dict):
            blobs.append(str(job.get("error") or job.get("message") or ""))
    targets: list[str] = []
    adjacencies: list[tuple[str, str]] = []
    for blob in blobs:
        seated = _SEATED_LAYUP_RE.search(blob)
        if seated:
            sid = seated.group(1)
            if sid not in targets:
                targets.append(sid)
        adj = _ADJACENCY_RE.search(blob)
        if adj:
            pair = (adj.group(1), adj.group(2))
            if pair not in adjacencies:
                adjacencies.append(pair)
            if pair[1] not in targets:
                targets.append(pair[1])
    if not targets and not adjacencies:
        return notes, adjacencies

    gap = (
        ctx.read_json("understanding/gap_report.json")
        if ctx.artifact_exists("understanding/gap_report.json")
        else {"interviewer_lines": []}
    )
    if not isinstance(gap, dict):
        gap = {"interviewer_lines": []}
    lines = gap.get("interviewer_lines")
    if not isinstance(lines, list):
        lines = []
        gap["interviewer_lines"] = lines
    covered = {
        str(ln.get("targets_segment_id") or "")
        for ln in lines
        if isinstance(ln, dict)
    }
    evals: dict[str, Any] = {}
    if ctx.artifact_exists("understanding/gap_evaluations.json"):
        loaded = ctx.read_json("understanding/gap_evaluations.json")
        if isinstance(loaded, dict):
            evals = loaded
    by_seg = {
        str(row.get("segment_id") or ""): row
        for row in (evals.get("evaluations") or [])
        if isinstance(row, dict)
    }
    for sid in targets:
        if not sid or sid in covered:
            continue
        row = by_seg.get(sid) or {}
        rec = str(row.get("recommended_framing") or "").strip()
        conf = str(row.get("listener_confusion") or "").strip()
        text = rec or (
            f"Before we go further: {conf[:180]}"
            if conf
            else "Before we go further, what made that next step actually usable?"
        )
        lines.append(
            {
                "line_id": f"vo_edl_seat_{sid}",
                "text": text,
                "delivery": "synthesize",
                "placement": "before",
                "targets_segment_id": sid,
                "gap_type": row.get("gap_type") or "missing_setup",
                "required": True,
                "category": "story_bridge",
                "origin": "edl_narrative_seated_layup",
            }
        )
        covered.add(sid)
        notes.append("seed_missing_seated_layup")
    if notes:
        try:
            from interview_mux.artifact_repairs import repair_gap_report
            from interview_mux.artifact_writes import write_validated_artifact

            repaired, _ = repair_gap_report(ctx, gap)
            write_validated_artifact(
                ctx,
                "understanding/gap_report.json",
                repaired,
                merge_from_disk=True,
                stage_key="gap_framing_compose",
            )
        except Exception:
            ctx.write_json(
                "understanding/gap_report.json",
                gap,
                stage_key="gap_framing_compose",
                mutation_class="compose_copy",
            )
    return notes, adjacencies


_ISSUE_CODE_ACTIONS: dict[str, str] = {
    "ordering_constraint_broken": "rerank",
    "coverage_missing": "rerank",
    "selected_continuity_broken": "rerank",
    "chapter_continuity_broken": "align_plan",
    "duplicate_spoken_seam": "transitions",
    "transition_missing": "transitions",
    "transition_adjacency_invalid": "transitions",
    "gap_vo_missing": "rebase_gap_vo",
    "gap_vo_target_invalid": "rebase_gap_vo",
    "opening_orientation_invalid": "rebase_gap_vo",
    "pre_edl_vo_placement_missing": "rebase_gap_vo",
    "invalid_segment_reference": "align_plan",
    "blank_segment": "drop_blank",
    "selection_excluded_intentional": "align_plan",
    "panel_handoff_unclear": "transitions",
}


def classify_edl_narrative_issue(text: str, *, code: str | None = None) -> str:
    coded = str(code or "").strip().lower()
    if coded in _ISSUE_CODE_ACTIONS:
        return _ISSUE_CODE_ACTIONS[coded]
    blob = str(text or "").strip().lower()
    if not blob:
        return "operator"
    # Duplicate VO+transition on one adjacency is a transitions drop, even when
    # the prose names vo_layup (exec_13157 Chapter 3→4 handoff).
    if any(
        n in blob
        for n in (
            "two spoken bridges",
            "duplicate framing",
            "same selected adjacency",
            "duplicate vo + transition",
            "duplicate vo and transition",
        )
    ):
        return "transitions"
    # VO/orientation defects often mention "transition coverage". Classify those
    # as gap-VO repair before the generic "transition" needle.
    vo_needles = (
        "orientation",
        "meta-question",
        "episode framing",
        "gap vo",
        "vo pickup",
        "vo_layup",
        "vo_ingest",
        "missing_question",
        "interviewer line",
        "layup",
        "framing line",
    )
    if any(n in blob for n in vo_needles):
        return "rebase_gap_vo"
    # Plan/chapter membership vs selected air order — before "transition".
    for action, needles in _CLASSIFIERS:
        if action == "align_plan" and any(n in blob for n in needles):
            return "align_plan"
    for action, needles in _CLASSIFIERS:
        if action in {"rebase_gap_vo", "align_plan"}:
            continue
        if any(n in blob for n in needles):
            return action
    return "operator"


def narrative_audit_blocks_edl(ctx: RunContext) -> bool:
    """True only for blocking issues not contradicted by current disk artifacts."""
    if not ctx.artifact_exists("master/edl_narrative_audit.json"):
        return False
    try:
        audit = ctx.read_json("master/edl_narrative_audit.json")
    except Exception:
        return False
    if not isinstance(audit, dict):
        return False
    return bool(effective_narrative_blocking_issues(ctx, audit))


def effective_narrative_blocking_issues(
    ctx: RunContext,
    audit: dict[str, Any] | None = None,
) -> list[Any]:
    """Return only live audit blockers; stale LLM claims never gate EDL."""
    if audit is None:
        if not ctx.artifact_exists("master/edl_narrative_audit.json"):
            return []
        try:
            loaded = ctx.read_json("master/edl_narrative_audit.json")
        except Exception:
            return []
        audit = loaded if isinstance(loaded, dict) else {}
    if not isinstance(audit, dict):
        return []
    from interview_mux.artifact_repairs import _edl_issue_contradicted_by_disk

    remaining: list[Any] = []
    for issue in audit.get("blocking_issues") or []:
        if isinstance(issue, dict) and _edl_issue_contradicted_by_disk(ctx, issue):
            continue
        remaining.append(issue)
    return remaining


def resume_after_narrative_audit_fail(preferred: str | None = None) -> str:
    """Never resume at edl while the narrative audit is fail."""
    pin = str(preferred or "").strip() or "edl_narrative_audit"
    if pin == "edl":
        return "edl_narrative_audit"
    return pin


def classify_edl_narrative_audit(audit: dict[str, Any] | None) -> list[str]:
    if not isinstance(audit, dict):
        return ["operator"]
    actions: list[str] = []
    for issue in audit.get("blocking_issues") or []:
        if isinstance(issue, dict):
            blob = " ".join(
                str(issue.get(k) or "")
                for k in ("issue", "summary", "reason", "recommended_action")
            )
        else:
            blob = str(issue or "")
        actions.append(
            classify_edl_narrative_issue(
                blob,
                code=str(issue.get("code") or "") if isinstance(issue, dict) else None,
            )
        )
    for raw in audit.get("recommended_actions") or []:
        actions.append(classify_edl_narrative_issue(str(raw or "")))
    # Stable unique order
    out: list[str] = []
    for a in actions:
        if a not in out:
            out.append(a)
    return out or ["operator"]


def plan_edl_narrative_remutate(
    ctx: RunContext, audit: dict[str, Any]
) -> dict[str, Any]:
    prior = (
        ctx.read_json(REMUTATE_REL)
        if ctx.artifact_exists(REMUTATE_REL)
        else {}
    )
    prior = prior if isinstance(prior, dict) else {}
    prior_attempt = int(prior.get("attempt") or 0)
    # Sticky exhausted — do not climb forever (exec_11559 hit attempt 230).
    if prior.get("exhausted") and prior_attempt >= MAX_ATTEMPTS:
        plan = {
            "version": 1,
            "attempt": prior_attempt,
            "max_attempts": MAX_ATTEMPTS,
            "actions": list(prior.get("actions") or classify_edl_narrative_audit(audit)),
            "from_stages": list(prior.get("from_stages") or []),
            "from_stage": prior.get("from_stage"),
            "exhausted": True,
        }
        ctx.write_json(REMUTATE_REL, plan)
        return plan
    attempt = prior_attempt + 1
    actions = classify_edl_narrative_audit(audit)
    stages: list[str] = []
    for action in actions:
        for sid in _ACTION_STAGES.get(action) or []:
            if sid not in stages:
                stages.append(sid)
    plan = {
        "version": 1,
        "attempt": attempt,
        "max_attempts": MAX_ATTEMPTS,
        "actions": actions,
        "from_stages": stages,
        "from_stage": stages[0] if stages else None,
        "exhausted": attempt > MAX_ATTEMPTS or not stages,
    }
    ctx.write_json(REMUTATE_REL, plan)
    return plan


def apply_edl_narrative_metadata_align(ctx: RunContext) -> dict[str, Any]:
    """Align selection chapters + narrative_plan to air order (no VO seat rewrites).

    Safe under soft/hard seat freeze — metadata only.
    """
    from interview_mux.artifact_ownership import freeze_write_allowed

    if not freeze_write_allowed(
        ctx,
        "edl_narrative_audit",
        "narrative_metadata_align",
    ):
        return {
            "ok": False,
            "notes": ["freeze_blocked_narrative_metadata_align"],
            "cleared": [],
            "from_stage": "edl_narrative_audit",
            "host_fixed": False,
        }
    notes: list[str] = []
    cleared: list[str] = []
    try:
        if ctx.artifact_exists("master/selection.json"):
            from interview_mux.air_order_boundary import commit_selection_mutation
            from interview_mux.artifact_repairs import repair_master_selection

            sel_c = ctx.read_json("master/selection.json")
            if isinstance(sel_c, dict):
                before_order = [
                    str(x) for x in (sel_c.get("ordered_segment_ids") or []) if x
                ]
                before_ch = [
                    tuple((ch.get("segment_ids") or []) if isinstance(ch, dict) else [])
                    for ch in (sel_c.get("chapters") or [])
                ]
                repaired_sel, sel_notes = repair_master_selection(ctx, sel_c)
                repaired_sel = commit_selection_mutation(
                    ctx,
                    repaired_sel,
                    producer="edl_narrative_metadata_align",
                    stage_key="edl_narrative_audit",
                    checkpoint_mode="detect",
                    merge_from_disk=False,
                    write_committed=True,
                )
                after_order = [
                    str(x)
                    for x in (repaired_sel.get("ordered_segment_ids") or [])
                    if x
                ]
                after_ch = [
                    tuple((ch.get("segment_ids") or []) if isinstance(ch, dict) else [])
                    for ch in (repaired_sel.get("chapters") or [])
                ]
                if (
                    after_ch != before_ch
                    or after_order != before_order
                    or any(
                        isinstance(n, dict)
                        and n.get("action")
                        in {
                            "drop_empty_selection_chapters",
                            "sort_chapter_air_order_by_source_time",
                            "sort_selection_chapters_to_air_order",
                            "merge_duplicate_chapter_titles",
                            "clamp_chapters_to_budget",
                        }
                        for n in sel_notes
                    )
                ):
                    notes.append("align_selection_chapters")
    except Exception as exc:
        notes.append(f"chapters:{exc}")
    try:
        from interview_mux.artifact_repairs import align_narrative_plan_to_selection

        align_notes = align_narrative_plan_to_selection(ctx)
        if align_notes:
            notes.append("align_narrative_plan")
    except Exception as exc:
        notes.append(f"narrative_plan:{exc}")
    try:
        if ctx.artifact_exists("master/coverage_audit.json") and ctx.artifact_exists(
            "master/selection.json"
        ):
            from interview_mux.artifact_repairs import repair_coverage_audit
            from interview_mux.artifact_writes import write_validated_artifact

            cov = ctx.read_json("master/coverage_audit.json")
            if isinstance(cov, dict):
                repaired_cov, cov_notes = repair_coverage_audit(ctx, cov)
                write_validated_artifact(
                    ctx,
                    "master/coverage_audit.json",
                    repaired_cov,
                    merge_from_disk=False,
                    stage_key="topic_coverage_audit",
                )
                if cov_notes:
                    notes.append("repair_coverage_for_selection")
    except Exception as exc:
        notes.append(f"coverage:{exc}")
    for sid in ("edl", "edl_narrative_audit"):
        marker = ctx.run_dir / ".stage_done" / sid
        if marker.is_file():
            marker.unlink(missing_ok=True)
            cleared.append(sid)
    fixed = bool(CHAPTER_FIX_PROGRESS_NOTES.intersection(notes))
    return {
        "ok": fixed,
        "notes": notes,
        "cleared": cleared,
        "from_stage": "edl_narrative_audit",
        "host_fixed": fixed,
    }


def _dedupe_framing_transitions_under_freeze(ctx: RunContext) -> list[str]:
    """Drop transition when required VO already covers the adjacency.

    Safe under seat freeze: touches transitions.json only (no VO/seat rewrite).
    """
    from interview_mux.artifact_ownership import freeze_write_allowed

    if not freeze_write_allowed(ctx, "transitions", "transition_dedupe"):
        return ["freeze_blocked_transition_dedupe"]
    notes: list[str] = []
    if not ctx.artifact_exists("master/transitions.json"):
        return notes
    try:
        from interview_mux.gap_framing import (
            dedupe_transitions_by_adjacency,
            dedupe_transitions_for_framing,
        )
        from interview_mux.transition_vo import persist_transitions_doc

        tr = ctx.read_json("master/transitions.json")
        if not isinstance(tr, dict):
            return notes
        gap = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else {}
        )
        before = len(tr.get("transitions") or [])
        tr = dedupe_transitions_for_framing(
            gap if isinstance(gap, dict) else {}, tr, ctx=ctx
        )
        tr = dedupe_transitions_by_adjacency(tr)
        tr = persist_transitions_doc(ctx, tr, stage_key="transitions")
        after = len(tr.get("transitions") or [])
        if after < before:
            notes.append("dedupe_transitions_for_framing")
        from interview_mux.seam_occupancy import build_seam_occupancy

        occupancy = build_seam_occupancy(
            ctx,
            transitions_doc=tr,
            stage_key="transitions",
        )
        if occupancy.get("clean") and ctx.artifact_exists(
            "master/edl_narrative_audit.json"
        ):
            from interview_mux.artifact_repairs import repair_edl_audit

            audit = ctx.read_json("master/edl_narrative_audit.json")
            repaired, _ = repair_edl_audit(
                ctx, audit if isinstance(audit, dict) else {}
            )
            if not repaired.get("blocking_issues") and str(
                repaired.get("verdict") or ""
            ).lower() != "fail":
                ctx.write_json(
                    "master/edl_narrative_audit.json",
                    repaired,
                    stage_key="edl_narrative_audit",
                    skip_handoff=True,
                )
                notes.append("upgrade_fail_audit_after_clean_occupancy")
    except Exception as exc:
        notes.append(f"transitions_freeze_dedupe:{exc}")
    return notes


def apply_edl_narrative_host_repair(ctx: RunContext) -> dict[str, Any]:
    """Rewrite unusable orientation/layup copy and keep one transition per adjacency.

    Does not rewind ranking or recompose layup. Does not soft-pass the audit.
    Metadata plan/chapter align always runs even when seat freeze blocks VO work.
    Framing-vs-transition dedupe still runs under freeze (transitions-only).
    """
    from interview_mux.artifact_ownership import freeze_write_allowed

    if not freeze_write_allowed(
        ctx,
        "edl_narrative_audit",
        "narrative_host_repair",
    ):
        meta = apply_edl_narrative_metadata_align(ctx)
        notes = list(meta.get("notes") or [])
        notes.extend(_dedupe_framing_transitions_under_freeze(ctx))
        notes.append("seat_freeze_blocked_host_repair")
        return {
            "ok": bool(HOST_REPAIR_PROGRESS_NOTES.intersection(notes)),
            "notes": notes,
            "cleared": list(meta.get("cleared") or []),
            "from_stage": "edl_narrative_audit",
            "host_fixed": bool(HOST_REPAIR_PROGRESS_NOTES.intersection(notes)),
        }
    try:
        from interview_mux.seat_authority import soft_freeze_active, request_seat_rewrite

        if soft_freeze_active(ctx):
            dec = request_seat_rewrite(
                ctx,
                proposed_delta={"ops": [], "from": "edl_narrative_host_repair"},
                reason="edl_narrative_host_repair",
                symptoms=["narrative_host_repair"],
            )
            if not dec.get("allow"):
                meta = apply_edl_narrative_metadata_align(ctx)
                notes = list(meta.get("notes") or [])
                notes.extend(_dedupe_framing_transitions_under_freeze(ctx))
                if "seat_freeze_blocked_host_repair" not in notes:
                    notes.append("seat_freeze_blocked_host_repair")
                return {
                    "ok": bool(HOST_REPAIR_PROGRESS_NOTES.intersection(notes)),
                    "notes": notes,
                    "cleared": list(meta.get("cleared") or []),
                    "from_stage": "edl_narrative_audit",
                    "host_fixed": bool(HOST_REPAIR_PROGRESS_NOTES.intersection(notes)),
                    "gate": dec,
                }
    except Exception:
        # b10 fail-closed when freeze may be active / unknown
        try:
            from interview_mux.seat_authority import soft_freeze_active, hard_freeze_active

            frozen = bool(soft_freeze_active(ctx) or hard_freeze_active(ctx))
        except Exception:
            frozen = True
        if frozen:
            meta = apply_edl_narrative_metadata_align(ctx)
            notes = list(meta.get("notes") or [])
            notes.extend(_dedupe_framing_transitions_under_freeze(ctx))
            if "seat_freeze_blocked_host_repair_fail_closed" not in notes:
                notes.append("seat_freeze_blocked_host_repair_fail_closed")
            return {
                "ok": bool(HOST_REPAIR_PROGRESS_NOTES.intersection(notes)),
                "notes": notes,
                "cleared": list(meta.get("cleared") or []),
                "from_stage": "edl_narrative_audit",
                "host_fixed": bool(HOST_REPAIR_PROGRESS_NOTES.intersection(notes)),
            }
    notes: list[str] = []
    pending_adj: list[tuple[str, str]] = []
    try:
        seeded, pending_adj = seed_missing_seated_layups(ctx)
        notes.extend(seeded)
    except Exception as exc:
        notes.append(f"seated_layup:{exc}")
    before_orientation = ""
    try:
        from interview_mux.opening_orientation import (
            is_episode_orientation,
            retarget_orientation_to_open,
        )

        if ctx.artifact_exists("understanding/gap_report.json"):
            gap0 = ctx.read_json("understanding/gap_report.json")
            for line in (gap0.get("interviewer_lines") or []) if isinstance(gap0, dict) else []:
                if isinstance(line, dict) and is_episode_orientation(line):
                    before_orientation = str(line.get("text") or "")
                    break
        written = retarget_orientation_to_open(ctx)
        after_orientation = before_orientation
        if ctx.artifact_exists("understanding/gap_report.json"):
            gap1 = ctx.read_json("understanding/gap_report.json")
            for line in (gap1.get("interviewer_lines") or []) if isinstance(gap1, dict) else []:
                if isinstance(line, dict) and is_episode_orientation(line):
                    after_orientation = str(line.get("text") or "")
                    break
        if after_orientation != before_orientation:
            notes.append("rewrite_episode_orientation_meta_question")
        elif written:
            notes.append("retarget_orientation")
        try:
            from interview_mux.opening_orientation import orientation_omitted

            gap_o = (
                ctx.read_json("understanding/gap_report.json")
                if ctx.artifact_exists("understanding/gap_report.json")
                else {}
            )
            if orientation_omitted(gap_o if isinstance(gap_o, dict) else None):
                notes.append("omit_episode_orientation")
        except Exception:
            pass
        try:
            from interview_mux.opening_adjacency_repair import (
                drop_late_intro_reset_from_selection,
                drop_orphan_opening_vo_when_native_orients,
                drop_post_coda_reverse_jump_from_selection,
                suppress_opening_layup_when_orientation_owns_slot,
            )

            suppressed = suppress_opening_layup_when_orientation_owns_slot(ctx)
            if suppressed:
                notes.append("suppress_opening_layup")
            dropped = drop_orphan_opening_vo_when_native_orients(ctx)
            if dropped:
                notes.append("drop_orphan_opening_vo")
            late = drop_late_intro_reset_from_selection(ctx)
            if late:
                notes.append("drop_late_intro_reset")
            jumped = drop_post_coda_reverse_jump_from_selection(ctx)
            if jumped:
                notes.append("drop_post_coda_reverse_jump")
        except Exception as adj_exc:
            notes.append(f"opening_adjacency:{adj_exc}")
    except Exception as exc:
        notes.append(f"orientation:{exc}")
    try:
        import json
        from pathlib import Path

        from interview_mux.nugget_layup import (
            PLAN_REL,
            publish_layup_plan_to_gap_report,
            repair_or_skip_spoken_copy_layups,
        )

        if not ctx.artifact_exists(PLAN_REL):
            pending = (
                Path(ctx.run_dir)
                / ".pending_writes"
                / "nugget_layup_compose"
                / "understanding"
                / "nugget_layup_plan.json"
            )
            if pending.is_file():
                ctx.write_json(
                    PLAN_REL,
                    json.loads(pending.read_text(encoding="utf-8")),
                )
                notes.append("promoted_pending_layup_plan")
        if ctx.artifact_exists(PLAN_REL):
            plan = ctx.read_json(PLAN_REL)
            repaired, repair_notes = repair_or_skip_spoken_copy_layups(
                ctx, plan if isinstance(plan, dict) else {}
            )
            ctx.write_json(PLAN_REL, repaired)
            publish_layup_plan_to_gap_report(ctx, repaired)
            if any(
                isinstance(n, dict) and n.get("action") == "rewrite_meta_question_layup"
                for n in repair_notes
            ):
                notes.append("rewrite_meta_question_layup")
            elif repair_notes:
                notes.append("layup_repair")
        from interview_mux.write_staging import discard_stage_writes

        pending_dir = Path(ctx.run_dir) / ".pending_writes" / "nugget_layup_compose"
        had_pending = pending_dir.exists() and any(pending_dir.rglob("*"))
        discard_stage_writes(ctx, "nugget_layup_compose")
        if had_pending:
            notes.append("discard_stale_layup_pending")
    except Exception as exc:
        notes.append(f"layup:{exc}")
    try:
        from interview_mux.air_script import (
            compose_pass_b,
            load_air_script,
            omitted_vo_line_ids,
            persist_air_script_omits_on_gap_report,
        )
        from interview_mux.mastering_plan_loader import load_plan_raw

        plan0 = load_plan_raw(ctx)
        if isinstance(plan0, dict) and load_air_script(plan0):
            omitted_before = omitted_vo_line_ids(plan0)
            compose_pass_b(ctx)
            persist_air_script_omits_on_gap_report(ctx)
            omitted_after = omitted_vo_line_ids(load_plan_raw(ctx))
            if omitted_before - omitted_after:
                notes.append("reseat_required_recovery_layup")
    except Exception as exc:
        notes.append(f"air_script:{exc}")
    if ctx.artifact_exists("master/transitions.json"):
        try:
            from interview_mux.gap_framing import (
                dedupe_transitions_by_adjacency,
                dedupe_transitions_for_framing,
            )

            tr = ctx.read_json("master/transitions.json")
            if isinstance(tr, dict):
                gap = (
                    ctx.read_json("understanding/gap_report.json")
                    if ctx.artifact_exists("understanding/gap_report.json")
                    else {}
                )
                before = len(tr.get("transitions") or [])
                tr = dedupe_transitions_for_framing(
                    gap if isinstance(gap, dict) else {}, tr
                )
                tr = dedupe_transitions_by_adjacency(tr)
                from interview_mux.transition_vo import persist_transitions_doc

                tr = persist_transitions_doc(ctx, tr, stage_key="transitions")
                after = len(tr.get("transitions") or [])
                if after < before:
                    notes.append("dedupe_transitions_by_adjacency")
            try:
                from interview_mux.gap_framing import prune_transitions_outside_selection

                sel_ids = []
                if ctx.artifact_exists("master/selection.json"):
                    sel0 = ctx.read_json("master/selection.json")
                    sel_ids = [
                        str(x)
                        for x in ((sel0 or {}).get("ordered_segment_ids") or [])
                        if x
                    ]
                before_n = len(tr.get("transitions") or [])
                tr = prune_transitions_outside_selection(tr, sel_ids)
                from interview_mux.transition_vo import persist_transitions_doc

                tr = persist_transitions_doc(ctx, tr, stage_key="transitions")
                after_n = len(tr.get("transitions") or [])
                if after_n < before_n:
                    notes.append("prune_stale_transitions")
            except Exception as prune_exc:
                notes.append(f"prune_transitions:{prune_exc}")
        except Exception as exc:
            notes.append(f"transitions:{exc}")
    try:
        if ctx.artifact_exists("master/selection.json"):
            from interview_mux.artifact_repairs import repair_master_selection
            from interview_mux.artifact_writes import write_validated_artifact

            sel_c = ctx.read_json("master/selection.json")
            if isinstance(sel_c, dict):
                before_order = [
                    str(x) for x in (sel_c.get("ordered_segment_ids") or []) if x
                ]
                before_ch = [
                    tuple((ch.get("segment_ids") or []) if isinstance(ch, dict) else [])
                    for ch in (sel_c.get("chapters") or [])
                ]
                repaired_sel, sel_notes = repair_master_selection(ctx, sel_c)
                from interview_mux.air_order_boundary import commit_selection_mutation

                # write_committed: chapter merge/clamp must land on disk even when
                # another stage (e.g. edl) holds pending staging that still has the
                # overflow chapter list.
                repaired_sel = commit_selection_mutation(
                    ctx,
                    repaired_sel,
                    producer="edl_narrative_remutate",
                    stage_key="full_master_ranking",
                    checkpoint_mode="detect",
                    merge_from_disk=False,
                    write_committed=True,
                )
                after_order = [
                    str(x)
                    for x in (repaired_sel.get("ordered_segment_ids") or [])
                    if x
                ]
                after_ch = [
                    tuple((ch.get("segment_ids") or []) if isinstance(ch, dict) else [])
                    for ch in (repaired_sel.get("chapters") or [])
                ]
                if (
                    after_ch != before_ch
                    or after_order != before_order
                    or any(
                        isinstance(n, dict)
                        and n.get("action")
                        in {
                            "drop_empty_selection_chapters",
                            "sort_chapter_air_order_by_source_time",
                            "merge_duplicate_chapter_titles",
                            "clamp_chapters_to_budget",
                        }
                        for n in sel_notes
                    )
                ):
                    notes.append("align_selection_chapters")
    except Exception as exc:
        notes.append(f"chapters:{exc}")
    try:
        from interview_mux.artifact_repairs import align_narrative_plan_to_selection

        align_notes = align_narrative_plan_to_selection(ctx)
        if align_notes:
            notes.append("align_narrative_plan")
    except Exception as exc:
        notes.append(f"narrative_plan:{exc}")
    try:
        if ctx.artifact_exists("master/coverage_audit.json") and ctx.artifact_exists(
            "master/selection.json"
        ):
            from interview_mux.artifact_repairs import repair_coverage_audit
            from interview_mux.artifact_writes import write_validated_artifact

            cov = ctx.read_json("master/coverage_audit.json")
            if isinstance(cov, dict):
                repaired_cov, cov_notes = repair_coverage_audit(ctx, cov)
                write_validated_artifact(
                    ctx,
                    "master/coverage_audit.json",
                    repaired_cov,
                    merge_from_disk=False,
                    stage_key="topic_coverage_audit",
                )
                if any(
                    isinstance(n, dict)
                    and n.get("action")
                    in {
                        "bind_coverage_to_selection",
                        "alias_topic_mapping_to_brief",
                        "drop_missing_coverage_now_bound",
                    }
                    for n in cov_notes
                ):
                    notes.append("repair_coverage_for_selection")
    except Exception as exc:
        notes.append(f"coverage:{exc}")
    if pending_adj:
        try:
            tr = (
                ctx.read_json("master/transitions.json")
                if ctx.artifact_exists("master/transitions.json")
                else {"transitions": []}
            )
            if not isinstance(tr, dict):
                tr = {"transitions": []}
            rows = tr.get("transitions")
            if not isinstance(rows, list):
                rows = []
                tr["transitions"] = rows
            have = {
                (
                    str(r.get("after_segment_id") or ""),
                    str(r.get("before_segment_id") or ""),
                )
                for r in rows
                if isinstance(r, dict)
            }
            added = False
            by_id: dict[str, dict[str, Any]] = {}
            try:
                if ctx.artifact_exists("segments/manifest.json"):
                    man = ctx.read_json("segments/manifest.json")
                    by_id = {
                        str(s.get("segment_id")): s
                        for s in ((man or {}).get("segments") or [])
                        if isinstance(s, dict) and s.get("segment_id")
                    }
            except Exception:
                by_id = {}
            from interview_mux.seam_glue import (
                default_bridge_text,
                enrich_bridge_pair_excerpts,
            )

            for after_id, before_id in pending_adj:
                if (after_id, before_id) in have:
                    continue
                pair = enrich_bridge_pair_excerpts(
                    {
                        "after_segment_id": after_id,
                        "before_segment_id": before_id,
                    },
                    by_id,
                )
                text = str(default_bridge_text(pair) or "").strip()
                if not text:
                    text = "With that established, what changed?"
                rows.append(
                    {
                        "after_segment_id": after_id,
                        "before_segment_id": before_id,
                        "type": "spoken_bridge",
                        "text": text,
                    }
                )
                have.add((after_id, before_id))
                added = True
            if added:
                ctx.write_json(
                    "master/transitions.json",
                    tr,
                    stage_key="transitions",
                    mutation_class="transition_repair",
                )
                notes.append("ensure_adjacency_transition")
        except Exception as exc:
            notes.append(f"ensure_adj:{exc}")
    try:
        prior = (
            ctx.read_json(REMUTATE_REL) if ctx.artifact_exists(REMUTATE_REL) else {}
        )
        if not isinstance(prior, dict):
            prior = {}
        prior["exhausted"] = False
        prior["attempt"] = 0
        prior["host_repair"] = notes
        ctx.write_json(REMUTATE_REL, prior)
    except Exception:
        pass
    try:
        from interview_mux.transition_vo import commit_current_transition_wavs

        still = commit_current_transition_wavs(ctx)
        notes.append("resync_current_transition_wavs")
        if still:
            notes.append("transition_wavs_missing:" + ",".join(still[:6]))
    except Exception as exc:
        notes.append(f"resync_vo:{exc}")
    cleared: list[str] = []
    for sid in ("g1_vo_pickup", "edl", "edl_narrative_audit"):
        marker = ctx.run_dir / ".stage_done" / str(sid)
        if marker.is_file():
            marker.unlink(missing_ok=True)
            cleared.append(str(sid))
    if "rewrite_episode_orientation_meta_question" in notes:
        try:
            from interview_mux.opening_orientation import ORIENTATION_LINE_ID

            pickup = ctx.final_path("vo_pickup")
            for folder in (pickup, pickup / "synthesized"):
                wav = folder / f"{ORIENTATION_LINE_ID}.wav"
                if wav.is_file():
                    wav.unlink()
                    notes.append("drop_stale_orientation_wav")
        except Exception:
            pass
    try:
        audit_path = ctx.path("master", "edl_narrative_audit.json")
        if audit_path.is_file():
            import json as _json

            try:
                prior_audit = _json.loads(audit_path.read_text(encoding="utf-8"))
            except Exception:
                prior_audit = {}
            if str((prior_audit or {}).get("verdict") or "").strip().lower() == "fail":
                audit_path.unlink(missing_ok=True)
                notes.append("drop_stale_fail_audit")
    except Exception:
        pass
    from_stage = "edl_narrative_audit"
    if "drop_late_intro_reset" in notes or "drop_post_coda_reverse_jump" in notes:
        from_stage = "nugget_layup_compose"
        for sid in ("nugget_layup_compose", "selection_framing_apply", "transitions"):
            marker = ctx.run_dir / ".stage_done" / sid
            if marker.is_file():
                marker.unlink(missing_ok=True)
                cleared.append(sid)
    elif "seed_missing_seated_layup" in notes:
        from_stage = "sound_design_vo_finalize"
    elif "ensure_adjacency_transition" in notes:
        from_stage = "transitions"
    return {
        "ok": True,
        "from_stage": from_stage,
        "notes": notes,
        "cleared": cleared,
        "host_fixed": bool(HOST_REPAIR_PROGRESS_NOTES.intersection(notes)),
    }


def _host_progress_notes(host: dict[str, Any] | None) -> set[str]:
    notes = (host or {}).get("notes") or []
    return HOST_REPAIR_PROGRESS_NOTES.intersection(notes)


def _remutate_from_host_progress(host: dict[str, Any], *, extra_notes: list[str] | None = None) -> dict[str, Any]:
    notes = list(host.get("notes") or [])
    if extra_notes:
        notes.extend(extra_notes)
    from_stage = str(host.get("from_stage") or "edl_narrative_audit")
    if "drop_late_intro_reset" in notes or "drop_post_coda_reverse_jump" in notes:
        from_stage = "nugget_layup_compose"
    elif CHAPTER_FIX_PROGRESS_NOTES.intersection(notes):
        from_stage = "edl_narrative_audit"
    return {
        "ok": True,
        "cleared": list(host.get("cleared") or []),
        "from_stage": resume_after_narrative_audit_fail(from_stage),
        "host_fixed": True,
        "notes": notes,
        "reason": "host_metadata_or_vo_progress",
    }


def apply_edl_narrative_remutate(ctx: RunContext, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Clear mapped stage markers so delivery can re-enter. Does not soft-pass audit."""
    doc = plan or (
        ctx.read_json(REMUTATE_REL) if ctx.artifact_exists(REMUTATE_REL) else None
    )
    actions = set((doc or {}).get("actions") or []) if isinstance(doc, dict) else set()
    # Metadata-only plan/chapter align never needs timeline reopen or seat unfreeze.
    if actions and actions.issubset(_METADATA_ALIGN_ACTIONS):
        host = apply_edl_narrative_host_repair(ctx)
        if _host_progress_notes(host):
            return _remutate_from_host_progress(host, extra_notes=["align_plan_metadata_only"])
        return {
            "ok": False,
            "reason": "align_plan_noop",
            "host_fixed": False,
            "notes": list(host.get("notes") or []) + ["align_plan_noop"],
            "cleared": list(host.get("cleared") or []),
            "from_stage": "edl_narrative_audit",
        }
    try:
        from interview_mux.timeline_reopen_meta_gate import (
            INTENT_NARRATIVE,
            decide_timeline_reopen,
        )

        gate = decide_timeline_reopen(
            ctx,
            intent=INTENT_NARRATIVE,
            detail={"plan_actions": list(actions)},
        )
        if not gate.get("allow"):
            # Host-repair-only path still attempted; stage clears refused
            host = apply_edl_narrative_host_repair(ctx)
            if _host_progress_notes(host):
                return _remutate_from_host_progress(
                    host, extra_notes=["timeline_reopen_refused"]
                )
            return {
                "ok": False,
                "reason": "refused_low_gain",
                "gate": gate,
                "host_fixed": False,
                "notes": list(host.get("notes") or []) + ["timeline_reopen_refused"],
                "cleared": list(host.get("cleared") or []),
                "from_stage": "edl_narrative_audit",
            }
    except Exception:
        # c8 fail-closed: host-repair only, no stage clears
        host = apply_edl_narrative_host_repair(ctx)
        if _host_progress_notes(host):
            return _remutate_from_host_progress(
                host, extra_notes=["timeline_reopen_fail_closed"]
            )
        return {
            "ok": False,
            "reason": "refused_low_gain",
            "gate": {"allow": False, "refuse_reason": "decide_error_fail_closed"},
            "host_fixed": False,
            "notes": list(host.get("notes") or []) + ["timeline_reopen_fail_closed"],
            "cleared": list(host.get("cleared") or []),
            "from_stage": "edl_narrative_audit",
        }
    host = apply_edl_narrative_host_repair(ctx)
    # Orientation / late-intro-reset / duplicate-adjacency / plan align are host-fixed.
    # Rewinding ranking recreates the same late welcome-back cluster.
    if _host_progress_notes(host):
        return _remutate_from_host_progress(host)
    if not isinstance(doc, dict) or doc.get("exhausted"):
        return {
            "ok": False,
            "reason": "exhausted_or_missing",
            "host_fixed": False,
            "notes": list(host.get("notes") or []),
            "cleared": list(host.get("cleared") or []),
            "from_stage": "edl_narrative_audit",
        }
    cleared: list[str] = list(host.get("cleared") or [])
    for sid in doc.get("from_stages") or []:
        marker = ctx.run_dir / ".stage_done" / str(sid)
        if marker.is_file():
            marker.unlink(missing_ok=True)
            cleared.append(str(sid))
    # Force a fresh audit after remutate.
    for sid in ("edl", "edl_narrative_audit"):
        marker = ctx.run_dir / ".stage_done" / sid
        if marker.is_file():
            marker.unlink(missing_ok=True)
            cleared.append(sid)
    ctx.log(
        f"edl_narrative remutate attempt {doc.get('attempt')}: "
        f"actions={doc.get('actions')} cleared={cleared[:8]}",
        level="warning",
        stage="edl_narrative_audit",
    )
    return {
        "ok": True,
        "cleared": cleared,
        "from_stage": resume_after_narrative_audit_fail(doc.get("from_stage")),
        "host_fixed": False,
        "notes": list(host.get("notes") or []),
    }
