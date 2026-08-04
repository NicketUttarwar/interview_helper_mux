"""Deterministic stage-input validation before pipeline stages run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from interview_mux.gates import (
    check_g1_vo,
    check_transcript_review_pending,
    get_selected_flow,
)
from interview_mux.llm_preflight import run_preflight
from interview_mux.run_context import RunContext
from interview_mux.write_staging import (
    has_pending_writes,
    stages_with_pending_writes,
    staging_approval_hint,
)


@dataclass(frozen=True)
class StageInputIssue:
    message: str
    remediation: str | None = None
    kind: str = "prerequisite"
    related_stage: str | None = None


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

    @property
    def write_approval_only(self) -> bool:
        return bool(self.issues) and all(issue.kind == "write_approval" for issue in self.issues)

    @property
    def pending_write_stage(self) -> str | None:
        for issue in self.issues:
            if issue.kind == "write_approval":
                return issue.related_stage or self.stage_id
        return None


def collect_stage_input_issues(ctx: RunContext, stage_id: str) -> list[StageInputIssue]:
    """Return actionable issues for a stage (empty list = ready to run)."""
    issues: list[StageInputIssue] = []
    issues.extend(_pending_write_approval_issues(ctx, stage_id))
    checker = _STAGE_CHECKERS.get(stage_id)
    if checker is not None:
        issues.extend(checker(ctx))
    elif stage_id in _LLM_STAGES:
        for err in run_preflight(stage_id, ctx):
            issues.append(StageInputIssue(err, _llm_remediation(err, ctx)))
    return issues


def require_stage_inputs(ctx: RunContext, stage_id: str) -> None:
    """Raise StageInputError when prerequisites are not satisfied."""
    issues = collect_stage_input_issues(ctx, stage_id)
    if not issues:
        return
    from interview_mux.operator_trace import log_step

    # Operator/gate pauses — not pipeline crashes. Keep gui_log at warning.
    log_step(
        f"Stage input check blocked: {stage_id}",
        ctx=ctx,
        stage=stage_id,
        level="warning",
        detail={
            "event": "stage_input_blocked",
            "issues": [issue.message for issue in issues],
            "remediation": [issue.remediation for issue in issues if issue.remediation],
            "kinds": [issue.kind for issue in issues],
        },
    )
    raise StageInputError(stage_id, issues)


def _pending_write_approval_issues(ctx: RunContext, stage_id: str) -> list[StageInputIssue]:
    """Block only when write approval must pause execute for this stage.

    Under first-try ``defer_write_approval_until=phase_end``, other stages may
    keep staged files without blocking subsequent stages. Re-running a stage
    that still has its own pending writes remains blocked.
    """
    from interview_mux.first_try import write_approval_deferred
    from interview_mux.write_staging import write_approval_enabled

    if not write_approval_enabled():
        return []

    if write_approval_deferred():
        if not has_pending_writes(ctx, stage_id):
            return []
        return [
            StageInputIssue(
                f"Write approval pending for stage '{stage_id}'",
                f"Open the write review modal for '{stage_id}' and choose Save & continue or Discard & re-run.",
                kind="write_approval",
                related_stage=stage_id,
            )
        ]

    from interview_mux.write_staging import stages_with_pending_writes

    pending = stages_with_pending_writes(ctx)
    if not pending:
        return []
    sid = pending[0]
    return [
        StageInputIssue(
            f"Write approval pending for stage '{sid}'",
            f"Open the write review modal for '{sid}' and choose Save & continue or Discard & re-run.",
            kind="write_approval",
            related_stage=sid,
        )
    ]


def _require_artifact(
    ctx: RunContext,
    rel: str,
    *,
    label: str | None = None,
    remediation: str | None = None,
    require_complete: bool = False,
) -> StageInputIssue | None:
    must_be_complete = require_complete or rel in _UPSTREAM_ARTIFACT_PRODUCER
    if ctx.artifact_exists(rel):
        from interview_mux.artifact_lifecycle import lifecycle_cfg, read_stale_guard

        if lifecycle_cfg().get("read_stale_guard", True):
            consumer = getattr(ctx, "_lifecycle_consumer_stage", None) or "preflight"
            stale = read_stale_guard(ctx, rel, consumer_stage=str(consumer))
            if stale:
                return StageInputIssue(stale, remediation or f"Re-run upstream producer for {rel}.")
        if must_be_complete:
            from interview_mux.artifact_completeness import artifact_status

            st = artifact_status(rel, ctx)
            if st != "complete":
                fix = remediation or _remediation_for_missing_artifact(ctx, rel)
                return StageInputIssue(
                    f"{label or rel} is {st} (not complete)",
                    fix or f"Re-run upstream producer for {rel}.",
                )
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


def _analysis_gate_issues(ctx: RunContext) -> list[StageInputIssue]:
    return _g0_issues(ctx)


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
    issue = _require_artifact(ctx, "master/edl.json", remediation="Run edl.")
    if issue:
        issues.append(issue)
    return issues


def _check_mix(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    issues.extend(_require_audio(ctx))
    for rel, remediation in (
        ("master/edl.json", "Run edl."),
        ("understanding/sound_design_plan.json", "Run sound_design_plan."),
    ):
        issue = _require_artifact(ctx, rel, remediation=remediation)
        if issue:
            issues.append(issue)
    return issues


def _check_master_finalize(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    issue = _require_artifact(
        ctx,
        "master/assembly.wav",
        remediation="Run mix and approve assembly.wav.",
    )
    if issue:
        issues.append(issue)
    if ctx.artifact_exists("master/selection.json") and ctx.artifact_exists("master/edl.json"):
        from interview_mux.order_hash import order_hashes_match

        sel = ctx.read_json("master/selection.json")
        edl = ctx.read_json("master/edl.json")
        if isinstance(sel, dict) and isinstance(edl, dict) and not order_hashes_match(sel, edl):
            issues.append(
                StageInputIssue(
                    "selection order drifted from edl",
                    "Re-run edl after order changes, then mix before master_finalize.",
                )
            )
    if ctx.artifact_exists("master/assembly_ledger.json"):
        ledger = ctx.read_json("master/assembly_ledger.json")
        if isinstance(ledger, dict) and not ledger.get("complete", True):
            n = int(ledger.get("naked_seam_count") or 0)
            issues.append(
                StageInputIssue(
                    f"assembly_ledger has {n} naked seam(s)",
                    "Rebuild edl so every reorder join has audible VO/transition glue.",
                )
            )
    elif ctx.artifact_exists("master/edl.json"):
        issues.append(
            StageInputIssue(
                "master/assembly_ledger.json missing",
                "Re-run edl to emit the assembly ledger.",
            )
        )
    if ctx.artifact_exists("master/bridge_completeness.json"):
        bc = ctx.read_json("master/bridge_completeness.json")
        if isinstance(bc, dict) and not bc.get("complete", True):
            issues.append(
                StageInputIssue(
                    "bridge_completeness incomplete",
                    "Mint pair-specific transitions for reorder joins, then re-run edl.",
                )
            )
    return issues


def _check_mmaudio_sfx(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    for rel, remediation in (
        ("understanding/sound_design_plan.json", "Run sound_design_plan."),
        ("sound_design/sfx_prompts.json", "Run sfx_prompt_craft and approve prompts."),
    ):
        issue = _require_artifact(ctx, rel, remediation=remediation)
        if issue:
            issues.append(issue)
    issue = _require_artifact(
        ctx,
        "master/assembly_preview.wav",
        label="assembly preview WAV",
        remediation="Run assembly_preview and listen before SFX spend.",
    )
    if issue:
        issues.append(issue)
    return issues


def _check_edl(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    for rel, remediation in (
        ("master/selection.json", "Run full_master_ranking."),
        ("master/transitions.json", "Run transitions."),
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
    issues = _check_flow1_profile_gate(ctx)
    from interview_mux.progression_readiness import build_delivery_readiness_report

    report = build_delivery_readiness_report(ctx, target_stage="topic_coverage_audit")
    for row in report.get("blockers") or []:
        if isinstance(row, dict):
            issues.append(
                StageInputIssue(
                    str(row.get("message", "Flow 1 not ready")),
                    f"Layer: {row.get('layer', 'readiness')}",
                )
            )
    return issues


def _check_narrative_arc_plan(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    issues.extend(_check_flow1_profile_gate(ctx))
    for rel, remediation in (
        ("master/coverage_audit.json", "Run topic_coverage_audit."),
        ("understanding/content_brief.json", "Run content_context and content_brief_reanchor."),
    ):
        issue = _require_artifact(ctx, rel, remediation=remediation)
        if issue:
            issues.append(issue)
    return issues


def _check_full_master_ranking(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    issues.extend(_check_flow1_profile_gate(ctx))
    for rel, remediation in (
        ("master/narrative_plan.json", "Run narrative_arc_plan."),
        ("segments/manifest.json", "Run segment_classification."),
        ("understanding/gap_report.json", "Run optimal_questions."),
    ):
        issue = _require_artifact(ctx, rel, remediation=remediation)
        if issue:
            issues.append(issue)
    return issues


def _check_sound_design_plan(ctx: RunContext) -> list[StageInputIssue]:
    issues: list[StageInputIssue] = []
    for rel, remediation in (
        ("master/selection.json", "Run full_master_ranking."),
        ("master/transitions.json", "Run transitions."),
        ("understanding/gap_report.json", "Run optimal_questions."),
    ):
        issue = _require_artifact(ctx, rel, remediation=remediation)
        if issue:
            issues.append(issue)
    return issues


_UPSTREAM_ARTIFACT_PRODUCER: dict[str, str] = {
    "understanding/speakers.json": "speaker_roles",
    "understanding/content_brief.json": "content_context",
    "segments/boundaries.json": "boundary_detection",
    "segments/manifest.json": "segment_classification",
}


def _latest_stage_attempt_excerpt(ctx: RunContext, stage_id: str) -> str | None:
    audit_dir = ctx.path("understanding", "stage_runs", stage_id)
    if not audit_dir.is_dir():
        return None
    attempts = sorted(audit_dir.glob("attempt_*.json"))
    if not attempts:
        return None
    try:
        doc = ctx.read_json(str(attempts[-1].relative_to(ctx.run_dir)).replace("\\", "/"))
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    extra = doc.get("extra") or {}
    if isinstance(extra, dict):
        for key in ("schema_errors", "verification_errors", "blocked_paths"):
            val = extra.get(key)
            if val:
                return str(val)[:240]
    llm_meta = doc.get("_llm_meta") or {}
    if isinstance(llm_meta, dict):
        ver = llm_meta.get("verification_errors")
        if ver:
            return str(ver)[:240]
    env = doc.get("envelope") or doc
    if isinstance(env, dict):
        needs = env.get("needs") or []
        for need in needs:
            if isinstance(need, dict) and need.get("reason"):
                return str(need["reason"])[:240]
    return None


def _remediation_for_missing_artifact(ctx: RunContext, rel: str) -> str | None:
    producer = _UPSTREAM_ARTIFACT_PRODUCER.get(rel)
    if not producer:
        return None
    excerpt = _latest_stage_attempt_excerpt(ctx, producer)
    base = f"Re-run upstream stage '{producer}'"
    if excerpt:
        return f"{base} — last error: {excerpt}"
    return f"{base} or use Rerun from this step on {producer}."


def _llm_remediation(error: str, ctx: RunContext | None = None) -> str | None:
    low = error.lower()
    if ctx is not None:
        for rel, producer in _UPSTREAM_ARTIFACT_PRODUCER.items():
            if rel.replace("/", " ") in low or rel.split("/")[-1] in low:
                hint = _remediation_for_missing_artifact(ctx, rel)
                if hint:
                    return hint
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
        "transitions",
        "sound_design_plan",
        "sound_design_plan_flow2",
        "sfx_prompt_craft",
        "edl_narrative_audit",
        "podcast_show_description",
    }
)

_STAGE_CHECKERS: dict[str, Callable[[RunContext], list[StageInputIssue]]] = {
    "transcript_review_build": _check_transcript_review_build,
    "source_acoustic_profile": _check_source_acoustic_profile,
    "interview_spine_build": _check_interview_spine_build,
    "sonic_context_build": _check_sonic_context_build,
    "vo_ingest": _check_vo_ingest,
    "topic_coverage_audit": _check_topic_coverage_audit,
    "narrative_arc_plan": _check_narrative_arc_plan,
    "full_master_ranking": _check_full_master_ranking,
    "sound_design_plan": _check_sound_design_plan,
    "assembly_preview": _check_assembly_preview,
    "mix": _check_mix,
    "master_finalize": _check_master_finalize,
    "mmaudio_sfx": _check_mmaudio_sfx,
    "edl": _check_edl,
}
