"""Consolidated Flow 1 progression readiness — single report before LLM/audio spend."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from interview_mux.run_context import RunContext

Layer = Literal[
    "gate",
    "cross",
    "completeness",
    "preflight",
    "itr",
    "io",
    "schema",
    "sufficiency",
    "audio",
]

@dataclass(frozen=True)
class ProgressionBlocker:
    layer: str
    message: str
    id: str | None = None
    path: str | None = None
    json_pointer: str | None = None
    checkpoint: str | None = None
    status: str | None = None
    stage_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

def _gate_blockers(ctx: RunContext) -> list[ProgressionBlocker]:
    from interview_mux.gates import (
        check_disfluency_review_pending,
        check_g1_vo,
        check_transcript_review_pending,
    )

    out: list[ProgressionBlocker] = []
    if check_transcript_review_pending(ctx):
        out.append(
            ProgressionBlocker(
                layer="gate",
                id="g0_transcript_review",
                message="G0 transcript review pending — correct STT in the GUI before continuing.",
                stage_id="transcript_review",
            )
        )
    if check_disfluency_review_pending(ctx):
        out.append(
            ProgressionBlocker(
                layer="gate",
                id="g0_5_disfluency_review",
                message="G0.5 disfluency review pending — confirm filler events in the GUI.",
                stage_id="disfluency_review",
            )
        )
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

    if gap_fill_was_skipped(ctx):
        missing_vo: list[str] = []
    else:
        missing_vo = check_g1_vo(ctx)
    if missing_vo:
        out.append(
            ProgressionBlocker(
                layer="gate",
                id="g1_vo_pickup",
                message=f"G1 VO pickup missing for line(s): {', '.join(missing_vo[:6])}.",
                path="vo_pickup/",
                stage_id="g1_vo_pickup",
            )
        )
    if ctx.artifact_exists("understanding/analysis_state.json"):
        state = ctx.read_json("understanding/analysis_state.json")
        meta = state.get("meta") if isinstance(state, dict) else {}
        if not (isinstance(meta, dict) and meta.get("operator_verified")):
            out.append(
                ProgressionBlocker(
                    layer="gate",
                    id="profile_operator_verified",
                    message="Interview profile not operator-verified — mark verified in the GUI.",
                    path="understanding/analysis_state.json",
                    json_pointer="/meta/operator_verified",
                    stage_id="analysis_profile",
                )
            )
    return out

def _p0_spine_blockers(ctx: RunContext) -> list[ProgressionBlocker]:
    from interview_mux.artifact_completeness import artifact_status
    from interview_mux.llm_flow_hardening import producer_artifact_path
    from interview_mux.progression_spine import P0_ANALYSIS_SPINE

    out: list[ProgressionBlocker] = []
    for stage_id in P0_ANALYSIS_SPINE:
        rel = producer_artifact_path(stage_id)
        if not rel:
            continue
        st = artifact_status(rel, ctx)
        if st != "complete":
            out.append(
                ProgressionBlocker(
                    layer="completeness",
                    id=f"p0_spine_{stage_id}",
                    stage_id=stage_id,
                    path=rel,
                    status=st,
                    message=f"P0 spine incomplete: {stage_id} ({rel} is {st}).",
                )
            )
            break
    return out

def _cross_blockers(ctx: RunContext, checkpoint: str) -> list[ProgressionBlocker]:
    from interview_mux.artifact_cross_validate import validate_cross_artifacts

    errors = validate_cross_artifacts(ctx, checkpoint)
    return [
        ProgressionBlocker(
            layer="cross",
            checkpoint=checkpoint,
            message=err,
            json_pointer=_guess_pointer(err),
        )
        for err in errors[:12]
    ]

def _guess_pointer(error: str) -> str | None:
    low = error.lower()
    if "segment_id" in low and "topics" in low:
        return "/topics/*/segment_ids"
    if "thesis" in low:
        return "/thesis"
    if "manifest" in low:
        return "/segments"
    return None

def _analysis_complete_blocker(ctx: RunContext) -> ProgressionBlocker | None:
    if ctx.artifact_exists("analysis_complete.json"):
        return None
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
    from interview_mux.pipeline import shared_analysis_chain_complete

    if gap_fill_was_skipped(ctx):
        stage_id = "episode_structure_compose"
        if shared_analysis_chain_complete(ctx):
            message = (
                "Shared analysis not marked complete — finish Episode structure "
                "(or refresh the run after gap-fill skip)."
            )
        else:
            message = "Shared analysis not complete — finish remaining Analyze steps."
    else:
        stage_id = "optimal_questions"
        message = "Shared analysis not marked complete — finish optimal_questions or vo_ingest."
    return ProgressionBlocker(
        layer="completeness",
        id="analysis_complete",
        path="analysis_complete.json",
        message=message,
        stage_id=stage_id,
    )

def _flow1_spine_blockers(ctx: RunContext, *, through_stage: str | None = None) -> list[ProgressionBlocker]:
    from interview_mux.artifact_completeness import artifact_status
    from interview_mux.llm_flow_hardening import producer_artifact_path
    from interview_mux.progression_spine import P0_DELIVERY_SPINE, flow1_spine_through

    out: list[ProgressionBlocker] = []
    chain = flow1_spine_through(through_stage) if through_stage else P0_DELIVERY_SPINE
    for stage_id in chain:
        rel = producer_artifact_path(stage_id)
        if not rel:
            continue
        st = artifact_status(rel, ctx)
        if st != "complete":
            out.append(
                ProgressionBlocker(
                    layer="completeness",
                    id=f"flow1_spine_{stage_id}",
                    stage_id=stage_id,
                    path=rel,
                    status=st,
                    message=f"Flow 1 spine incomplete: {stage_id} ({rel} is {st}).",
                )
            )
            break
    return out

def _preflight_blockers(ctx: RunContext, stage_id: str) -> list[ProgressionBlocker]:
    from interview_mux.llm_preflight import run_preflight

    issues = run_preflight(stage_id, ctx)
    return [
        ProgressionBlocker(
            layer="preflight",
            stage_id=stage_id,
            message=issue if isinstance(issue, str) else str(issue),
        )
        for issue in issues[:8]
    ]

def _pending_write_blocker(ctx: RunContext) -> ProgressionBlocker | None:
    from interview_mux.write_staging import all_pending_stages

    stages = sorted(all_pending_stages(ctx))
    if not stages:
        return None
    return ProgressionBlocker(
        layer="io",
        id="pending_write_approval",
        message=f"Write approval pending for stage(s): {', '.join(stages[:4])}. Save staged outputs before continuing.",
        stage_id=stages[0],
    )

def build_delivery_readiness_report(
    ctx: RunContext,
    *,
    target_stage: str | None = "topic_coverage_audit",
    include_flow1_spine: bool = False,
) -> dict[str, Any]:
    """Structured readiness report before Flow 1 LLM spend."""
    blockers: list[ProgressionBlocker] = []
    blockers.extend(_gate_blockers(ctx))
    blockers.extend(_p0_spine_blockers(ctx))
    ac = _analysis_complete_blocker(ctx)
    if ac:
        blockers.append(ac)
    blockers.extend(_cross_blockers(ctx, "post_reanchor"))
    blockers.extend(_cross_blockers(ctx, "pre_delivery"))
    pending = _pending_write_blocker(ctx)
    if pending:
        blockers.append(pending)
    if include_flow1_spine and target_stage:
        blockers.extend(_flow1_spine_blockers(ctx, through_stage=target_stage))
    if target_stage:
        blockers.extend(_preflight_blockers(ctx, target_stage))

    # De-dupe by (layer, message)
    seen: set[tuple[str, str]] = set()
    unique: list[ProgressionBlocker] = []
    for b in blockers:
        key = (b.layer, b.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(b)

    return {
        "ready": len(unique) == 0,
        "target_stage": target_stage,
        "blockers": [b.to_dict() for b in unique],
    }

def build_pre_audio_readiness_report(ctx: RunContext) -> dict[str, Any]:
    """Readiness before mmaudio_sfx / mix spend."""
    from interview_mux.stage_input_checks import collect_stage_input_issues

    blockers: list[ProgressionBlocker] = []
    flow_report = build_delivery_readiness_report(
        ctx,
        target_stage="edl",
        include_flow1_spine=True,
    )
    for row in flow_report.get("blockers") or []:
        if isinstance(row, dict):
            blockers.append(ProgressionBlocker(**{k: row[k] for k in row if k in ProgressionBlocker.__dataclass_fields__}))

    for stage_id in ("mmaudio_sfx", "mix"):
        for issue in collect_stage_input_issues(ctx, stage_id):
            blockers.append(
                ProgressionBlocker(
                    layer="audio",
                    stage_id=stage_id,
                    message=issue.message,
                )
            )

    seen: set[tuple[str, str]] = set()
    unique: list[ProgressionBlocker] = []
    for b in blockers:
        key = (b.layer, b.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(b)

    return {
        "ready": len(unique) == 0,
        "blockers": [b.to_dict() for b in unique],
        "source_readiness": (
            __import__(
                "interview_mux.source_readiness", fromlist=["load_source_readiness"]
            ).load_source_readiness(ctx)
        ),
    }

def assert_delivery_ready(ctx: RunContext, *, target_stage: str = "topic_coverage_audit") -> None:
    report = build_delivery_readiness_report(ctx, target_stage=target_stage)
    if report["ready"]:
        return
    summary = "; ".join(
        str(b.get("message", "")) for b in (report.get("blockers") or [])[:4]
    )
    ctx.log(
        f"Flow 1 not ready: {summary}",
        level="error",
        stage=target_stage,
        detail={"readiness": report, "layer": "readiness"},
    )
    raise SystemExit(f"Flow 1 readiness gate: {summary}")

def log_blocker(ctx: RunContext, blocker: ProgressionBlocker, *, stage: str | None = None) -> None:
    """Emit operator-visible log with unified failure taxonomy."""
    ctx.log(
        blocker.message,
        level="warning",
        stage=stage or blocker.stage_id,
        detail=blocker.to_dict(),
    )
