"""Sequence the Shape Engine hardening gates around L2–L4.

Spec: docs/cross-cutting/mastering-quality-hardening.md

Order matters: diversity before feasibility (no point costing infeasible clones),
feasibility before integrity, both before auditions, auditions before critics,
critics before Pareto. Every gate fails open unless its mode is authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from interview_mux import mastering_auditions as auditions_mod
from interview_mux import mastering_diversity as diversity_mod
from interview_mux import mastering_feasibility as feasibility_mod
from interview_mux import mastering_pareto as pareto_mod
from interview_mux import mastering_semantic_integrity as integrity_mod
from interview_mux.mastering_hardening_config import gate_runs
from interview_mux.run_context import RunContext


EVAL_RUBRIC_ARTIFACT = "mastering/shape/eval_rubric.json"


class ShapeGateBlocked(RuntimeError):
    """Raised when an authoritative gate leaves no viable candidate."""


def emit_eval_rubric(
    ctx: RunContext | None,
    rubric: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist the L0 per-run rubric beside the agenda.

    Every L4 critic and the polish audit score against this, so it must exist
    before the panel runs whenever the rubric gate is authoritative.
    """
    payload = {
        "version": 1,
        **rubric,
        "generated_at": rubric.get("generated_at") or _utc_now(),
    }
    if ctx is not None and gate_runs("rubric", cfg):
        ctx.write_json(EVAL_RUBRIC_ARTIFACT, payload)
    return payload


def load_eval_rubric(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(EVAL_RUBRIC_ARTIFACT):
        return None
    doc = ctx.read_json(EVAL_RUBRIC_ARTIFACT)
    return doc if isinstance(doc, dict) else None


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


@dataclass
class ShapeGateResult:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    diversity: dict[str, Any] | None = None
    feasibility: dict[str, Any] | None = None
    semantic_integrity: dict[str, Any] | None = None
    audition_manifests: dict[str, dict[str, Any]] = field(default_factory=dict)
    remint_required: list[str] = field(default_factory=list)
    blocked_reason: str | None = None


def run_pre_critique_gates(
    ctx: RunContext | None,
    candidates: list[dict[str, Any]],
    *,
    feasibility_inputs: feasibility_mod.FeasibilityInputs | None = None,
    integrity_inputs: integrity_mod.IntegrityInputs | None = None,
    segments: dict[str, dict[str, Any]] | None = None,
    transcripts: dict[str, str] | None = None,
    render: bool = False,
    cfg: dict[str, Any] | None = None,
) -> ShapeGateResult:
    """Diversity → feasibility → semantic integrity → audition planning.

    `ctx` may be None for dry evaluation; artifacts are only written when given.
    """
    result = ShapeGateResult(candidates=list(candidates))

    if gate_runs("diversity", cfg) and len(result.candidates) > 1:
        report = diversity_mod.build_diversity_report(result.candidates, cfg=cfg)
        result.diversity = report
        result.remint_required = list(report.get("remint_candidate_ids") or [])
        if ctx is not None:
            diversity_mod.write_diversity_report(ctx, report)

    if gate_runs("feasibility", cfg):
        inputs = feasibility_inputs or feasibility_mod.FeasibilityInputs()
        report = feasibility_mod.build_feasibility_report(result.candidates, inputs, cfg=cfg)
        result.feasibility = report
        if ctx is not None:
            feasibility_mod.write_feasibility_report(ctx, report)
        result.candidates = feasibility_mod.eligible_candidates(report, result.candidates)
        if not result.candidates:
            result.blocked_reason = "no candidate is feasible"
            _raise_if_blocking(report, result)

    if gate_runs("semantic_integrity", cfg):
        inputs = integrity_inputs or integrity_mod.IntegrityInputs()
        if ctx is not None and not inputs.vernacular_must_keep_segment_ids:
            try:
                from interview_mux.stages.audio_probes import authoritative_must_keep_ids

                inputs.vernacular_must_keep_segment_ids = authoritative_must_keep_ids(ctx)
            except Exception:
                pass
        report = integrity_mod.build_integrity_report(result.candidates, inputs, cfg=cfg)
        result.semantic_integrity = report
        if ctx is not None:
            integrity_mod.write_integrity_report(ctx, report)
        result.candidates = integrity_mod.clean_candidates(report, result.candidates)
        if not result.candidates:
            result.blocked_reason = "every candidate carries a critical integrity finding"
            _raise_if_blocking(report, result)

    if gate_runs("auditions", cfg) and result.candidates:
        selected = auditions_mod.select_audition_candidates(result.candidates, cfg=cfg)
        for candidate in selected:
            manifest = auditions_mod.build_manifest(
                candidate, segments or {}, transcripts=transcripts, cfg=cfg
            )
            if render and ctx is not None:
                manifest = auditions_mod.render_audition(ctx, manifest)
            if ctx is not None:
                auditions_mod.write_manifest(ctx, manifest)
            result.audition_manifests[str(candidate.get("candidate_id"))] = manifest

    return result


def _raise_if_blocking(report: dict[str, Any], result: ShapeGateResult) -> None:
    if report.get("mode") == "authoritative":
        raise ShapeGateBlocked(result.blocked_reason or "shape gate blocked the run")


def run_post_critique_gates(
    ctx: RunContext | None,
    cross_critique: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Pareto frontier → synthesize inputs."""
    from interview_mux.mastering_critics import survivors_for_pareto

    if not gate_runs("pareto", cfg):
        return None, list(candidates)

    frontier = pareto_mod.build_frontier(
        survivors_for_pareto(cross_critique),
        hard_failed=[
            {"candidate_id": k.get("candidate_id"), "reason": k.get("reason") or "hard fail"}
            for k in (cross_critique.get("killed") or [])
        ],
        cfg=cfg,
    )
    if ctx is not None:
        pareto_mod.write_frontier(ctx, frontier)
    return frontier, pareto_mod.select_synthesize_inputs(frontier, candidates)


def hardening_artifact_status(ctx: RunContext) -> dict[str, bool]:
    """Which hardening artifacts exist — drives soft-gated journey steps."""
    rels = {
        "routing": "mastering/research/routing.json",
        "eval_rubric": "mastering/shape/eval_rubric.json",
        "diversity": diversity_mod.DIVERSITY_ARTIFACT,
        "feasibility": feasibility_mod.FEASIBILITY_ARTIFACT,
        "semantic_integrity": integrity_mod.INTEGRITY_ARTIFACT,
        "cross_critique": "mastering/shape/cross_critique.json",
        "pareto": pareto_mod.PARETO_ARTIFACT,
        "voice_clone_audit": "mastering/voice_clone_audit.json",
        "polish_audit": "mastering/polish_audit.json",
    }
    return {name: ctx.artifact_exists(rel) for name, rel in rels.items()}
