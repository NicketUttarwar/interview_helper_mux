"""Fault-tolerant LLM output handling: sanitize, partial persist, operator logging."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.config import merged_config
from interview_mux.llm_flow_hardening import flow_hardening_cfg, producer_artifact_path
from interview_mux.prompt_validation import validate_artifact_write

PersistAction = Literal["none", "partial", "full"]
ResilienceEvent = Literal[
    "sanitize",
    "partial_persist",
    "degraded_continue",
    "parse_failed",
]

_DETAIL_CAP = 2000


def resilience_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    base = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "progression_mode": "strict",
        "partial_persist_enabled": True,
        "record_stripped_fields": True,
        "min_artifact_mass": {},
        "detail_value_max_chars": _DETAIL_CAP,
    }
    raw = base.get("llm_resilience") or {}
    return {**defaults, **raw}


def progression_mode(cfg: dict[str, Any] | None = None) -> str:
    return str(resilience_cfg(cfg).get("progression_mode") or "strict")


def partial_persist_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(resilience_cfg(cfg).get("partial_persist_enabled", True))


def is_degraded_continue(cfg: dict[str, Any] | None = None) -> bool:
    """Deprecated — strict progression is always enforced."""
    if progression_mode(cfg) == "degraded_continue":
        return False
    return False


def spend_stages_strict(cfg: dict[str, Any] | None = None) -> frozenset[str]:
    fh = flow_hardening_cfg(cfg)
    return frozenset(fh.get("spend_block_stages") or [])


def is_spend_stage_strict(stage_key: str, cfg: dict[str, Any] | None = None) -> bool:
    return stage_key in spend_stages_strict(cfg)


def artifact_resilience_partial(data: dict[str, Any] | None) -> bool:
    """True when artifact was saved via partial-persist after a failed LLM gate."""
    if not isinstance(data, dict):
        return False
    resilience = (data.get("_meta") or {}).get("resilience") or {}
    return isinstance(resilience, dict) and bool(resilience.get("partial"))


def upstream_artifact_acceptable(
    stage_key: str,
    rel_path: str,
    ctx: Any,
    cfg: dict[str, Any] | None = None,
) -> bool:
    """True when upstream producer artifact is complete (strict progression)."""
    from interview_mux.artifact_completeness import artifact_status

    if artifact_status(rel_path, ctx) != "complete":
        return False
    try:
        doc = ctx.read_json(rel_path)
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    if artifact_resilience_partial(doc):
        return False
    return True


def _cap_value(val: Any, max_chars: int) -> Any:
    if isinstance(val, str) and len(val) > max_chars:
        return val[:max_chars] + "…"
    if isinstance(val, (dict, list)):
        text = json.dumps(val, default=str)
        if len(text) > max_chars:
            return {"truncated": True, "preview": text[:max_chars] + "…"}
    return val


def _claim_has_evidence(claim: dict[str, Any]) -> bool:
    if claim.get("approx_time_range"):
        return True
    for key in ("segment_ids", "evidence_segment_ids"):
        ids = claim.get(key)
        if isinstance(ids, list) and ids:
            return True
    return False


def _claim_body(claim: dict[str, Any]) -> str:
    return str(claim.get("claim") or claim.get("text") or "").strip()


@dataclass
class ResilienceReport:
    stage_key: str
    artifact_path: str | None = None
    kept_paths: list[str] = field(default_factory=list)
    stripped: list[dict[str, Any]] = field(default_factory=list)
    generated: list[dict[str, Any]] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)
    lint_errors_before: list[str] = field(default_factory=list)
    lint_errors_after: list[str] = field(default_factory=list)
    artifact_mass_score: float = 0.0
    original_artifacts: dict[str, Any] | None = None
    sanitized_artifacts: dict[str, Any] | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_key": self.stage_key,
            "artifact_path": self.artifact_path,
            "kept_paths": self.kept_paths,
            "stripped": self.stripped,
            "generated": self.generated,
            "schema_errors": self.schema_errors,
            "lint_errors_before": self.lint_errors_before,
            "lint_errors_after": self.lint_errors_after,
            "artifact_mass_score": self.artifact_mass_score,
            "summary": self.summary,
        }


@dataclass
class PersistPlan:
    action: PersistAction
    artifacts: dict[str, Any]
    report: ResilienceReport
    merge_memory: bool = False


def _artifact_mass(stage_key: str, artifacts: dict[str, Any], cfg: dict[str, Any]) -> float:
    if not artifacts:
        return 0.0
    required = (resilience_cfg(cfg).get("min_artifact_mass") or {}).get(stage_key) or []
    if not required:
        return 1.0 if artifacts else 0.0
    score = 0.0
    for key in required:
        val = artifacts.get(key)
        if isinstance(val, str) and val.strip():
            score += 1.0
        elif isinstance(val, list) and val:
            score += 1.0
        elif val:
            score += 1.0
    return score / max(len(required), 1)


def artifact_mass_score(stage_key: str, artifacts: dict[str, Any], cfg: dict[str, Any] | None = None) -> float:
    return _artifact_mass(stage_key, artifacts, cfg or merged_config())


def _prepare_stage_artifacts_for_write(
    ctx: Any,
    stage_key: str,
    artifacts: dict[str, Any],
) -> dict[str, Any]:
    """Stage-specific enrichment/repair before staging or committing artifacts."""
    if stage_key == "speaker_roles":
        from interview_mux.conversation_context import enrich_speakers_artifact

        return enrich_speakers_artifact(ctx, artifacts)
    from interview_mux.artifact_repairs import apply_repairs_for_stage

    repaired, _applied = apply_repairs_for_stage(ctx, stage_key, artifacts)
    return repaired


def sanitize_artifacts(
    ctx: Any,
    stage_key: str,
    artifacts: dict[str, Any],
    *,
    lint_errors: list[str] | None = None,
    schema_errors: list[str] | None = None,
) -> tuple[dict[str, Any], ResilienceReport]:
    """Return sanitized copy and report of stripped fields."""
    lint_errors = lint_errors or []
    schema_errors = schema_errors or []
    rel = producer_artifact_path(stage_key)
    original = copy.deepcopy(artifacts)
    out = copy.deepcopy(artifacts)
    report = ResilienceReport(
        stage_key=stage_key,
        artifact_path=rel,
        lint_errors_before=list(lint_errors),
        schema_errors=list(schema_errors),
        original_artifacts=original,
    )

    if stage_key == "speaker_roles":
        out = _prepare_stage_artifacts_for_write(ctx, stage_key, out)
    elif stage_key == "content_context":
        from interview_mux.artifact_repairs import apply_repairs_for_stage

        repaired, applied = apply_repairs_for_stage(ctx, stage_key, out)
        for entry in applied:
            report.stripped.append(entry)
        out = repaired

    report.sanitized_artifacts = out
    report.kept_paths = sorted(k for k in out if not k.startswith("_"))
    report.artifact_mass_score = artifact_mass_score(stage_key, out, merged_config())
    n = len(report.stripped)
    report.summary = (
        f"Stripped {n} field(s); kept {', '.join(report.kept_paths[:6])}"
        if n
        else f"No fields stripped; kept {', '.join(report.kept_paths[:6])}"
    )
    return out, report


def extract_schema_valid_artifact(
    rel_path: str,
    artifacts: dict[str, Any],
    *,
    stage_key: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Drop invalid rows until validate_artifact_write passes."""
    out = copy.deepcopy(artifacts)
    errors = validate_artifact_write(rel_path, out)
    if not errors:
        return out, []

    if "key_claims" in out and isinstance(out["key_claims"], list):
        valid: list[Any] = []
        for item in out["key_claims"]:
            trial = {**out, "key_claims": valid + ([item] if item else [])}
            item_errors = validate_artifact_write(rel_path, trial)
            if not item_errors:
                valid.append(item)
        out["key_claims"] = valid
        errors = validate_artifact_write(rel_path, out)

    if errors and stage_key == "content_context":
        minimal = {
            k: out[k]
            for k in ("thesis", "topics", "emotional_beats", "audience", "jargon_glossary")
            if k in out
        }
        min_errors = validate_artifact_write(rel_path, minimal)
        if not min_errors:
            return minimal, errors

    return out, errors


