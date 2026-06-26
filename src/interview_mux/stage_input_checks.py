"""Deterministic stage-input validation before pipeline stages run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from interview_mux.gates import (
    check_disfluency_review_pending,
    check_g1_vo,
    check_transcript_review_pending,
    get_selected_flow,
)
from interview_mux.llm_preflight import run_preflight
from interview_mux.run_context import RunContext
from interview_mux.write_staging import all_pending_stages, staging_approval_hint


@dataclass(frozen=True)
class StageInputIssue:
    message: str
    remediation: str | None = None


class StageInputError(RuntimeError):
    """Raised when a stage cannot run because prerequisites are missing or blocked."""

    def __init__(self, stage_id: str, issues: list[StageInputIssue]) -> None:
        self.stage_id = stage_id
        self.issues = issues
        lines = [issue.message for issue in issues]
        fixes = [issue.remediation for issue in issues if issue.remediation]
        msg = f"Stage '{stage_id}' blocked — " + "; ".join(lines)
        if fixes:
            msg += "\nRemediation: " + " | ".join(fixes)
        super().__init__(msg)


def collect_stage_input_issues(ctx: RunContext, stage_id: str) -> list[StageInputIssue]:
    """Return actionable issues for a stage (empty list = ready to run)."""
    issues: list[StageInputIssue] = []
    issues.extend(_pending_write_approval_issues(ctx))
    checker = _STAGE_CHECKERS.get(stage_id)
    if checker is not None:
        issues.extend(checker(ctx))
    elif stage_id in _LLM_STAGES:
        for err in run_preflight(stage_id, ctx):
            issues.append(StageInputIssue(err, _llm_remediation(err)))
    return issues


def require_stage_inputs(ctx: RunContext, stage_id: str) -> None:
    """Raise StageInputError when prerequisites are not satisfied."""
    issues = collect_stage_input_issues(ctx, stage_id)
    if not issues:
        return
    from interview_mux.operator_trace import log_step

    log_step(
        f"Stage input check failed: {stage_id}",
        ctx=ctx,
        stage=stage_id,
        level="error",
        detail={
            "event": "stage_input_blocked",
            "issues": [issue.message for issue in issues],
            "remediation": [issue.remediation for issue in issues if issue.remediation],
        },
    )
    raise StageInputError(stage_id, issues)


def _pending_write_approval_issues(ctx: RunContext) -> list[StageInputIssue]:
    pending = all_pending_stages(ctx)
    if not pending:
        return []
    sid = pending[0]
    return [
        StageInputIssue(
            f"Write approval pending for stage '{sid}'",
            f"Open the write review modal for '{sid}' and choose Save & continue or Discard & re-run.",
        )
    ]


def _require_artifact(
    ctx: RunContext,
    rel: str,
    *,
    label: str | None = None,
    remediation: str | None = None,
) -> StageInputIssue | None:
    if ctx.artifact_exists(rel):
        return None
    hint = staging_approval_hint(ctx, rel)
    msg = f"Missing {label or rel}"
    fix = remediation or hint
    if hint and remediation:
        fix = f"{remediation} ({hint})"
    return StageInputIssue(msg, fix)


def _require_audio(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    if ctx.artifact_exists("preclean/isolated.wav"):
        return issues
    issue = _require_artifact(
        ctx,
        "ingest/normalized.wav",
        label="normalized interview audio",
        remediation="Run and approve the ingest stage.",
    )
    if issue:
        issues.append(issue)
    return issues


def _g0_issues(ctx: RunContext) -> list[StageInputIssue]:
    if not check_transcript_review_pending(ctx):
        return []
    return [
        StageInputIssue(
            "Transcript review (G0) is incomplete",
            "Open Transcript review in the GUI, correct ranked clips, then Complete transcript review.",
        )
    ]


def _g0_5_issues(ctx: RunContext) -> list[StageInputIssue]:
    if not check_disfluency_review_pending(ctx):
        return []
    return [
        StageInputIssue(
            "Disfluency review (G0.5) is incomplete",
            "Confirm or reject filler events in the Disfluency review panel, then complete review.",
        )
    ]


def _analysis_gate_issues(ctx: RunContext) -> list[StageInputIssue]:
    return _g0_issues(ctx) + _g0_5_issues(ctx)


def _check_source_acoustic_profile(ctx: RunContext) -> list[StageInputIssue]:
    issues = _analysis_gate_issues(ctx)
    issues.extend(_require_audio(ctx))
    issue = _require_artifact(
        ctx,
        "transcript/full.json",
        remediation="Run transcribe and complete G0 transcript review.",
    )
    if issue:
        issues.append(issue)
    return issues


def _check_interview_spine_build(ctx: RunContext) -> list[StageInputIssue]:
    issues = _analysis_gate_issues(ctx)
    issues.extend(_require_audio(ctx))
    for rel, remediation in (
        ("transcript/full.json", "Run transcribe and complete G0."),
        (
            "understanding/source_acoustic_profile.json",
            "Run source_acoustic_profile (stage 8) and approve its outputs.",
        ),
    ):
        issue = _require_artifact(ctx, rel, remediation=remediation)
        if issue:
            issues.append(issue)
    return issues


def _check_sonic_context_build(ctx: RunContext) -> list[StageInputIssue]:
    issues = _analysis_gate_issues(ctx)
    for rel, remediation in (
        ("understanding/content_brief.json", "Run content_context and content_brief_reanchor."),
        ("segments/manifest.json", "Run boundary_detection and segment_classification."),
        (
            "understanding/source_acoustic_profile.json",
            "Run source_acoustic_profile before sonic context.",
        ),
    ):
        issue = _require_artifact(ctx, rel, remediation=remediation)
        if issue:
            issues.append(issue)
    return issues


def _check_disfluency_extract(ctx: RunContext) -> list[StageInputIssue]:
    issues = _g0_issues(ctx)
    issues.extend(_require_audio(ctx))
    issue = _require_artifact(ctx, "transcript/full.json", remediation="Run transcribe first.")
    if issue:
        issues.append(issue)
    return issues


def _check_transcript_review_build(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    issues.extend(_require_audio(ctx))
    issue = _require_artifact(ctx, "transcript/full.json", remediation="Run transcribe first.")
    if issue:
        issues.append(issue)
    return issues


def _check_vo_ingest(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    issue = _require_artifact(ctx, "understanding/gap_report.json", remediation="Run optimal_questions.")
    if issue:
        issues.append(issue)
        return issues
    missing = check_g1_vo(ctx)
    if missing:
        issues.append(
            StageInputIssue(
                f"Missing VO pickup WAV(s) for: {missing}",
                f"Record files under vo_pickup/{{line_id}}.wav — see understanding/interviewer_script.txt.",
            )
        )
    return issues


def _check_assembly_preview(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    issues.extend(_require_audio(ctx))
    issue = _require_artifact(ctx, "flow_1_master/edl.json", remediation="Run edl_flow1.")
    if issue:
        issues.append(issue)
    return issues


def _check_mix_flow1(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    issues.extend(_require_audio(ctx))
    for rel, remediation in (
        ("flow_1_master/edl.json", "Run edl_flow1."),
        ("understanding/sound_design_plan.json", "Run sound_design_plan_flow1."),
    ):
        issue = _require_artifact(ctx, rel, remediation=remediation)
        if issue:
            issues.append(issue)
    return issues


def _check_master_flow1(ctx: RunContext) -> list[StageInputIssue]:
    issue = _require_artifact(
        ctx,
        "flow_1_master/assembly.wav",
        remediation="Run mix_flow1 and approve assembly.wav.",
    )
    return [issue] if issue else []


def _check_mmaudio_sfx_flow1(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    for rel, remediation in (
        ("understanding/sound_design_plan.json", "Run sound_design_plan_flow1."),
        ("sound_design/sfx_prompts.json", "Run sfx_prompt_craft and approve prompts."),
    ):
        issue = _require_artifact(ctx, rel, remediation=remediation)
        if issue:
            issues.append(issue)
    issue = _require_artifact(
        ctx,
        "flow_1_master/assembly_preview.wav",
        label="assembly preview WAV",
        remediation="Run assembly_preview and listen before SFX spend.",
    )
    if issue:
        issues.append(issue)
    return issues


def _check_mmaudio_sfx_flow2(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    for rel, remediation in (
        ("understanding/sound_design_plan.json", "Run sound_design_plan_flow2."),
        ("sound_design/sfx_prompts.json", "Run sfx_prompt_craft."),
        ("flow_2_highlights/selection.json", "Run highlight_selection."),
    ):
        issue = _require_artifact(ctx, rel, remediation=remediation)
        if issue:
            issues.append(issue)
    return issues


def _check_edl_flow1(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    for rel, remediation in (
        ("flow_1_master/selection.json", "Run full_master_ranking."),
        ("flow_1_master/transitions.json", "Run transitions."),
        ("understanding/gap_report.json", "Run optimal_questions."),
    ):
        issue = _require_artifact(ctx, rel, remediation=remediation)
        if issue:
            issues.append(issue)
    missing = check_g1_vo(ctx)
    if missing:
        issues.append(
            StageInputIssue(
                f"G1 VO pickup missing for: {missing}",
                "Record vo_pickup WAVs before building the EDL.",
            )
        )
    return issues


def _check_flow1_profile_gate(ctx: RunContext) -> list[StageInputIssue]:
    if get_selected_flow(ctx) != "flow1":
        return []
    if not ctx.artifact_exists("understanding/analysis_state.json"):
        return [
            StageInputIssue(
                "analysis_state.json missing",
                "Complete analysis through optimal_questions.",
            )
        ]
    state = ctx.read_json("understanding/analysis_state.json")
    meta = state.get("meta") if isinstance(state, dict) else {}
    if isinstance(meta, dict) and meta.get("operator_verified"):
        return []
    return [
        StageInputIssue(
            "Interview profile not operator-verified",
            "Open Interview profile in the GUI and Mark verified before Flow 1 extended stages.",
        )
    ]


def _check_topic_coverage_audit(ctx: RunContext) -> list[StageInputIssue]:
    return _check_flow1_profile_gate(ctx)


def _llm_remediation(error: str) -> str | None:
    low = error.lower()
    if "g0" in low or "transcript review" in low:
        return "Complete G0 transcript review in the GUI."
    if "interview_spine" in low:
        return "Run interview_spine_build and approve outputs."
    if "interviewer" in low:
        return "Re-run speaker_roles or edit understanding/speakers.json."
    if "boundaries" in low:
        return "Re-run boundary_detection."
    if "manifest" in low:
        return "Re-run segment_classification."
    if "content_brief" in low or "thesis" in low:
        return "Re-run content_context or content_brief_reanchor."
    if "gap_evaluations" in low:
        return "Re-run missing_framing."
    if "operator_verified" in low or "profile" in low:
        return "Mark the interview profile verified in the GUI."
    if "sdp" in low or "sound_design_plan" in low:
        return "Re-run sound design plan stages."
    if "sfx_prompts" in low:
        return "Run sfx_prompt_craft and approve prompts."
    return None


_LLM_STAGES = frozenset(
    {
        "speaker_roles",
        "content_context",
        "boundary_detection",
        "segment_classification",
        "content_brief_reanchor",
        "sound_design_palettes",
        "missing_framing",
        "optimal_questions",
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "highlight_selection",
        "transitions",
        "sound_design_plan_flow1",
        "sound_design_plan_flow2",
        "sfx_prompt_craft",
        "edl_narrative_audit",
        "podcast_show_description",
    }
)

_STAGE_CHECKERS: dict[str, Callable[[RunContext], list[StageInputIssue]]] = {
    "transcript_review_build": _check_transcript_review_build,
    "disfluency_extract": _check_disfluency_extract,
    "source_acoustic_profile": _check_source_acoustic_profile,
    "interview_spine_build": _check_interview_spine_build,
    "sonic_context_build": _check_sonic_context_build,
    "vo_ingest": _check_vo_ingest,
    "topic_coverage_audit": _check_topic_coverage_audit,
    "assembly_preview": _check_assembly_preview,
    "mix_flow1": _check_mix_flow1,
    "master_flow1": _check_master_flow1,
    "mmaudio_sfx_flow1": _check_mmaudio_sfx_flow1,
    "mmaudio_sfx_flow2": _check_mmaudio_sfx_flow2,
    "edl_flow1": _check_edl_flow1,
}
