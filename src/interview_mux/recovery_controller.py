"""Product recovery controller — one typed playbook per (stage, signature).

Not an e2e waiver layer. Playbooks produce a legal artifact or escalate.
Budget: at most one attempt per signature per run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

RECOVERY_LOG_REL = "operator/recovery_actions.jsonl"

# Explicit consumer → producer for fingerprint restamp (never guess).
FINGERPRINT_PRODUCER_BY_CONSUMER: dict[str, str] = {
    "sonic_context_build": "content_brief_reanchor",
    "topic_coverage_audit": "content_brief_reanchor",
}


@dataclass
class RecoveryResult:
    status: str  # recovered | escalate
    playbook_id: str
    signature: str
    resume_stage: str
    artifacts_written: list[str] = field(default_factory=list)
    detail: str = ""


def classify_error_class(stage_id: str, exc: BaseException) -> str | None:
    """Map a stage exception to a closed error_class (no fuzzy driver substrings)."""
    msg = str(exc).lower()
    stage = str(stage_id or "")
    if stage == "ideal_cuts_materialize" and (
        "no valid cuts after snap" in msg or "bind_mode requires boundaries" in msg
    ):
        return "empty_snap"
    if stage in {"nugget_layup_compose", "gap_framing_recompose"} and (
        "layup_coverage" in msg
        or "min_layup_coverage" in msg
        or "nugget layup qc failed" in msg
        or "nugget_layup_qc_failed" in msg
        or "layup authority" in msg
    ):
        return "layup_coverage"
    if stage == "edl" and "targets_segment_id" in msg and "does not match gap_report" in msg:
        return "orientation_target_mismatch"
    if stage in {"edl", "mix", "junction_snip_qa", "master_finalize"} and (
        "naked seam" in msg or "naked_seam" in msg
    ):
        return "naked_seam"
    if stage in {"mix", "mmaudio_sfx"} and "mmaudio_qa" in msg:
        return "mmaudio_qa_missing"
    if stage in {"master_finalize", "mix"} and (
        "episode_close_outro" in msg or "missing_episode_close_outro" in msg
    ):
        return "episode_close_outro"
    if stage in {"edl", "g1_vo", "g1_vo_pickup"} and (
        "g1 vo pickup missing" in msg or "stale_or_missing_pickup" in msg
    ):
        return "missing_g1_pickup"
    if "fingerprint mismatch" in msg:
        return "fingerprint_mismatch"
    return None


def signature_key(stage_id: str, error_class: str) -> str:
    return f"{stage_id}:{error_class}"


def _log_path(ctx: RunContext) -> Path:
    dest = Path(ctx.run_dir) / RECOVERY_LOG_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def _read_actions(ctx: RunContext) -> list[dict[str, Any]]:
    path = _log_path(ctx)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _append_action(ctx: RunContext, row: dict[str, Any]) -> None:
    path = _log_path(ctx)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def already_attempted(ctx: RunContext, signature: str) -> bool:
    for row in _read_actions(ctx):
        if str(row.get("signature") or "") == signature:
            return True
    return False


def _result(
    *,
    status: str,
    playbook_id: str,
    signature: str,
    resume_stage: str,
    artifacts: list[str] | None = None,
    detail: str = "",
) -> RecoveryResult:
    return RecoveryResult(
        status=status,
        playbook_id=playbook_id,
        signature=signature,
        resume_stage=resume_stage,
        artifacts_written=list(artifacts or []),
        detail=detail,
    )


def playbook_stamp_valueless_skips(ctx: RunContext) -> list[str]:
    from interview_mux.nugget_layup import (
        PLAN_REL,
        prepare_layup_plan_for_persist,
        publish_layup_plan_to_gap_report,
        stamp_valueless_skips,
    )

    if not ctx.artifact_exists(PLAN_REL):
        return []
    plan = ctx.read_json(PLAN_REL)
    plan, notes = stamp_valueless_skips(ctx, plan if isinstance(plan, dict) else {})
    plan = prepare_layup_plan_for_persist(ctx, plan)
    ctx.write_json(PLAN_REL, plan, stage_key="nugget_layup_compose")
    publish_layup_plan_to_gap_report(ctx, plan)
    return [PLAN_REL] if notes else []


def playbook_orientation_retarget(ctx: RunContext) -> list[str]:
    from interview_mux.opening_orientation import retarget_orientation_to_open

    return retarget_orientation_to_open(ctx)


def playbook_place_episode_close(ctx: RunContext) -> list[str]:
    from interview_mux.listen_quality import place_episode_close_cue

    return place_episode_close_cue(ctx)


def playbook_ensure_mmaudio_qa(ctx: RunContext) -> list[str]:
    from interview_mux.delivery_recovery import ensure_mmaudio_qa_before_mix

    state = ensure_mmaudio_qa_before_mix(ctx, run_if_missing=True)
    if state.get("ok"):
        return [str(state.get("path") or "sound_design/mmaudio_qa.json")]
    return []


def playbook_ensure_g1(ctx: RunContext) -> list[str]:
    from interview_mux.delivery_recovery import ensure_g1_pickups

    result = ensure_g1_pickups(ctx)
    if isinstance(result, dict) and result.get("ok"):
        return list(result.get("synthesized") or []) or ["vo_pickup"]
    return []


def playbook_mint_reorder_glue(ctx: RunContext) -> list[str]:
    from interview_mux.seam_glue import ensure_seam_glue

    selection = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else {}
    )
    ordered = [
        str(s)
        for s in ((selection or {}).get("ordered_segment_ids") or [])
        if s
    ]
    if not ordered:
        return []
    manifest = (
        ctx.read_json("segments/manifest.json")
        if ctx.artifact_exists("segments/manifest.json")
        else {}
    )
    by_id = {
        str(s.get("segment_id") or ""): s
        for s in ((manifest or {}).get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }
    gap = (
        ctx.read_json("understanding/gap_report.json")
        if ctx.artifact_exists("understanding/gap_report.json")
        else None
    )
    transitions = (
        ctx.read_json("master/transitions.json")
        if ctx.artifact_exists("master/transitions.json")
        else {"transitions": []}
    )
    _bridges, transitions_doc, completeness = ensure_seam_glue(
        ctx,
        ordered=ordered,
        segments_by_id=by_id,
        gap_report=gap if isinstance(gap, dict) else None,
        transitions=transitions if isinstance(transitions, dict) else None,
        soft=False,
    )
    written = ["master/bridge_completeness.json"]
    if isinstance(transitions_doc, dict):
        ctx.write_json("master/transitions.json", transitions_doc)
        written.append("master/transitions.json")
    if isinstance(completeness, dict) and not completeness.get("complete"):
        return []
    return written


def handle_stage_failure(
    ctx: RunContext,
    stage_id: str,
    exc: BaseException,
) -> RecoveryResult:
    """Run at most one playbook for this signature, then recovered or escalate."""
    error_class = classify_error_class(stage_id, exc)
    if not error_class:
        return _result(
            status="escalate",
            playbook_id="none",
            signature=signature_key(stage_id, "unknown"),
            resume_stage=stage_id,
            detail="no_matching_playbook",
        )
    sig = signature_key(stage_id, error_class)
    if already_attempted(ctx, sig):
        result = _result(
            status="escalate",
            playbook_id="budget_exhausted",
            signature=sig,
            resume_stage=stage_id,
            detail="already_attempted",
        )
        _append_action(
            ctx,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "signature": sig,
                "playbook_id": result.playbook_id,
                "status": result.status,
                "detail": result.detail,
            },
        )
        return result

    playbook_id = error_class
    artifacts: list[str] = []
    recovered = False
    detail = ""
    resume_stage = stage_id
    try:
        if error_class == "empty_snap":
            playbook_id = "cuts_empty_snap_demote"
            from interview_mux.ideal_cuts import MATERIALIZED_REL, run_ideal_cuts_materialize

            # In-stage demote writes materialized without raising; re-run once.
            try:
                run_ideal_cuts_materialize(ctx)
            except Exception:
                pass
            recovered = ctx.artifact_exists(MATERIALIZED_REL)
        elif error_class == "layup_coverage":
            playbook_id = "stamp_valueless_skips"
            artifacts = playbook_stamp_valueless_skips(ctx)
            recovered = True
        elif error_class == "orientation_target_mismatch":
            playbook_id = "orientation_retarget_open"
            artifacts = playbook_orientation_retarget(ctx)
            recovered = True
        elif error_class == "naked_seam":
            playbook_id = "seam_mint_reorder"
            artifacts = playbook_mint_reorder_glue(ctx)
            recovered = bool(artifacts)
        elif error_class == "mmaudio_qa_missing":
            playbook_id = "ensure_mmaudio_qa"
            artifacts = playbook_ensure_mmaudio_qa(ctx)
            recovered = bool(artifacts)
        elif error_class == "episode_close_outro":
            playbook_id = "place_episode_close_cue"
            artifacts = playbook_place_episode_close(ctx)
            recovered = bool(artifacts)
            if recovered:
                resume_stage = "mix"
        elif error_class == "missing_g1_pickup":
            playbook_id = "ensure_g1_pickups"
            artifacts = playbook_ensure_g1(ctx)
            recovered = bool(artifacts)
        elif error_class == "fingerprint_mismatch":
            playbook_id = "fingerprint_restamp_or_rerun"
            producer = FINGERPRINT_PRODUCER_BY_CONSUMER.get(stage_id)
            recovered = bool(producer)
            detail = producer or "no_mapped_producer"
            if producer:
                resume_stage = producer
        else:
            recovered = False
            detail = "unhandled_class"
    except Exception as play_exc:
        recovered = False
        detail = str(play_exc)[:240]

    result = _result(
        status="recovered" if recovered else "escalate",
        playbook_id=playbook_id,
        signature=sig,
        resume_stage=resume_stage,
        artifacts=artifacts,
        detail=detail,
    )
    _append_action(
        ctx,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signature": sig,
            "playbook_id": result.playbook_id,
            "status": result.status,
            "artifacts": result.artifacts_written,
            "detail": result.detail,
        },
    )
    return result
