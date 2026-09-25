"""Typed remutate actions for edl_narrative_audit fail (no verdict soft-pass)."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.run_context import RunContext

REMUTATE_REL = "mastering/edl_narrative_remutate.json"
MAX_ATTEMPTS = 2
HOST_REPAIR_PROGRESS_NOTES = frozenset(
    {
        # ENA S4: host_repair is metadata + freeze-safe transition shrink only.
        "dedupe_transitions_for_framing",
        "dedupe_transitions_by_adjacency",
        "repair_mid_sentence_transition_openers",
        "upgrade_fail_audit_after_clean_occupancy",
    }
)

# Metadata-only notes — useful, but must not claim host_fixed when continuity
# still needs a spoken-bridge repair (align_* used to short-circuit remutate).
METADATA_ONLY_PROGRESS_NOTES = frozenset(
    {
        "align_selection_chapters",
        "align_narrative_plan",
    }
)

# Driver overflow detect (full_auto) — chapter-cap prose. Classification uses
# align_plan needles instead of a separate soup path (ENA S5).
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
            # Chapter-cap / duplicate-title → metadata align (not ranking rewind).
            *CHAPTER_OVERFLOW_MARKERS,
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

# ENA S3 safest: never auto-clear ranking / transitions / VO. Re-audit only.
_ACTION_STAGES: dict[str, list[str]] = {
    "rerank": ["edl_narrative_audit"],
    "align_plan": ["edl_narrative_audit"],
    "transitions": ["edl_narrative_audit"],
    "rebase_gap_vo": ["edl_narrative_audit"],
    "drop_blank": ["edl_narrative_audit"],
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
                from interview_mux.open_shape_repair import apply_open_window_and_repair

                repaired_sel = apply_open_window_and_repair(
                    ctx,
                    sel_c,
                    repaired_sel,
                    mutation_class="narrative_metadata_align",
                    stage="edl_narrative_metadata_align",
                )
                repaired_sel = commit_selection_mutation(
                    ctx,
                    repaired_sel,
                    producer="edl_narrative_metadata_align",
                    stage_key="edl_narrative_audit",
                    checkpoint_mode="detect",
                    merge_from_disk=False,
                    write_committed=True,
                    mutation_class="narrative_metadata_align",
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
    # ENA S7: do not clear .stage_done markers (demote-or-refuse, no remutate thrash).
    # ENA S8: coverage bind is topic_coverage's job — not narrative metadata align.
    fixed = bool(CHAPTER_FIX_PROGRESS_NOTES.intersection(notes))
    return {
        "ok": fixed,
        "notes": notes,
        "cleared": cleared,
        "from_stage": "edl_narrative_audit",
        "host_fixed": fixed,
    }


def _repair_mid_sentence_transition_openers(ctx: RunContext) -> list[str]:
    """Freeze-safe: complete mid-sentence transition openers (lowercase starts).

    spoken_copy_guard fallback historically returned fragments like
    \"alone does not settle…\" which flagship audit marks selected_continuity_broken.
    Prefix with a listener-facing demonstrative under transition_repair.
    """
    from interview_mux.artifact_ownership import freeze_write_allowed

    if not freeze_write_allowed(ctx, "transitions", "transition_repair"):
        return []
    if not ctx.artifact_exists("master/transitions.json"):
        return []
    tr = ctx.read_json("master/transitions.json")
    if not isinstance(tr, dict):
        return []
    rows = list(tr.get("transitions") or [])
    changed = 0
    out_rows: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            out_rows.append(row)
            continue
        text = str(row.get("text") or "").strip()
        if not text or not text[:1].islower():
            out_rows.append(row)
            continue
        fixed_text = f"That {text}"
        new_row = dict(row)
        new_row["text"] = fixed_text
        guard = dict(new_row.get("spoken_copy_guard") or {})
        guard["action"] = "repair_mid_sentence_opener"
        new_row["spoken_copy_guard"] = guard
        out_rows.append(new_row)
        changed += 1
    if not changed:
        return []
    tr = dict(tr)
    tr["transitions"] = out_rows
    try:
        from interview_mux.transition_vo import persist_transitions_doc

        persist_transitions_doc(ctx, tr, stage_key="transitions")
    except Exception:
        ctx.write_json(
            "master/transitions.json",
            tr,
            stage_key="transitions",
            mutation_class="transition_repair",
        )
    return ["repair_mid_sentence_transition_openers"]


def _dedupe_framing_transitions_under_freeze(ctx: RunContext) -> list[str]:
    """Drop transition when required VO already covers the adjacency.

    Safe under seat freeze: touches transitions.json only (no VO/seat rewrite).
    """
    from interview_mux.artifact_ownership import freeze_write_allowed

    notes: list[str] = []
    notes.extend(_repair_mid_sentence_transition_openers(ctx))
    if not freeze_write_allowed(ctx, "transitions", "transition_dedupe"):
        if not notes:
            return ["freeze_blocked_transition_dedupe"]
        return notes
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
    """ENA S4: metadata align + freeze-safe transition shrink only.

    Does not rewrite VO, layup, air_script, or gap seats. Does not soft-pass
    the audit. Does not rewind ranking.
    """
    meta = apply_edl_narrative_metadata_align(ctx)
    notes: list[str] = list(meta.get("notes") or [])
    notes.extend(_dedupe_framing_transitions_under_freeze(ctx))
    try:
        prior = (
            ctx.read_json(REMUTATE_REL) if ctx.artifact_exists(REMUTATE_REL) else {}
        )
        if not isinstance(prior, dict):
            prior = {}
        # ENA S7: sticky exhausted — do not reset attempt counters for thrash re-entry.
        prior["host_repair"] = notes
        prior["s7_demote_or_refuse"] = True
        ctx.write_json(REMUTATE_REL, prior)
    except Exception:
        pass
    progress = bool(
        HOST_REPAIR_PROGRESS_NOTES.intersection(notes)
        or METADATA_ONLY_PROGRESS_NOTES.intersection(notes)
    )
    return {
        "ok": progress,
        "from_stage": "edl_narrative_audit",
        "notes": notes,
        "cleared": list(meta.get("cleared") or []),
        "host_fixed": progress,
    }



def _host_progress_notes(host: dict[str, Any] | None) -> set[str]:
    notes = (host or {}).get("notes") or []
    return HOST_REPAIR_PROGRESS_NOTES.intersection(notes)


def _metadata_progress_notes(host: dict[str, Any] | None) -> set[str]:
    notes = (host or {}).get("notes") or []
    return METADATA_ONLY_PROGRESS_NOTES.intersection(notes)


def _remutate_from_host_progress(host: dict[str, Any], *, extra_notes: list[str] | None = None) -> dict[str, Any]:
    notes = list(host.get("notes") or [])
    if extra_notes:
        notes.extend(extra_notes)
    # ENA S3: always re-pin at narrative audit — never rewind layup/VO.
    from_stage = "edl_narrative_audit"
    pin = resume_after_narrative_audit_fail(from_stage)
    return {
        "ok": True,
        "cleared": list(host.get("cleared") or []),
        "from_stage": pin,
        "host_fixed": True,
        "notes": notes,
        "reason": "host_metadata_or_vo_progress",
    }


def apply_edl_narrative_remutate(ctx: RunContext, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """ENA S7: demote-or-refuse — metadata align + audit demote; no marker clears.

    Kept as a callable for full_auto / driver entry points. Does not soft-pass
    audit and does not rewind stage markers.
    """
    from interview_mux.artifact_repairs import repair_edl_audit

    _ = plan  # plan retained for API compat; stages are no longer cleared
    host = apply_edl_narrative_host_repair(ctx)
    notes = list(host.get("notes") or []) + ["s7_demote_or_refuse"]
    audit: dict[str, Any] = {}
    if ctx.artifact_exists("master/edl_narrative_audit.json"):
        try:
            loaded = ctx.read_json("master/edl_narrative_audit.json")
            audit = loaded if isinstance(loaded, dict) else {}
        except Exception:
            audit = {}
    if audit:
        demoted, demote_notes = repair_edl_audit(ctx, audit)
        notes.extend(
            str(n.get("action") or n)
            for n in demote_notes
            if isinstance(n, (dict, str))
        )
        try:
            ctx.write_json(
                "master/edl_narrative_audit.json",
                demoted,
                stage_key="edl_narrative_audit",
                skip_handoff=True,
            )
        except Exception:
            pass
        still_fail = str(demoted.get("verdict") or "").strip().lower() == "fail"
        still_block = bool(effective_narrative_blocking_issues(ctx, demoted))
    else:
        still_fail = True
        still_block = True
    progress = bool(
        HOST_REPAIR_PROGRESS_NOTES.intersection(notes)
        or METADATA_ONLY_PROGRESS_NOTES.intersection(notes)
    )
    ctx.log(
        "edl_narrative remutate collapsed to demote-or-refuse "
        f"(fail={still_fail} block={still_block} notes={notes[:6]})",
        level="warning" if (still_fail or still_block) else "info",
        stage="edl_narrative_audit",
    )
    return {
        "ok": progress and not still_block,
        "cleared": [],
        "from_stage": "edl_narrative_audit",
        "host_fixed": progress and not still_block,
        "notes": notes,
        "reason": "s7_demote_or_refuse",
    }
