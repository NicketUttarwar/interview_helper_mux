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
        "drop_stale_orientation_wav",
        "reseat_required_recovery_layup",
        "promoted_pending_layup_plan",
        "layup_repair",
        "seed_missing_seated_layup",
        "ensure_adjacency_transition",
    }
)

# Allowlisted issue → action classifiers (substring match on lowered text).
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

_ACTION_STAGES: dict[str, list[str]] = {
    "rerank": ["full_master_ranking", "edl_narrative_audit"],
    "transitions": ["transitions", "edl_narrative_audit"],
    "rebase_gap_vo": ["selection_framing_apply", "nugget_layup_compose", "edl_narrative_audit"],
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
            ctx.write_json("understanding/gap_report.json", gap)
    return notes, adjacencies


def classify_edl_narrative_issue(text: str) -> str:
    blob = str(text or "").strip().lower()
    if not blob:
        return "operator"
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
    for action, needles in _CLASSIFIERS:
        if action == "rebase_gap_vo":
            continue
        if any(n in blob for n in needles):
            return action
    return "operator"


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
        actions.append(classify_edl_narrative_issue(blob))
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
    attempt = int((prior or {}).get("attempt") or 0) + 1
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


def apply_edl_narrative_host_repair(ctx: RunContext) -> dict[str, Any]:
    """Rewrite unusable orientation/layup copy and keep one transition per adjacency.

    Does not rewind ranking or recompose layup. Does not soft-pass the audit.
    """
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
                ctx.write_json("master/transitions.json", tr)
                after = len(tr.get("transitions") or [])
                if after < before:
                    notes.append("dedupe_transitions_by_adjacency")
        except Exception as exc:
            notes.append(f"transitions:{exc}")
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
                ctx.write_json("master/transitions.json", tr)
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
    if "seed_missing_seated_layup" in notes:
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


def apply_edl_narrative_remutate(ctx: RunContext, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Clear mapped stage markers so delivery can re-enter. Does not soft-pass audit."""
    host = apply_edl_narrative_host_repair(ctx)
    doc = plan or (
        ctx.read_json(REMUTATE_REL) if ctx.artifact_exists(REMUTATE_REL) else None
    )
    actions = set((doc or {}).get("actions") or []) if isinstance(doc, dict) else set()
    vo_notes = HOST_REPAIR_PROGRESS_NOTES
    # Orientation / duplicate-adjacency / question-only layup are host-fixed.
    # Rewinding transitions or layup compose recreates the same defects.
    if vo_notes.intersection(host.get("notes") or []) and not (actions & {"rerank", "drop_blank"}):
        return {
            "ok": True,
            "cleared": host.get("cleared") or [],
            "from_stage": "edl_narrative_audit",
            "host_fixed": True,
            "notes": host.get("notes") or [],
        }
    if not isinstance(doc, dict) or doc.get("exhausted"):
        return {"ok": False, "reason": "exhausted_or_missing", **host}
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
    return {"ok": True, "cleared": cleared, "from_stage": doc.get("from_stage")}
