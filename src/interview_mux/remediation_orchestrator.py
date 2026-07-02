"""Central remediation strategy selection for artifact failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from interview_mux.adaptation_loop_guard import AdaptationLoopGuard
from interview_mux.artifact_dependency_graph import root_cause_stage, transitive_invalidate
from interview_mux.micro_gap_fill import paths_from_findings, run_micro_gap_fill
from interview_mux.sufficiency_engine import SufficiencyFinding


class RemediationTrigger(str, Enum):
    REQUEST_SCHEMA = "request_schema"
    PREFLIGHT_FAIL = "preflight_fail"
    ENVELOPE_REJECT = "envelope_reject"
    ACCEPTANCE_FAIL = "acceptance_fail"
    DOWNSTREAM_PROBE_FAIL = "downstream_probe_fail"
    STALE_READ = "stale_read"
    REUSE_INVALID = "reuse_invalid"
    ITR_OPEN = "itr_open"


@dataclass
class RemediationResult:
    ok: bool
    strategy: str
    stage_key: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifact: dict[str, Any] | None = None
    upstream_stage: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "strategy": self.strategy,
            "stage_key": self.stage_key,
            "errors": self.errors[:8],
            "warnings": self.warnings[:8],
            "upstream_stage": self.upstream_stage,
        }


def remediation_enabled(cfg: dict[str, Any] | None = None) -> bool:
    from interview_mux.config import merged_config

    analysis = (cfg or merged_config()).get("analysis") or {}
    raw = analysis.get("remediation_orchestrator") or {}
    return bool(raw.get("enabled", True))


def remediate(
    ctx: Any,
    stage_key: str,
    trigger: RemediationTrigger,
    issues: list[Any],
    *,
    existing: dict[str, Any] | None = None,
) -> RemediationResult:
    if not remediation_enabled():
        return RemediationResult(False, "disabled", stage_key, errors=["remediation disabled"])

    guard = AdaptationLoopGuard.load(ctx, stage_key)
    messages = [str(getattr(i, "message", i)) for i in issues]

    if trigger == RemediationTrigger.REQUEST_SCHEMA:
        return RemediationResult(True, "recompose_schema", stage_key)

    suff_findings = [i for i in issues if isinstance(i, SufficiencyFinding)]
    if suff_findings and guard.can_micro_gap_fill():
        paths = paths_from_findings(suff_findings)
        art, errs = run_micro_gap_fill(ctx, stage_key, paths, existing=existing)
        if not errs:
            return RemediationResult(True, "micro_gap_fill", stage_key, artifact=art)

    if trigger in (RemediationTrigger.PREFLIGHT_FAIL, RemediationTrigger.ACCEPTANCE_FAIL):
        up = root_cause_stage(messages[0] if messages else "", stage_key, ctx)
        if up and up != stage_key and not guard.upstream_rerun_requested:
            guard.upstream_rerun_requested = True
            guard.save(ctx)
            return RemediationResult(
                False,
                "upstream_rerun",
                stage_key,
                upstream_stage=up,
                warnings=[f"suggest rerun {up}"],
            )

    if trigger == RemediationTrigger.DOWNSTREAM_PROBE_FAIL:
        stale = transitive_invalidate(stage_key)
        return RemediationResult(
            False,
            "propagation",
            stage_key,
            warnings=[f"stale downstream: {', '.join(stale[:6])}"],
        )

    return RemediationResult(
        False,
        "volley_retry",
        stage_key,
        errors=messages[:6],
        warnings=["retry with lint hints"],
    )


__all__ = ["RemediationResult", "RemediationTrigger", "remediate", "remediation_enabled"]