def _block_partial_segment_classification(lint_errors: list[str], cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or merged_config()
    from interview_mux.artifact_issue_triage import triage_cfg
    from interview_mux.coverage_limits import partition_lint_errors, soft_progression_enabled
    from interview_mux.segment_timeline_standard import segmentation_cfg

    blocking_lint, _soft = partition_lint_errors(lint_errors, cfg)
    if soft_progression_enabled(cfg) and lint_errors and not blocking_lint:
        return False
    joined = " ".join(blocking_lint).lower()
    triggers = (
        "segment_coverage_ratio",
        "all segments typed interviewee_answer",
        "manifest times not monotonic",
        "envelope_status_complete",
    )
    if segmentation_cfg(cfg).get("block_partial_classification", True):
        if any(x in joined for x in triggers):
            return True
    if triage_cfg(cfg).get("allow_partial_then_repair", True):
        return False
    fh = flow_hardening_cfg(cfg)
    if not fh.get("block_partial_segment_classification", True):
        return False
    return any(x in joined for x in triggers)


def _block_partial_on_quality_fail(
    stage_key: str,
    envelope: dict[str, Any],
    arbiter_result: dict[str, Any] | None,
    schema_errors: list[str],
    lint_errors: list[str],
    *,
    routed_via_collate: bool = False,
    cfg: dict[str, Any] | None = None,
) -> str | None:
    """Return a reason when critical stages must not stage write-approvable partials."""
    from interview_mux.analysis_memory import should_merge_envelope
    from interview_mux.coverage_limits import partition_lint_errors, soft_progression_enabled
    from interview_mux.llm_flow_hardening import ALL_CRITICAL_LLM_STAGES

    if stage_key not in ALL_CRITICAL_LLM_STAGES:
        return None
    fh = flow_hardening_cfg(cfg)
    if not fh.get("block_partial_on_quality_fail", True):
        return None
    blocking_lint, _soft = partition_lint_errors(lint_errors, cfg)
    if soft_progression_enabled(cfg) and lint_errors and not blocking_lint:
        return None
    if blocking_lint:
        return (
            f"Critical stage lint failures — no partial persist "
            f"({'; '.join(blocking_lint[:2])})"
        )
    if schema_errors:
        return (
            f"Critical stage schema errors — no partial persist "
            f"({'; '.join(schema_errors[:2])})"
        )
    te = ((envelope.get("_llm_meta") or {}).get("truncation_escalation") or {})
    flags = te.get("final_flags") or []
    if flags:
        return f"Truncation flags present — no partial persist ({', '.join(list(flags)[:2])})"
    if not should_merge_envelope(
        arbiter_result, envelope, routed_via_collate=routed_via_collate
    ):
        return "Envelope not accepted — no partial persist"
    return None


def resolve_persist_plan(
    ctx: Any,
    stage_key: str,
    envelope: dict[str, Any],
    arbiter_result: dict[str, Any] | None,
    schema_errors: list[str],
    lint_errors: list[str],
    *,
    routed_via_collate: bool = False,
    cfg: dict[str, Any] | None = None,
) -> PersistPlan:
    from interview_mux.analysis_memory import should_merge_envelope

    cfg = cfg or merged_config()
    rel = producer_artifact_path(stage_key)
    artifacts = envelope.get("artifacts") or {}
    empty_report = ResilienceReport(stage_key=stage_key, artifact_path=rel)

    if not artifacts:
        empty_report.summary = "No artifacts in envelope"
        return PersistPlan("none", {}, empty_report)

    if (
        not schema_errors
        and not lint_errors
        and should_merge_envelope(arbiter_result, envelope, routed_via_collate=routed_via_collate)
    ):
        valid, _ = extract_schema_valid_artifact(rel or "", artifacts, stage_key=stage_key) if rel else (artifacts, [])
        empty_report.kept_paths = list(valid.keys())
        empty_report.artifact_mass_score = 1.0
        empty_report.sanitized_artifacts = valid
        empty_report.summary = "Full persist — no sanitization needed"
        return PersistPlan("full", valid, empty_report, merge_memory=True)

    if not partial_persist_enabled(cfg):
        empty_report.summary = "Partial persist disabled"
        return PersistPlan("none", {}, empty_report)

    if stage_key == "segment_classification" and _block_partial_segment_classification(lint_errors, cfg):
        empty_report.summary = "Partial persist blocked — segment classification obligation lint failed"
        empty_report.lint_errors_before = lint_errors[:8]
        return PersistPlan("none", {}, empty_report)

    quality_block = _block_partial_on_quality_fail(
        stage_key,
        envelope,
        arbiter_result,
        schema_errors,
        lint_errors,
        routed_via_collate=routed_via_collate,
        cfg=cfg,
    )
    if quality_block:
        empty_report.summary = quality_block
        empty_report.lint_errors_before = lint_errors[:8]
        empty_report.schema_errors = schema_errors[:8]
        return PersistPlan("none", {}, empty_report)

    sanitized, report = sanitize_artifacts(
        ctx,
        stage_key,
        artifacts,
        lint_errors=lint_errors,
        schema_errors=schema_errors,
    )
    if rel:
        sanitized, remaining_schema = extract_schema_valid_artifact(
            rel, sanitized, stage_key=stage_key
        )
        report.schema_errors = remaining_schema
        if remaining_schema:
            report.summary = "Schema validation failed after sanitize"
            return PersistPlan("none", {}, report)
    report.sanitized_artifacts = sanitized
    report.artifact_mass_score = artifact_mass_score(stage_key, sanitized, cfg)

    if report.artifact_mass_score <= 0:
        report.summary = "Insufficient artifact mass after sanitize"
        return PersistPlan("none", {}, report)

    return PersistPlan("partial", sanitized, report, merge_memory=False)


def write_resilience_sidecar(
    ctx: Any,
    stage_key: str,
    attempt: int,
    report: ResilienceReport,
) -> str:
    if not resilience_cfg().get("record_stripped_fields", True):
        return ""
    rel = f"understanding/stage_runs/{stage_key}/attempt_{attempt:03d}_resilience.json"
    ctx.write_json(rel, report.to_dict(), skip_handoff=True)
    return rel


def log_resilience_event(
    ctx: Any,
    stage_key: str,
    event: ResilienceEvent,
    report: ResilienceReport,
    *,
    attempt: int | None = None,
    arbiter_result: dict[str, Any] | None = None,
    envelope: dict[str, Any] | None = None,
    llm_call_path: str | None = None,
    sidecar_path: str | None = None,
) -> None:
    cfg = merged_config()
    cap = int(resilience_cfg(cfg).get("detail_value_max_chars") or _DETAIL_CAP)
    action_ids = {
        "sanitize": "llm.resilience.sanitize",
        "partial_persist": "llm.resilience.partial_persist",
        "degraded_continue": "llm.resilience.degraded_continue",
        "parse_failed": "llm.resilience.parse_failed",
    }
    levels = {
        "sanitize": "warning",
        "partial_persist": "action",
        "degraded_continue": "action",
        "parse_failed": "warning",
    }
    n_stripped = len(report.stripped)
    n_gen = len(report.generated)
    messages = {
        "sanitize": f"LLM resilience: sanitized partial output ({stage_key}) — {n_stripped} field(s) stripped",
        "partial_persist": (
            f"LLM resilience: saved partial artifact ({report.artifact_path or stage_key}) "
            f"— {len(report.kept_paths)} field(s) kept"
        ),
        "degraded_continue": f"LLM resilience: stage continued in degraded mode ({stage_key})",
        "parse_failed": f"LLM resilience: envelope parse failed — raw preserved ({stage_key})",
    }

    orig = report.original_artifacts or (envelope or {}).get("artifacts") or {}
    llm_meta = (envelope or {}).get("_llm_meta") or {}
    detail: dict[str, Any] = {
        "event": event,
        "stage_key": stage_key,
        "attempt": attempt,
        "progression_mode": progression_mode(cfg),
        "artifact_path": report.artifact_path,
        "sidecar_path": sidecar_path,
        "llm_call_path": llm_call_path,
        "original": {
            "envelope_status": (envelope or {}).get("status"),
            "arbiter_verdict": (arbiter_result or {}).get("verdict"),
            "model_id": llm_meta.get("model_id"),
            "task_kind": llm_meta.get("task_kind"),
            "artifact_keys": list(orig.keys()) if isinstance(orig, dict) else [],
            "envelope_excerpt": _cap_value(orig, cap),
        },
        "changes": {
            "stripped": report.stripped,
            "kept": report.kept_paths,
            "generated": report.generated,
        },
        "lint_errors_before": report.lint_errors_before,
        "lint_errors_after": report.lint_errors_after,
        "schema_errors": report.schema_errors,
        "summary": report.summary or messages.get(event, ""),
    }

    ctx.log(
        messages.get(event, f"LLM resilience: {event} ({stage_key})"),
        level=levels.get(event, "info"),
        stage=stage_key,
        detail=detail,
        action_id=action_ids.get(event),
        origin="pipeline",
    )


def apply_resilience_and_persist(
    ctx: Any,
    stage_key: str,
    attempt: int,
    envelope: dict[str, Any],
    arbiter_result: dict[str, Any] | None,
    schema_errors: list[str],
    lint_errors: list[str],
    *,
    persist_fn: Any | None,
    sync_fn: Any | None = None,
    routed_via_collate: bool = False,
    volley: list[dict[str, str]] | None = None,
) -> PersistPlan:
    """Sanitize, persist partial/full, log events."""
    from interview_mux.llm_output_normalizer import normalize_envelope_for_stage
    from interview_mux.null_field_policy import (
        acknowledge_null_fields,
        log_critical_null_blocked,
        null_policy_cfg,
    )

    caller_envelope = envelope
    norm = normalize_envelope_for_stage(
        ctx,
        envelope,
        stage_key=stage_key,
        volley=volley,
    )
    envelope = norm.normalized

    def _sync_caller_envelope() -> None:
        caller_envelope.clear()
        caller_envelope.update(envelope)

    artifacts = envelope.get("artifacts") or {}
    if artifacts:
        updated, critical_nulls, _ack = acknowledge_null_fields(
            ctx,
            stage_key,
            artifacts,
            envelope_meta=envelope.get("_llm_meta"),
        )
        envelope["artifacts"] = updated
        if critical_nulls and null_policy_cfg().get("hard_stop_on_critical_null", True):
            log_critical_null_blocked(
                ctx,
                stage_key,
                critical_nulls,
                artifacts=updated,
                envelope=envelope,
                arbiter_result=arbiter_result,
                volley=volley,
                llm_call_path=(envelope.get("_llm_meta") or {}).get("llm_call_path"),
            )
            envelope["status"] = "blocked"
            envelope.setdefault("needs", [])
            envelope["needs"].append(
                {
                    "type": "rerun_stage",
                    "stage": stage_key,
                    "reason": f"Critical null field(s): {', '.join(critical_nulls[:4])}",
                    "blocking": True,
                }
            )
            empty = ResilienceReport(stage_key=stage_key, artifact_path=producer_artifact_path(stage_key))
            empty.summary = "Blocked — critical null fields"
            routing = envelope.setdefault("_routing_meta", {})
            routing["persist_action"] = "none"
            routing["critical_null_paths"] = critical_nulls
            _sync_caller_envelope()
            return PersistPlan("none", {}, empty)

    artifacts = envelope.get("artifacts") or {}
    if artifacts:
        envelope["artifacts"] = _prepare_stage_artifacts_for_write(ctx, stage_key, artifacts)

    plan = resolve_persist_plan(
        ctx,
        stage_key,
        envelope,
        arbiter_result,
        schema_errors,
        lint_errors,
        routed_via_collate=routed_via_collate,
    )

    routing = envelope.setdefault("_routing_meta", {})
    if arbiter_result and str(arbiter_result.get("verdict", "")).strip() != "accept":
        routing["envelope_blocked"] = True

    if plan.action == "none":
        summary = (plan.report.summary or "").lower()
        if any(
            tok in summary
            for tok in (
                "no partial persist",
                "partial persist blocked",
                "partial persist disabled",
            )
        ):
            sidecar = write_resilience_sidecar(ctx, stage_key, attempt, plan.report)
            ctx.log(
                f"LLM resilience: skipped partial persist ({stage_key}) — {plan.report.summary}",
                level="warning",
                stage=stage_key,
                action_id="llm.resilience.partial_blocked",
                detail={
                    "summary": plan.report.summary,
                    "sidecar": sidecar or None,
                    "lint_errors": (plan.report.lint_errors_before or [])[:4],
                },
            )
        routing["persist_action"] = "none"
        _sync_caller_envelope()
        return plan

    if plan.action in ("partial", "full") and plan.report.stripped:
        log_resilience_event(
            ctx,
            stage_key,
            "sanitize",
            plan.report,
            attempt=attempt,
            arbiter_result=arbiter_result,
            envelope=envelope,
        )

    artifacts = _prepare_stage_artifacts_for_write(ctx, stage_key, plan.artifacts)

    if persist_fn and artifacts:
        from interview_mux.artifact_writes import write_partial_artifact

        rel = producer_artifact_path(stage_key) or ""
        try:
            write_partial_artifact(
                ctx,
                rel,
                artifacts,
                resilience_report=plan.report,
                stage_key=stage_key,
                partial=(plan.action == "partial"),
            )
        except ValueError as exc:
            ctx.log(
                f"LLM resilience: partial persist failed ({stage_key}) — {exc}",
                level="warning",
                stage=stage_key,
            )
            plan.action = "none"
            _sync_caller_envelope()
            return plan
        sidecar = write_resilience_sidecar(ctx, stage_key, attempt, plan.report)
        log_resilience_event(
            ctx,
            stage_key,
            "partial_persist",
            plan.report,
            attempt=attempt,
            arbiter_result=arbiter_result,
            envelope=envelope,
            sidecar_path=sidecar or None,
        )
        if sync_fn:
            sync_fn(ctx, artifacts)

    routing = envelope.setdefault("_routing_meta", {})
    routing["resilience_report"] = plan.report.to_dict()
    routing["persist_action"] = plan.action
    _sync_caller_envelope()
    return plan


def record_degraded_stage(ctx: Any, stage_key: str, report: ResilienceReport) -> None:
    from interview_mux.analysis_memory import load_analysis_state, save_analysis_state

    state = load_analysis_state(ctx)
    meta = state.setdefault("meta", {})
    degraded = meta.setdefault("degraded_stages", {})
    degraded[stage_key] = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "summary": report.summary,
        "stripped_count": len(report.stripped),
        "generated_count": len(report.generated),
    }
    save_analysis_state(ctx, state)
