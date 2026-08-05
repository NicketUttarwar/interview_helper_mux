"""Bounded identify-all -> fix-all recovery for final-master failures.

At most two *full* remediation runs are allowed.  Each run inventories every
currently visible broken piece before planning or applying any repair.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.write_staging import write_committed_json

FAILURE_REVIEW_REL = "master/failure_review.json"
REMEDIATION_PLAN_REL = "master/remediation_plan.json"
REMEDIATION_LOG_REL = "master/remediation_run_log.json"
LEARNING_REL = "remediation_learning.jsonl"
MAX_REMEDIATION_RUNS = 2

SUPPORTED_ACTIONS = frozenset(
    {
        "resnip_earlier",
        "resnip_later",
        "merge_micro",
        "exclude_micro",
        "rebuild_synthetic_plan",
        "rewrite_vo_line",
        "retarget_music_region",
        "fix_music_fade",
        "regen_sfx",
        "reorder_pair",
        "restore_native_setup",
        "rebuild_edl",
        "remaster_mix",
        "rerun_from_stage",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def recovery_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    master = (cfg or merged_config()).get("mastering") or {}
    block = master.get("remediation") if isinstance(master.get("remediation"), dict) else {}
    defaults = {
        "enabled": True,
        "auto_execute": True,
        "max_runs": MAX_REMEDIATION_RUNS,
        "learning_log_enabled": True,
        "use_llm_planner": True,
    }
    out = {**defaults, **block}
    out["max_runs"] = min(MAX_REMEDIATION_RUNS, max(0, int(out.get("max_runs") or 0)))
    return out


def _piece(
    *,
    piece_id: str,
    kind: str,
    owning_stage: str,
    target_ids: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
    listener_impact: str,
    severity: str = "critical",
) -> dict[str, Any]:
    return {
        "piece_id": piece_id,
        "kind": kind,
        "severity": severity,
        "owning_stage": owning_stage,
        "target_ids": target_ids or [],
        "evidence": evidence or {},
        "listener_impact": listener_impact,
    }


def identify_all_failures(
    ctx: RunContext,
    *,
    trigger: str,
    trigger_detail: dict[str, Any] | None = None,
    snip_report: dict[str, Any] | None = None,
    autopsy: dict[str, Any] | None = None,
    run_index: int,
) -> dict[str, Any]:
    """Inventory all visible issues before any fix is attempted."""
    pieces: list[dict[str, Any]] = []
    report = snip_report if isinstance(snip_report, dict) else (
        ctx.read_json("master/junction_snip_qa.json")
        if ctx.artifact_exists("master/junction_snip_qa.json")
        else {}
    )
    for i, finding in enumerate(report.get("findings") or []):
        if not isinstance(finding, dict):
            continue
        severity = str(finding.get("severity") or "warn")
        if severity not in {"critical", "error", "warn"}:
            continue
        kind = str(finding.get("kind") or "junction")
        sid = str(finding.get("segment_id") or "")
        owning = "music_placement" if "music" in kind else (
            "synthetic_framing" if kind.startswith("vo_") else "segmentation"
        )
        pieces.append(
            _piece(
                piece_id=f"junction:{i}:{kind}:{sid}",
                kind=kind,
                owning_stage=owning,
                target_ids=[sid] if sid else [],
                evidence={
                    "action": finding.get("action"),
                    "detail": finding.get("detail") or {},
                    "text": finding.get("evidence"),
                },
                listener_impact=(
                    "chopped_music"
                    if "music" in kind
                    else ("vo_slam" if kind.startswith("vo_") else "mid_thought")
                ),
                severity=severity,
            )
        )

    auto = autopsy if isinstance(autopsy, dict) else (
        ctx.read_json("master/seam_autopsy.json")
        if ctx.artifact_exists("master/seam_autopsy.json")
        else {}
    )
    for reason in (auto.get("commitment") or {}).get("reasons") or []:
        pieces.append(
            _piece(
                piece_id=f"commitment:{reason}",
                kind=str(reason),
                owning_stage="junction_snip_qa",
                evidence={"commitment": auto.get("commitment")},
                listener_impact="uncommitted_audio",
            )
        )
    for conflict in auto.get("pack_conflicts") or []:
        if isinstance(conflict, dict):
            pieces.append(
                _piece(
                    piece_id=f"pack:{conflict.get('action')}:{conflict.get('count')}",
                    kind="plan_pack_conflict",
                    owning_stage="full_master_ranking",
                    target_ids=[str(x) for x in (conflict.get("ids") or []) if x],
                    evidence=conflict,
                    listener_impact="editorial_reexpansion",
                )
            )

    if ctx.artifact_exists("segments/boundaries.json"):
        boundaries = ctx.read_json("segments/boundaries.json")
        for i, warning in enumerate((boundaries or {}).get("warnings") or []):
            text = str(warning)
            if "coarse" in text.lower() or "mid-sentence" in text.lower():
                pieces.append(
                    _piece(
                        piece_id=f"boundaries:{i}",
                        kind="coarse_segmentation",
                        owning_stage="boundary_detection",
                        evidence={"warning": text},
                        listener_impact="mid_thought",
                    )
                )

    if ctx.artifact_exists("understanding/sound_design_plan.json") and ctx.artifact_exists(
        "master/selection.json"
    ):
        sdp = ctx.read_json("understanding/sound_design_plan.json")
        selection = ctx.read_json("master/selection.json")
        ordered = [str(x) for x in (selection.get("ordered_segment_ids") or []) if x]
        cues = (((sdp.get("flow_plans") or {}).get("podcast") or {}).get("cues") or [])
        for cue in cues:
            if not isinstance(cue, dict) or str(cue.get("role") or "") != "theme_outro":
                continue
            anchor = str(cue.get("after_segment_id") or "")
            if ordered and anchor != ordered[-1]:
                pieces.append(
                    _piece(
                        piece_id=f"music:outro:{cue.get('cue_id')}",
                        kind="outro_misplaced",
                        owning_stage="sound_design_plan",
                        target_ids=[anchor] if anchor else [],
                        evidence={"cue": cue, "expected_after_segment_id": ordered[-1]},
                        listener_impact="chopped_music",
                    )
                )

    # Stable de-duplication, preserving the first (richest) occurrence.
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in pieces:
        key = str(row.get("piece_id") or "")
        if key and key not in seen:
            seen.add(key)
            deduped.append(row)
    review = {
        "version": 1,
        "generated_at": _now(),
        "run_index": run_index,
        "trigger": trigger,
        "trigger_detail": trigger_detail or {},
        "failed_check": trigger,
        "severity": "critical" if deduped else "pass",
        "broken_pieces": deduped,
        "piece_count": len(deduped),
        "listener_impacts": sorted({str(x.get("listener_impact")) for x in deduped}),
        "complete_inventory": True,
    }
    # Failure evidence must survive even when the owning stage hard-stops before
    # normal staging flush; otherwise the operator sees an error with no review.
    write_committed_json(ctx, FAILURE_REVIEW_REL, review)
    return review


def _default_action(piece: dict[str, Any]) -> dict[str, Any]:
    kind = str(piece.get("kind") or "")
    evidence = piece.get("evidence") if isinstance(piece.get("evidence"), dict) else {}
    finding_action = str(evidence.get("action") or "")
    action_type = {
        "exclude_micro": "exclude_micro",
        "merge_micro": "merge_micro",
        "extend_later": "resnip_later",
        "cut_earlier": "resnip_earlier",
        "nudge_source_bounds": "resnip_later",
        "adjust_music_fade": "fix_music_fade",
        "insert_impact_hold": "restore_native_setup",
    }.get(finding_action)
    if not action_type:
        if kind == "coarse_segmentation":
            action_type = "rerun_from_stage"
        elif "music" in kind or kind == "outro_misplaced":
            action_type = "retarget_music_region"
        elif kind.startswith("vo_"):
            action_type = "rebuild_synthetic_plan"
        elif "commit" in kind or "drift" in kind:
            action_type = "rebuild_edl"
        elif kind == "plan_pack_conflict":
            action_type = "rerun_from_stage"
        else:
            action_type = "resnip_later"
    return {
        "action_id": f"fix:{piece.get('piece_id')}",
        "piece_id": piece.get("piece_id"),
        "action_type": action_type,
        "target_ids": piece.get("target_ids") or [],
        "params": {
            "finding_action": finding_action,
            "detail": evidence.get("detail") or {},
            "reentry_stage": (
                "boundary_detection"
                if kind == "coarse_segmentation"
                else ("full_master_ranking" if kind == "plan_pack_conflict" else "junction_snip_qa")
            ),
        },
        "rationale": f"Resolve {kind} for listener impact {piece.get('listener_impact')}",
        "expected_listen_gain": 0.2,
        "depends_on": [],
        "idempotent": True,
    }


def load_learning_hints(ctx: RunContext, *, limit: int = 50) -> list[dict[str, Any]]:
    """Load recent remediation learning rows, preferring same source_audio_hash."""
    path = ctx.assets_root / LEARNING_REL
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-max(1, limit * 4) :]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    source_hash = str((meta or {}).get("source_audio_hash") or "") if isinstance(meta, dict) else ""
    if source_hash:
        matched = [r for r in rows if str(r.get("source_audio_hash") or "") == source_hash]
        if matched:
            rows = matched
    return rows[-limit:]


def _bias_action_from_hints(
    action: dict[str, Any],
    piece: dict[str, Any],
    hints: list[dict[str, Any]],
) -> dict[str, Any]:
    kind = str(piece.get("kind") or "")
    if not kind or not hints:
        return action
    # Prefer action_types that succeeded for the same failure_code historically.
    votes: dict[str, int] = {}
    stage_votes: dict[str, int] = {}
    for h in hints:
        codes = {str(c) for c in (h.get("failure_codes") or []) if c}
        if kind not in codes and kind not in {str(c) for c in (h.get("actions_executed") or [])}:
            # Still use succeeded runs with overlapping codes.
            if not codes:
                continue
        if not h.get("succeeded"):
            continue
        for a in h.get("actions_executed") or []:
            votes[str(a)] = votes.get(str(a), 0) + 1
        # Some learning rows may store preferred reentry.
        reentry = h.get("reentry_stage")
        if reentry:
            stage_votes[str(reentry)] = stage_votes.get(str(reentry), 0) + 1
    if votes:
        best = max(votes.items(), key=lambda kv: kv[1])[0]
        # Map historical finding actions / remediation verbs onto action_type.
        mapped = {
            "exclude_micro": "exclude_micro",
            "merge_micro": "merge_micro",
            "extend_later": "resnip_later",
            "cut_earlier": "resnip_earlier",
            "resnip_later": "resnip_later",
            "resnip_earlier": "resnip_earlier",
            "fix_music_fade": "fix_music_fade",
            "adjust_music_fade": "fix_music_fade",
        }.get(best)
        if mapped and mapped in SUPPORTED_ACTIONS:
            action = dict(action)
            action["action_type"] = mapped
            action["rationale"] = (
                str(action.get("rationale") or "") + f" (learning bias → {mapped})"
            ).strip()
            params = dict(action.get("params") or {})
            params["learning_bias"] = best
            action["params"] = params
    if stage_votes:
        best_stage = max(stage_votes.items(), key=lambda kv: kv[1])[0]
        action = dict(action)
        params = dict(action.get("params") or {})
        params["reentry_stage"] = best_stage
        action["params"] = params
    return action


def plan_all_fixes(ctx: RunContext, review: dict[str, Any]) -> dict[str, Any]:
    """Build one plan that covers every broken piece in the inventory."""
    hints = load_learning_hints(ctx, limit=50)
    actions = []
    for p in review.get("broken_pieces") or []:
        if not isinstance(p, dict):
            continue
        action = _default_action(p)
        actions.append(_bias_action_from_hints(action, p, hints))
    plan = {
        "version": 1,
        "generated_at": _now(),
        "run_index": int(review.get("run_index") or 1),
        "goal": "Restore harmonious flow, comprehension, committed edits, and publishable quality.",
        "source_review_piece_count": len(review.get("broken_pieces") or []),
        "actions": actions,
        "execution_order": [str(a["action_id"]) for a in actions],
        "reentry_stage": min(
            (
                str((a.get("params") or {}).get("reentry_stage") or "junction_snip_qa")
                for a in actions
            ),
            key=lambda s: (
                "boundary_detection",
                "full_master_ranking",
                "junction_snip_qa",
            ).index(s)
            if s in {"boundary_detection", "full_master_ranking", "junction_snip_qa"}
            else 99,
            default="junction_snip_qa",
        ),
        "covers_all_pieces": len(actions) == len(review.get("broken_pieces") or []),
        "planner": "deterministic_complete_inventory",
        "learning_hints_used": len(hints),
    }
    write_committed_json(ctx, REMEDIATION_PLAN_REL, plan)
    return plan


def append_learning(ctx: RunContext, row: dict[str, Any]) -> None:
    """Append one remediation outcome to the durable ASSETS learning log."""
    if not recovery_cfg().get("learning_log_enabled", True):
        return
    path = ctx.assets_root / LEARNING_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


# Back-compat for callers/tests that imported the private name.
_append_learning = append_learning


def run_full_remediation(
    ctx: RunContext,
    *,
    trigger: str,
    identify: Callable[[int], dict[str, Any]],
    execute: Callable[[dict[str, Any], int], dict[str, Any]],
) -> dict[str, Any]:
    """Run at most two identify-all -> fix-all batches.

    The caller supplies domain-specific identification and execution so this
    orchestrator can be reused by junction, music, and publish quality.
    """
    cfg = recovery_cfg()
    max_runs = min(MAX_REMEDIATION_RUNS, int(cfg.get("max_runs") or 0))
    history: list[dict[str, Any]] = []
    final_review: dict[str, Any] = {}
    for run_index in range(1, max_runs + 1):
        review = identify(run_index)
        final_review = review
        pieces = [p for p in (review.get("broken_pieces") or []) if isinstance(p, dict)]
        if not pieces:
            break
        plan = plan_all_fixes(ctx, review)
        if not plan.get("covers_all_pieces"):
            raise RuntimeError("remediation plan did not cover the complete failure inventory")
        result = execute(plan, run_index)
        row = {
            "run_index": run_index,
            "trigger": trigger,
            "pieces_targeted": len(pieces),
            "pieces_resolved": int(result.get("pieces_resolved") or 0),
            "actions_executed": result.get("actions_executed") or [],
            "completed_at": _now(),
        }
        history.append(row)
        write_committed_json(
            ctx,
            REMEDIATION_LOG_REL,
            {
                "version": 1,
                "max_runs": MAX_REMEDIATION_RUNS,
                "runs": history,
                "runs_used": len(history),
                "third_run_forbidden": True,
            },
        )
        _append_learning(
            ctx,
            {
                "execution_id": ctx.run_id,
                **row,
                "failure_codes": sorted({str(p.get("kind") or "") for p in pieces}),
                "succeeded": int(result.get("pieces_resolved") or 0) >= len(pieces),
            },
        )
    return {
        "clean": not bool(final_review.get("broken_pieces")),
        "runs_used": len(history),
        "max_runs": MAX_REMEDIATION_RUNS,
        "history": history,
        "final_review": final_review,
    }


def record_loud_failure(
    ctx: RunContext,
    *,
    stage: str,
    reason: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Best-effort structured record for hard stops outside a recovery loop."""
    try:
        identify_all_failures(
            ctx,
            trigger=reason,
            trigger_detail={"stage": stage, **(detail or {})},
            run_index=0,
        )
    except Exception as exc:
        ctx.log(
            f"failure review recording failed: {exc}",
            level="warning",
            stage=stage,
            detail={"original_reason": reason},
        )
