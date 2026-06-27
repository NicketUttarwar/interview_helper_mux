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
    "local_gap_fill",
    "degraded_continue",
    "parse_failed",
]

_DETAIL_CAP = 2000


def resilience_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    base = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "progression_mode": "degraded_continue",
        "partial_persist_enabled": True,
        "local_gap_fill_enabled": True,
        "record_stripped_fields": True,
        "min_artifact_mass": {},
        "detail_value_max_chars": _DETAIL_CAP,
    }
    raw = base.get("llm_resilience") or {}
    return {**defaults, **raw}


def progression_mode(cfg: dict[str, Any] | None = None) -> str:
    return str(resilience_cfg(cfg).get("progression_mode") or "degraded_continue")


def partial_persist_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(resilience_cfg(cfg).get("partial_persist_enabled", True))


def local_gap_fill_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(resilience_cfg(cfg).get("local_gap_fill_enabled", True))


def is_degraded_continue(cfg: dict[str, Any] | None = None) -> bool:
    return progression_mode(cfg) == "degraded_continue"


def spend_stages_strict(cfg: dict[str, Any] | None = None) -> frozenset[str]:
    fh = flow_hardening_cfg(cfg)
    return frozenset(fh.get("spend_block_stages") or [])


def is_spend_stage_strict(stage_key: str, cfg: dict[str, Any] | None = None) -> bool:
    return stage_key in spend_stages_strict(cfg)


def upstream_artifact_acceptable(
    stage_key: str,
    rel_path: str,
    ctx: Any,
    cfg: dict[str, Any] | None = None,
) -> bool:
    """True when upstream producer artifact is complete or degraded-partial with mass."""
    from interview_mux.artifact_completeness import artifact_status

    cfg = cfg or merged_config()
    status = artifact_status(rel_path, ctx)
    if status == "complete":
        return True
    if not is_degraded_continue(cfg) or status != "partial":
        return False
    mass_req = (resilience_cfg(cfg).get("min_artifact_mass") or {}).get(stage_key)
    if mass_req:
        raw = ctx.read_json(rel_path)
        data = raw if isinstance(raw, dict) else {}
        return artifact_mass_score(stage_key, data, cfg) > 0
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


def sanitize_artifacts(
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

    if stage_key == "content_context":
        claims = out.get("key_claims")
        if isinstance(claims, list) and any("key_claim" in e for e in lint_errors):
            kept: list[Any] = []
            for i, claim in enumerate(claims):
                if not isinstance(claim, dict):
                    report.stripped.append(
                        {"path": f"key_claims[{i}]", "reason": "invalid claim row", "removed_value": claim}
                    )
                    continue
                if _claim_body(claim) and not _claim_has_evidence(claim):
                    report.stripped.append(
                        {
                            "path": f"key_claims[{i}]",
                            "reason": "key_claim without evidence anchor",
                            "removed_value": copy.deepcopy(claim),
                        }
                    )
                    continue
                kept.append(claim)
            out["key_claims"] = kept

        if any("thesis empty" in e.lower() for e in lint_errors):
            if not str(out.get("thesis", "")).strip():
                report.stripped.append(
                    {"path": "thesis", "reason": "thesis empty", "removed_value": out.get("thesis")}
                )
                out.pop("thesis", None)

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


def resolve_persist_plan(
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

    sanitized, report = sanitize_artifacts(
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

    merge = is_degraded_continue(cfg) and report.artifact_mass_score > 0
    return PersistPlan("partial", sanitized, report, merge_memory=merge)


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
        "local_gap_fill": "llm.resilience.gap_fill",
        "degraded_continue": "llm.resilience.degraded_continue",
        "parse_failed": "llm.resilience.parse_failed",
    }
    levels = {
        "sanitize": "warning",
        "partial_persist": "action",
        "local_gap_fill": "action",
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
        "local_gap_fill": f"LLM resilience: local gap-fill generated {n_gen} field(s) ({stage_key})",
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
) -> PersistPlan:
    """Sanitize, optional gap-fill, persist partial/full, log events."""
    plan = resolve_persist_plan(
        stage_key,
        envelope,
        arbiter_result,
        schema_errors,
        lint_errors,
        routed_via_collate=routed_via_collate,
    )

    if plan.action == "none":
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

    artifacts = plan.artifacts
    if plan.action == "partial" and local_gap_fill_enabled():
        from interview_mux.local_gap_filler import fill_artifact_gaps

        rel = producer_artifact_path(stage_key)
        if rel:
            filled, fill_report = fill_artifact_gaps(ctx, stage_key, rel, artifacts, plan.report)
            if fill_report.generated:
                artifacts = filled
                plan.report.generated.extend(fill_report.generated)
                plan.report.summary = fill_report.summary or plan.report.summary
                log_resilience_event(
                    ctx,
                    stage_key,
                    "local_gap_fill",
                    plan.report,
                    attempt=attempt,
                    arbiter_result=arbiter_result,
                    envelope=envelope,
                )
            plan.artifacts = artifacts

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
