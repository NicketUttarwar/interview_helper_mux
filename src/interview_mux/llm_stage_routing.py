"""Unified LLM stage routing: primary, schema, arbiter, uptier, decompose, merge gating."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.analysis_memory import (
    apply_envelope_to_memory,
    enqueue_investigations,
    record_stage_attempt,
    record_uptier_retry,
    uptier_budget_remaining,
)
from interview_mux.llm_output_resilience import apply_resilience_and_persist
from interview_mux.config import merged_config
from interview_mux.context_volley import truncation_flags_for_volley
from interview_mux.local_llm_config import skip_openai_when_local_satisfied
from interview_mux.llm_flow_hardening import flow_hardening_cfg, flow_hardening_enabled
from interview_mux.llm_preflight import run_preflight
from interview_mux.model_registry import stage_severity
from interview_mux.local_capability_router import (
    attach_router_meta,
    prepare_volley_via_router,
)
from interview_mux.local_volley_framer import LocalFramingResult, prepare_volley_for_llm
from interview_mux.arbiter_expectations import build_stage_expectations
from interview_mux.attempt_budget import (
    budget_extra_for_attempt,
    build_attempt_signature,
    check_arbiter_budget,
    is_stuck,
    record_arbiter_reject,
    record_primary_attempt,
    stuck_count,
    stuck_signature_threshold,
)
from interview_mux.deterministic_lint import deterministic_lint, reconcile_envelope_confidence
from interview_mux.llm_arbiter import run_llm_arbiter
from interview_mux.llm_shard_plans import (
    DECOMPOSE_ELIGIBLE,
    build_deterministic_shard_plan,
    should_proactive_decompose_boundary_detection,
    should_proactive_decompose_content_context,
    should_proactive_decompose_segment_classification,
)
from interview_mux.lint_adaptation import format_lint_feedback
from interview_mux.classification_obligation import obligation_lint_errors
from interview_mux.operator_recovery import log_adaptation_step, log_operator_halt
from interview_mux.llm_subtasks import run_shards_then_collate
from interview_mux.model_registry import resolve_model
from interview_mux.prompt_validation import (
    STAGE_ARTIFACT_SCHEMAS,
    format_validation_feedback,
    validate_envelope,
    validate_stage_artifacts,
)
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.stages.llm_runner import run_prompt_envelope

PersistFn = Callable[[RunContext, dict[str, Any]], None]
SyncFn = Callable[[RunContext, dict[str, Any]], None]

_LINT_EVIDENCE_APPENDIX = (
    "Prior attempt failed evidence anchoring. Pre-segmentation: every topic and key_claim "
    "MUST include a non-null approx_time_range (mm:ss-mm:ss) drawn from transcript timing. "
    "Use JSON null for segment_ids/evidence_segment_ids when seg_* ids do not exist yet — "
    "empty [] arrays without a time range will fail lint again."
)
_LINT_THESIS_APPENDIX = (
    "Prior attempt had an empty thesis. Produce a non-empty one-sentence thesis grounded "
    "in the interviewee's stated goals from the transcript."
)


def _lint_retry_strategy(lint_errors: list[str], stage_key: str) -> dict[str, Any]:
    """Map lint failures to non-identical retry parameters for the next inner-loop attempt."""
    from interview_mux.lint_adaptation import lint_retry_strategy

    return lint_retry_strategy(lint_errors, stage_key)


def _system_prompt_with_appendix(
    prompt_rel: str,
    stage_key: str,
    appendix: str | None,
) -> str | None:
    if not appendix:
        return None
    from interview_mux.stages.llm_runner import load_system_prompt_for_stage

    base = load_system_prompt_for_stage(
        prompt_rel,
        stage_key,
        include_preamble=True,
        cfg=merged_config(),
    )
    return f"{base}\n\n## Retry constraints\n{appendix}"


def _max_volley_retries(ctx: RunContext) -> int:
    if ctx.artifact_exists("understanding/analysis_orchestration.json"):
        orch = ctx.read_json("understanding/analysis_orchestration.json")
        return int(orch.get("max_volley_retries", 2))
    return int((merged_config().get("analysis") or {}).get("max_volley_retries", 2))


def _assistant_summary_from_envelope(envelope: dict[str, Any]) -> str:
    artifacts = envelope.get("artifacts") or {}
    counts = {k: len(v) if isinstance(v, list) else 1 for k, v in artifacts.items()}
    summary = (envelope.get("reasoning_summary") or "").strip() or "(no reasoning_summary)"
    return (
        f"## Prior attempt output (incomplete)\n"
        f"Status: {envelope.get('status')}\n"
        f"Summary: {summary[:400]}\n"
        f"Artifact keys: {list(artifacts.keys())}; counts: {counts}"
    )


def _try_flagship_uptier_promote(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    arbiter_result: dict[str, Any],
    schema_errors: list[str],
    *,
    volley: list[dict[str, str]] | None = None,
) -> bool:
    """When uptier is exhausted at flagship, accept if lint/schema clean and roles evidenced."""
    from interview_mux.model_registry import resolve_model

    llm_meta = envelope.get("_llm_meta") or {}
    tier = str(llm_meta.get("model_tier") or "")
    resolved = resolve_model(stage_key, task_kind="primary", bump_tier=True)
    if tier != "flagship" and resolved.tier != "flagship":
        return False
    reconcile_envelope_confidence(stage_key, envelope)
    lint_errors = deterministic_lint(
        stage_key,
        envelope,
        ctx,
        schema_errors=schema_errors,
        volley=volley,
    )
    if schema_errors or lint_errors:
        return False
    if stage_key == "speaker_roles":
        speakers = (envelope.get("artifacts") or {}).get("speakers") or []
        if not speakers:
            return False
        if all(str(sp.get("role") or "unknown") == "unknown" for sp in speakers if isinstance(sp, dict)):
            return False
    arbiter_result["verdict"] = "accept"
    arbiter_result["reasoning_summary"] = (
        "Promoted to accept: flagship tier with clean schema/lint after uptier exhaustion."
    )
    envelope["status"] = "complete"
    ctx.log(
        f"Stage {stage_key}: flagship uptier promote — accepting envelope.",
        level="info",
        stage=stage_key,
        action_id="llm.flagship_promote",
    )
    return True


def _extend_volley_for_retry(
    volley: list[dict[str, str]],
    envelope: dict[str, Any],
    *,
    stage_key: str,
    schema_errors: list[str] | None = None,
    lint_errors: list[str] | None = None,
    lint_feedback: str | None = None,
    blocking_needs: list[dict[str, Any]] | None = None,
    retry_index: int = 0,
    ctx: RunContext | None = None,
) -> list[dict[str, str]]:
    extended = [*volley]
    uncertainty_phrases = ("role is unclear", "roles are unclear", "cannot determine", "not explicitly labeled")
    stripped = [
        m
        for m in extended
        if not (
            m.get("role") == "assistant"
            and any(p in str(m.get("content", "")).lower() for p in uncertainty_phrases)
        )
    ]
    if len(stripped) != len(extended):
        extended = stripped
    extended.append({"role": "assistant", "content": _assistant_summary_from_envelope(envelope)})
    if schema_errors:
        env_errs = [e for e in schema_errors if e.startswith("envelope.")]
        art_errs = [e for e in schema_errors if not e.startswith("envelope.")]
        extended.append(
            {
                "role": "user",
                "content": format_validation_feedback(
                    schema_errors,
                    stage_key=stage_key,
                    envelope_errors=env_errs,
                ),
            }
        )
        error_class = "envelope" if env_errs and not art_errs else "schema"
    elif lint_errors or lint_feedback:
        content = lint_feedback or format_lint_feedback(lint_errors or [], stage_key, ctx=ctx)
        extended.append({"role": "user", "content": content})
        error_class = "lint"
    elif blocking_needs:
        lines = ["## Blocking needs from prior attempt", ""]
        for need in blocking_needs:
            lines.append(f"- [{need.get('type')}] {need.get('reason', need.get('question', ''))}")
        extended.append({"role": "user", "content": "\n".join(lines)})
        error_class = "blocking_needs"
    else:
        error_class = "unknown"
    if ctx is not None:
        ctx.log(
            f"LLM volley retry {retry_index} for {stage_key} ({error_class})",
            level="warning",
            stage=stage_key,
            action_id="llm.volley_retry",
            detail={
                "retry_index": retry_index,
                "error_class": error_class,
                "schema_errors": (schema_errors or [])[:8],
                "format_block_injected": True,
            },
            origin="pipeline",
        )
    return extended


def _run_primary_with_openai_fallback(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    volley: list[dict[str, str]],
    *,
    local_framing: LocalFramingResult | None = None,
    bump_tier: bool = False,
    call_attempt: int = 1,
    system_appendix: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
    """
    Run OpenAI primary (always, unless explicitly configured to skip when local satisfied).
    Local framing only compresses the volley; OpenAI remains the source of stage envelopes.
    """
    force_openai = stage_key in STAGE_ARTIFACT_SCHEMAS
    if (
        not force_openai
        and local_framing
        and local_framing.used_local
        and not local_framing.escalate
        and skip_openai_when_local_satisfied()
    ):
        ctx.log(
            f"Local LLM satisfied {stage_key} without OpenAI primary (pilot mode).",
            level="warning",
            stage=stage_key,
        )
        return (
            {
                "status": "complete",
                "artifacts": {},
                "memory_updates": {},
                "needs": [],
                "follow_up_investigations": [],
                "reasoning_summary": local_framing.reason or "local-only pilot",
                "_llm_meta": {"model_tier": "local", "model_id": local_framing.model_id or "local_mlx", "task_kind": "primary"},
                "_local_only_pilot": True,
            },
            volley,
            ["local_only_pilot_no_artifacts"],
        )
    return _run_primary_with_volley_retries(
        ctx,
        stage_key,
        prompt_rel,
        volley,
        bump_tier=bump_tier,
        call_attempt=call_attempt,
        system_appendix=system_appendix,
    )


def _run_primary_with_volley_retries(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    volley: list[dict[str, str]],
    *,
    bump_tier: bool = False,
    call_attempt: int = 1,
    system_appendix: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
    from interview_mux.truncation_policy import TruncationEscalationRequired

    system_override = _system_prompt_with_appendix(prompt_rel, stage_key, system_appendix)

    def _call_primary(*, retry_index: int = 0) -> dict[str, Any]:
        try:
            return run_prompt_envelope(
                stage_key,
                prompt_rel,
                messages=volley,
                ctx=ctx,
                task_kind="primary",
                bump_tier=bump_tier,
                call_attempt=call_attempt,
                system_override=system_override,
                volley_retry_index=retry_index,
            )
        except TruncationEscalationRequired as exc:
            ctx.log(
                f"Stage {stage_key}: truncation escalation required — "
                f"{', '.join(exc.flags[:3])}",
                level="warning",
                stage=stage_key,
                action_id="truncation.escalation_required",
                detail={"flags": exc.flags, "steps": exc.steps},
            )
            return {
                "status": "blocked",
                "artifacts": {},
                "memory_updates": {},
                "needs": [
                    {
                        "type": "decompose",
                        "stage": stage_key,
                        "reason": f"LLM input truncated: {', '.join(exc.flags[:3])}",
                        "blocking": True,
                    }
                ],
                "follow_up_investigations": [],
                "confidence": 0.0,
                "reasoning_summary": f"Blocked: truncated LLM input ({', '.join(exc.flags[:3])})",
                "_llm_meta": {
                    "task_kind": "primary",
                    "truncation_escalation": {
                        "rounds": 1,
                        "steps": list(exc.steps),
                        "final_flags": list(exc.flags),
                        "provider": "openai",
                    },
                },
            }

    envelope = _call_primary()
    artifacts = envelope.get("artifacts") or {}
    schema_errors = validate_stage_artifacts(stage_key, artifacts)
    envelope_errors = validate_envelope(envelope)
    all_errors = envelope_errors + schema_errors

    # Truncation hard-block: do not volley-retry with the same truncated messages.
    if any(
        isinstance(n, dict) and n.get("type") == "decompose"
        for n in (envelope.get("needs") or [])
    ) and (envelope.get("_llm_meta") or {}).get("truncation_escalation", {}).get("final_flags"):
        reconcile_envelope_confidence(stage_key, envelope)
        return envelope, volley, all_errors

    retries = 0
    max_retries = _max_volley_retries(ctx)
    while retries < max_retries and all_errors:
        retries += 1
        volley = _extend_volley_for_retry(
            volley,
            envelope,
            stage_key=stage_key,
            schema_errors=all_errors,
            retry_index=retries,
            ctx=ctx,
        )
        envelope = _call_primary(retry_index=retries)
        artifacts = envelope.get("artifacts") or {}
        schema_errors = validate_stage_artifacts(stage_key, artifacts)
        envelope_errors = validate_envelope(envelope)
        all_errors = envelope_errors + schema_errors

    status = envelope.get("status", "complete")
    blocking_needs = [
        n for n in envelope.get("needs") or [] if n.get("blocking") and n.get("type") != "operator"
    ]
    if retries < max_retries and status in ("partial", "needs_input") and (blocking_needs or not artifacts):
        retries += 1
        volley = _extend_volley_for_retry(
            volley,
            envelope,
            stage_key=stage_key,
            blocking_needs=blocking_needs,
            retry_index=retries,
            ctx=ctx,
        )
        envelope = _call_primary(retry_index=retries)
        artifacts = envelope.get("artifacts") or {}
        schema_errors = validate_stage_artifacts(stage_key, artifacts)
        envelope_errors = validate_envelope(envelope)
        all_errors = envelope_errors + schema_errors

    reconcile_envelope_confidence(stage_key, envelope)
    return envelope, volley, all_errors


def _apply_lint_accept_hardening(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    arbiter_result: dict[str, Any],
    lint_errors: list[str],
) -> None:
    """Reject arbiter accept when deterministic lint fails."""
    if not flow_hardening_enabled() or not lint_errors:
        return
    if str(arbiter_result.get("verdict", "")).strip() != "accept":
        return
    envelope["status"] = "blocked"
    envelope.setdefault("needs", [])
    envelope["needs"].append(
        {
            "type": "rerun_stage",
            "stage": stage_key,
            "reason": f"Deterministic lint: {'; '.join(lint_errors[:3])}",
            "blocking": True,
        }
    )
    arbiter_result["verdict"] = "enqueue_investigation"
    arbiter_result["reasoning_summary"] = "Overridden: accept blocked by deterministic lint."
    ctx.log(
        f"Stage {stage_key}: arbiter accept overridden — lint failures.",
        level="warning",
        stage=stage_key,
        detail={"lint_errors": lint_errors[:4]},
    )


def _apply_stuck_detector(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    arbiter_result: dict[str, Any],
    attempt_signature: tuple[Any, ...],
) -> None:
    if not flow_hardening_enabled():
        return
    if not is_stuck(ctx, stage_key):
        return
    threshold = stuck_signature_threshold()
    envelope["status"] = "blocked"
    envelope.setdefault("follow_up_investigations", [])
    envelope["follow_up_investigations"].append(
        {
            "kind": "stuck_retry_loop",
            "question": (
                f"{stage_key}: same attempt signature {threshold}+ times — operator review required."
            ),
            "priority": "high",
            "blocking": True,
            "suggested_action": {"type": "operator", "stage": stage_key},
        }
    )
    log_operator_halt(
        ctx,
        stage_key=stage_key,
        halt_kind="stuck_signature",
        message=(
            f"Stage {stage_key}: stuck retry loop detected "
            f"({stuck_count(ctx, stage_key)}/{threshold} identical signatures)."
        ),
        recovery_from_stage=stage_key,
        action_id="llm.budget.stuck_signature",
        cap_name="stuck_signature_threshold",
        cap_value=threshold,
        current_value=stuck_count(ctx, stage_key),
    )
    arbiter_result["verdict"] = "enqueue_investigation"
    arbiter_result["reasoning_summary"] = (
        f"Stuck loop detected ({threshold} identical signatures)."
    )
    ctx.log(
        f"Stage {stage_key}: stuck retry loop — operator checkpoint.",
        level="action",
        stage=stage_key,
    )


def _apply_schema_accept_hardening(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    arbiter_result: dict[str, Any],
    schema_errors: list[str],
) -> None:
    """Reject arbiter accept when artifacts fail schema under flow hardening."""
    if not flow_hardening_enabled():
        return
    if not flow_hardening_cfg().get("halt_on_schema_errors_with_accept", True):
        return
    if not schema_errors:
        return
    if str(arbiter_result.get("verdict", "")).strip() != "accept":
        return
    envelope["status"] = "blocked"
    envelope.setdefault("needs", [])
    envelope["needs"].append(
        {
            "type": "rerun_stage",
            "stage": stage_key,
            "reason": f"Schema errors after arbiter accept: {'; '.join(schema_errors[:3])}",
            "blocking": True,
        }
    )
    arbiter_result["verdict"] = "enqueue_investigation"
    arbiter_result["reasoning_summary"] = (
        "Overridden: accept with schema errors blocked by flow_hardening."
    )
    ctx.log(
        f"Stage {stage_key}: arbiter accept overridden — schema errors remain.",
        level="warning",
        stage=stage_key,
    )


def _maybe_enqueue_truncation(
    ctx: RunContext,
    stage_key: str,
    truncation_flags: list[str],
    envelope: dict[str, Any],
    arbiter_result: dict[str, Any],
) -> None:
    if not truncation_flags:
        return
    verdict = arbiter_result.get("verdict")
    if verdict in ("accept",) and envelope.get("status") == "complete":
        return
    enqueue_investigations(
        ctx,
        [
            {
                "kind": "context_truncated",
                "question": f"{stage_key}: evidence truncated ({', '.join(truncation_flags)}). Consider decompose or raise caps.",
                "priority": "high",
                "blocking": False,
                "suggested_action": {"type": "rerun_stage", "stage": stage_key},
            }
        ],
        created_by_stage=stage_key,
    )


def _preflight_blocked_envelope(
    stage_key: str,
    errors: list[str],
) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, Any], list[str]]:
    reason = errors[0] if errors else "preflight failed"
    envelope: dict[str, Any] = {
        "status": "blocked",
        "artifacts": {},
        "memory_updates": {},
        "needs": [
            {
                "type": "rerun_stage",
                "stage": stage_key,
                "reason": reason,
                "blocking": True,
            }
        ],
        "follow_up_investigations": [],
        "reasoning_summary": f"Preflight blocked: {reason}",
        "_routing_meta": {"preflight_blocked": True},
    }
    arbiter_result = {
        "verdict": "enqueue_investigation",
        "confidence": 0.0,
        "gaps": errors[:4],
        "shard_plan": [],
        "reasoning_summary": "Skipped OpenAI — preflight failed.",
    }
    return envelope, [], arbiter_result, errors


def _arbiter_stage_expectations(stage_key: str, *, bump_tier: bool = False) -> dict[str, Any]:
    return build_stage_expectations(stage_key, bump_tier=bump_tier)


def _post_arbiter_hardening(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    arbiter_result: dict[str, Any],
    schema_errors: list[str],
    *,
    volley: list[dict[str, str]] | None = None,
    truncation_flags: list[str] | None = None,
    routed_via_collate: bool = False,
    stage_input_obligation: dict[str, Any] | None = None,
) -> list[str]:
    obligation_errors: list[str] = []
    if stage_key == "segment_classification" and stage_input_obligation:
        artifacts = envelope.get("artifacts") or {}
        segments = artifacts.get("segments") or []
        if isinstance(segments, list):
            obligation_errors = obligation_lint_errors(stage_input_obligation, segments)
    lint_errors = deterministic_lint(
        stage_key,
        envelope,
        ctx,
        schema_errors=schema_errors,
        truncation_flags=truncation_flags,
        volley=volley,
        routed_via_collate=routed_via_collate,
    )
    if obligation_errors:
        lint_errors = [*obligation_errors, *lint_errors]
    verdict = str(arbiter_result.get("verdict", "")).strip()
    if verdict != "accept":
        record_arbiter_reject(ctx, stage_key, verdict)
    _apply_lint_accept_hardening(ctx, stage_key, envelope, arbiter_result, lint_errors)
    _apply_schema_accept_hardening(ctx, stage_key, envelope, arbiter_result, schema_errors)
    sig = build_attempt_signature(envelope, volley, schema_errors, lint_errors)
    _apply_stuck_detector(ctx, stage_key, envelope, arbiter_result, sig)
    return lint_errors


def run_llm_stage_with_routing(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    stage_input: dict[str, Any],
    *,
    attempt: int = 1,
    bump_tier: bool = False,
    force_decompose: bool = False,
    system_appendix: str | None = None,
    stage_input_obligation: dict[str, Any] | None = None,
    context_cap_boost_round: int = 0,
    clear_field_truncation: bool = False,
) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, Any], list[str], int, str | None]:
    """
    Run primary → validate → arbiter → optional uptier/decompose.
    Returns (envelope, volley, arbiter_result, schema_errors, shard_count, shard_plan_source).
    """
    obligation = stage_input_obligation or stage_input.get("classification_obligation")
    record_primary_attempt(ctx, stage_key)
    router_outcome = None
    with logged_step(f"{stage_key}/preflight", ctx=ctx, stage=stage_key):
        arb_budget_msg = check_arbiter_budget(ctx, stage_key)
        if arb_budget_msg:
            log_operator_halt(
                ctx,
                stage_key=stage_key,
                halt_kind="arbiter_budget_exhausted",
                message=arb_budget_msg,
                recovery_from_stage=stage_key,
                action_id="llm.budget.arbiter_exhausted",
                cap_name="max_arbiter_rejects_per_stage",
            )
            env, volley, arb, errs = _preflight_blocked_envelope(stage_key, [arb_budget_msg])
            return env, volley, arb, errs, 0, None

        if flow_hardening_enabled() and flow_hardening_cfg().get("preflight_enabled", True):
            pf_errors = run_preflight(stage_key, ctx)
            if pf_errors:
                ctx.log(
                    f"Stage {stage_key}: preflight failed — {pf_errors[0]}",
                    level="warning",
                    stage=stage_key,
                )
                env, volley, arb, errs = _preflight_blocked_envelope(stage_key, pf_errors)
                return env, volley, arb, errs, 0, None

    if stage_key == "content_context" and should_proactive_decompose_content_context(stage_input):
        shard_plan, shard_plan_source = build_deterministic_shard_plan(
            stage_key,
            stage_input,
            truncation_flags=["proactive_decompose_chars"],
        )
        if shard_plan:
            with logged_step(f"{stage_key}/proactive_decompose", ctx=ctx, stage=stage_key):
                volley, _local = prepare_volley_for_llm(
                    ctx, stage_key, stage_input, profile="full", task_kind="primary"
                )
                envelope, shard_count = run_shards_then_collate(
                    ctx,
                    stage_key=stage_key,
                    prompt_rel=prompt_rel,
                    stage_input=stage_input,
                    shard_plan=shard_plan,
                    parent_attempt=attempt,
                )
                schema_errors = validate_stage_artifacts(stage_key, envelope.get("artifacts") or {})
                arbiter_result = run_llm_arbiter(
                    ctx=ctx,
                    stage_key=stage_key,
                    attempt_number=attempt,
                    envelope=envelope,
                    schema_errors=schema_errors,
                    context_chars=sum(len(m.get("content", "")) for m in volley),
                    truncation_flags=truncation_flags_for_volley(volley),
                    stage_expectations=_arbiter_stage_expectations(stage_key),
                )
                envelope["_routing_meta"] = {
                    "routed_via_collate": True,
                    "shard_plan_source": shard_plan_source,
                    "proactive_decompose": True,
                }
                lint_errors = _post_arbiter_hardening(
                    ctx,
                    stage_key,
                    envelope,
                    arbiter_result,
                    schema_errors,
                    volley=volley,
                    truncation_flags=truncation_flags_for_volley(volley),
                    routed_via_collate=True,
                    stage_input_obligation=obligation,
                )
                envelope.setdefault("_routing_meta", {})["deterministic_lint_errors"] = lint_errors
            return envelope, volley, arbiter_result, schema_errors, shard_count, shard_plan_source

    if stage_key == "boundary_detection" and should_proactive_decompose_boundary_detection(
        stage_input, ctx
    ) and not force_decompose:
        shard_plan, shard_plan_source = build_deterministic_shard_plan(
            stage_key,
            stage_input,
            truncation_flags=["proactive_boundary_oversplit"],
        )
        if shard_plan:
            log_adaptation_step(
                ctx,
                stage_key=stage_key,
                message=f"Proactive boundary decompose ({len(shard_plan)} shards)",
                action_id="boundary.proactive_decompose",
                extra_detail={"shard_count": len(shard_plan)},
            )
            with logged_step(f"{stage_key}/proactive_decompose", ctx=ctx, stage=stage_key):
                volley, _local = prepare_volley_for_llm(
                    ctx, stage_key, stage_input, profile="full", task_kind="primary"
                )
                envelope, shard_count = run_shards_then_collate(
                    ctx,
                    stage_key=stage_key,
                    prompt_rel=prompt_rel,
                    stage_input=stage_input,
                    shard_plan=shard_plan,
                    parent_attempt=attempt,
                )
                schema_errors = validate_stage_artifacts(stage_key, envelope.get("artifacts") or {})
                arbiter_result = run_llm_arbiter(
                    ctx=ctx,
                    stage_key=stage_key,
                    attempt_number=attempt,
                    envelope=envelope,
                    schema_errors=schema_errors,
                    context_chars=sum(len(m.get("content", "")) for m in volley),
                    truncation_flags=truncation_flags_for_volley(volley),
                    stage_expectations=_arbiter_stage_expectations(stage_key),
                )
                envelope["_routing_meta"] = {
                    "routed_via_collate": True,
                    "shard_plan_source": shard_plan_source,
                    "proactive_decompose": True,
                }
                lint_errors = _post_arbiter_hardening(
                    ctx,
                    stage_key,
                    envelope,
                    arbiter_result,
                    schema_errors,
                    volley=volley,
                    truncation_flags=truncation_flags_for_volley(volley),
                    routed_via_collate=True,
                    stage_input_obligation=obligation,
                )
                envelope.setdefault("_routing_meta", {})["deterministic_lint_errors"] = lint_errors
            return envelope, volley, arbiter_result, schema_errors, shard_count, shard_plan_source

    if (
        stage_key == "segment_classification"
        and should_proactive_decompose_segment_classification(stage_input)
        and not force_decompose
    ):
        shard_plan, shard_plan_source = build_deterministic_shard_plan(
            stage_key,
            stage_input,
            truncation_flags=["proactive_per_segment"],
        )
        if shard_plan:
            log_adaptation_step(
                ctx,
                stage_key=stage_key,
                message=f"Proactive per-segment decompose ({len(shard_plan)} shards)",
                action_id="llm.adaptation.decompose_start",
                extra_detail={"shard_count": len(shard_plan), "trigger": "proactive_per_segment"},
            )
            with logged_step(f"{stage_key}/proactive_decompose", ctx=ctx, stage=stage_key):
                volley, _local = prepare_volley_for_llm(
                    ctx, stage_key, stage_input, profile="full", task_kind="primary"
                )
                envelope, shard_count = run_shards_then_collate(
                    ctx,
                    stage_key=stage_key,
                    prompt_rel=prompt_rel,
                    stage_input=stage_input,
                    shard_plan=shard_plan,
                    parent_attempt=attempt,
                )
                schema_errors = validate_stage_artifacts(stage_key, envelope.get("artifacts") or {})
                arbiter_result = run_llm_arbiter(
                    ctx=ctx,
                    stage_key=stage_key,
                    attempt_number=attempt,
                    envelope=envelope,
                    schema_errors=schema_errors,
                    context_chars=sum(len(m.get("content", "")) for m in volley),
                    truncation_flags=truncation_flags_for_volley(volley),
                    stage_expectations=_arbiter_stage_expectations(stage_key, bump_tier=bump_tier),
                )
                envelope["_routing_meta"] = {
                    "routed_via_collate": True,
                    "shard_plan_source": shard_plan_source,
                    "proactive_decompose": True,
                }
                lint_errors = _post_arbiter_hardening(
                    ctx,
                    stage_key,
                    envelope,
                    arbiter_result,
                    schema_errors,
                    volley=volley,
                    truncation_flags=truncation_flags_for_volley(volley),
                    routed_via_collate=True,
                    stage_input_obligation=obligation,
                )
                envelope.setdefault("_routing_meta", {})["deterministic_lint_errors"] = lint_errors
            return envelope, volley, arbiter_result, schema_errors, shard_count, shard_plan_source

    if force_decompose and stage_key in DECOMPOSE_ELIGIBLE:
        shard_plan, shard_plan_source = build_deterministic_shard_plan(
            stage_key,
            stage_input,
            truncation_flags=["lint_retry_force_decompose"]
            + (["field_truncated"] if clear_field_truncation else []),
        )
        if shard_plan:
            with logged_step(f"{stage_key}/lint_retry_decompose", ctx=ctx, stage=stage_key):
                volley, _local = prepare_volley_for_llm(
                    ctx, stage_key, stage_input, profile="full", task_kind="primary"
                )
                envelope, shard_count = run_shards_then_collate(
                    ctx,
                    stage_key=stage_key,
                    prompt_rel=prompt_rel,
                    stage_input=stage_input,
                    shard_plan=shard_plan,
                    parent_attempt=attempt,
                    context_cap_boost_round=max(int(context_cap_boost_round), 1)
                    if clear_field_truncation
                    else int(context_cap_boost_round),
                    clear_field_truncation=bool(clear_field_truncation),
                )
                schema_errors = validate_stage_artifacts(stage_key, envelope.get("artifacts") or {})
                arbiter_result = run_llm_arbiter(
                    ctx=ctx,
                    stage_key=stage_key,
                    attempt_number=attempt,
                    envelope=envelope,
                    schema_errors=schema_errors,
                    context_chars=sum(len(m.get("content", "")) for m in volley),
                    truncation_flags=truncation_flags_for_volley(volley),
                    stage_expectations=_arbiter_stage_expectations(stage_key, bump_tier=bump_tier),
                )
                envelope["_routing_meta"] = {
                    "routed_via_collate": True,
                    "shard_plan_source": shard_plan_source,
                    "lint_retry_decompose": True,
                }
                lint_errors = _post_arbiter_hardening(
                    ctx,
                    stage_key,
                    envelope,
                    arbiter_result,
                    schema_errors,
                    volley=volley,
                    truncation_flags=truncation_flags_for_volley(volley),
                    routed_via_collate=True,
                    stage_input_obligation=obligation,
                )
                envelope.setdefault("_routing_meta", {})["deterministic_lint_errors"] = lint_errors
            return envelope, volley, arbiter_result, schema_errors, shard_count, shard_plan_source

    with logged_step(f"{stage_key}/prepare_volley", ctx=ctx, stage=stage_key):
        router_outcome = prepare_volley_via_router(
            ctx, stage_key, stage_input, profile="full", task_kind="primary"
        )
        volley, local_framing = router_outcome.volley, router_outcome.framing
        truncation_flags = truncation_flags_for_volley(volley)
    cap_boost_used = 0
    if flow_hardening_enabled() and truncation_flags:
        from interview_mux.truncation_policy import rebuild_volley_clearing_truncation

        # Holistic escalation: rebuild volley with higher caps before decompose/block.
        rebuild = rebuild_volley_clearing_truncation(
            ctx,
            stage_key,
            stage_input,
            profile="full",
            task_kind="primary",
            initial_volley=volley,
            initial_framing=local_framing,
            initial_flags=truncation_flags,
        )
        volley = rebuild.volley
        local_framing = rebuild.framing
        truncation_flags = rebuild.flags
        cap_boost_used = rebuild.boost_round
        if rebuild.cleared:
            ctx.log(
                f"Stage {stage_key}: truncation cleared after cap-boost rebuild "
                f"(round={rebuild.boost_round}, steps={rebuild.steps[:4]})",
                level="info",
                stage=stage_key,
                action_id="truncation.cap_boost_cleared",
                detail={"boost_round": rebuild.boost_round, "steps": rebuild.steps},
            )
        elif stage_key in DECOMPOSE_ELIGIBLE:
            shard_plan, shard_plan_source = build_deterministic_shard_plan(
                stage_key,
                stage_input,
                truncation_flags=truncation_flags or ["field_truncated"],
            )
            if shard_plan:
                ctx.log(
                    f"Stage {stage_key}: truncated evidence after cap boost — "
                    f"auto-escalating to decompose ({', '.join(truncation_flags[:3])}).",
                    level="warning",
                    stage=stage_key,
                    action_id="truncation.auto_decompose",
                    detail={
                        "flags": truncation_flags[:4],
                        "shard_count": len(shard_plan),
                        "boost_round": cap_boost_used,
                    },
                )
                with logged_step(f"{stage_key}/truncation_decompose", ctx=ctx, stage=stage_key):
                    envelope, shard_count = run_shards_then_collate(
                        ctx,
                        stage_key=stage_key,
                        prompt_rel=prompt_rel,
                        stage_input=stage_input,
                        shard_plan=shard_plan,
                        parent_attempt=attempt,
                        context_cap_boost_round=max(cap_boost_used, 1),
                        clear_field_truncation=True,
                    )
                    schema_errors = validate_stage_artifacts(
                        stage_key, envelope.get("artifacts") or {}
                    )
                    arbiter_result = run_llm_arbiter(
                        ctx=ctx,
                        stage_key=stage_key,
                        attempt_number=attempt,
                        envelope=envelope,
                        schema_errors=schema_errors,
                        context_chars=sum(len(m.get("content", "")) for m in volley),
                        truncation_flags=truncation_flags,
                        stage_expectations=_arbiter_stage_expectations(
                            stage_key, bump_tier=True
                        ),
                    )
                    envelope["_routing_meta"] = {
                        "routed_via_collate": True,
                        "shard_plan_source": shard_plan_source,
                        "truncation_auto_decompose": True,
                        "cap_boost_round": cap_boost_used,
                        "cap_boost_steps": rebuild.steps,
                    }
                    lint_errors = _post_arbiter_hardening(
                        ctx,
                        stage_key,
                        envelope,
                        arbiter_result,
                        schema_errors,
                        volley=volley,
                        truncation_flags=truncation_flags_for_volley(volley),
                        routed_via_collate=True,
                        stage_input_obligation=obligation,
                    )
                    envelope.setdefault("_routing_meta", {})[
                        "deterministic_lint_errors"
                    ] = lint_errors
                return (
                    envelope,
                    volley,
                    arbiter_result,
                    schema_errors,
                    shard_count,
                    shard_plan_source,
                )
        if truncation_flags and stage_severity(stage_key) == "high":
            ctx.log(
                f"Stage {stage_key}: high-severity truncation — blocking primary "
                f"after cap-boost exhaustion (flags={', '.join(truncation_flags[:3])}).",
                level="warning",
                stage=stage_key,
                action_id="truncation.blocked",
                detail={"flags": truncation_flags, "boost_steps": rebuild.steps},
            )
            envelope = {
                "status": "blocked",
                "artifacts": {},
                "memory_updates": {},
                "needs": [
                    {
                        "type": "decompose",
                        "stage": stage_key,
                        "reason": f"Evidence truncated: {', '.join(truncation_flags[:3])}",
                        "blocking": True,
                    }
                ],
                "follow_up_investigations": [],
                "reasoning_summary": "Truncation hard-block before primary.",
                "_llm_meta": {
                    "truncation_escalation": {
                        "rounds": cap_boost_used,
                        "steps": rebuild.steps,
                        "final_flags": truncation_flags,
                        "provider": "openai",
                    }
                },
            }
            arbiter_result = {
                "verdict": "decompose",
                "confidence": 0.9,
                "gaps": truncation_flags,
                "shard_plan": [],
                "reasoning_summary": "Flow hardening: high-severity stage with truncated context.",
            }
            return envelope, volley, arbiter_result, [], 0, None

    with logged_step(f"{stage_key}/primary", ctx=ctx, stage=stage_key):
        envelope, volley, schema_errors = _run_primary_with_openai_fallback(
            ctx,
            stage_key,
            prompt_rel,
            volley,
            local_framing=local_framing,
            bump_tier=bump_tier,
            call_attempt=attempt,
            system_appendix=system_appendix,
        )
        truncation_flags = truncation_flags_for_volley(volley)

        if schema_errors and any("envelope" in e.lower() for e in schema_errors):
            arbiter_result = {
                "verdict": "enqueue_investigation",
                "confidence": 0.0,
                "gaps": schema_errors[:3],
                "shard_plan": [],
                "suggested_investigation": {
                    "kind": "envelope_invalid",
                    "question": f"{stage_key}: envelope failed schema before arbiter.",
                    "blocking": True,
                },
                "reasoning_summary": "Skipped arbiter due to envelope/schema failure.",
            }
            envelope["status"] = "blocked"
            return envelope, volley, arbiter_result, schema_errors, 0, None

    with logged_step(f"{stage_key}/arbiter", ctx=ctx, stage=stage_key):
        arbiter_result = run_llm_arbiter(
            ctx=ctx,
            stage_key=stage_key,
            attempt_number=attempt,
            envelope=envelope,
            schema_errors=schema_errors,
            context_chars=sum(len(m.get("content", "")) for m in volley),
            truncation_flags=truncation_flags,
            stage_expectations=_arbiter_stage_expectations(stage_key, bump_tier=bump_tier),
        )

    shard_count = 0
    routed_via_collate = False
    shard_plan_source: str | None = None
    verdict = arbiter_result.get("verdict")

    with logged_step(f"{stage_key}/post_arbiter", ctx=ctx, stage=stage_key):
        if verdict == "retry_uptier" and uptier_budget_remaining(ctx, stage_key) > 0:
            record_uptier_retry(ctx, stage_key)
            router_outcome = prepare_volley_via_router(
                ctx, stage_key, stage_input, profile="full", task_kind="primary"
            )
            volley, local_framing = router_outcome.volley, router_outcome.framing
            uptier_flags = truncation_flags_for_volley(volley)
            if uptier_flags:
                from interview_mux.truncation_policy import rebuild_volley_clearing_truncation

                rebuild = rebuild_volley_clearing_truncation(
                    ctx,
                    stage_key,
                    stage_input,
                    profile="full",
                    task_kind="primary",
                    initial_volley=volley,
                    initial_framing=local_framing,
                    initial_flags=uptier_flags,
                )
                volley, local_framing = rebuild.volley, rebuild.framing
            envelope, volley, schema_errors = _run_primary_with_openai_fallback(
                ctx,
                stage_key,
                prompt_rel,
                volley,
                local_framing=local_framing,
                bump_tier=True,
                call_attempt=attempt,
            )
            truncation_flags = truncation_flags_for_volley(volley)
            arbiter_result = run_llm_arbiter(
                ctx=ctx,
                stage_key=stage_key,
                attempt_number=attempt,
                envelope=envelope,
                schema_errors=schema_errors,
                context_chars=sum(len(m.get("content", "")) for m in volley),
                truncation_flags=truncation_flags,
                stage_expectations=_arbiter_stage_expectations(stage_key, bump_tier=True),
            )
            verdict = arbiter_result.get("verdict")
        if verdict == "retry_uptier":
            if not _try_flagship_uptier_promote(
                ctx,
                stage_key,
                envelope,
                arbiter_result,
                schema_errors,
                volley=volley,
            ):
                envelope.setdefault("follow_up_investigations", [])
                envelope["follow_up_investigations"].append(
                    arbiter_result.get("suggested_investigation")
                    or {
                        "kind": "uptier_exhausted",
                        "question": f"{stage_key}: uptier budget exhausted for this run.",
                        "blocking": True,
                    }
                )
                envelope["status"] = "blocked"

        if verdict == "decompose" and stage_key in DECOMPOSE_ELIGIBLE:
            shard_plan = arbiter_result.get("shard_plan") or []
            shard_plan_source = "arbiter" if shard_plan else None
            if not shard_plan:
                shard_plan, shard_plan_source = build_deterministic_shard_plan(
                    stage_key,
                    stage_input,
                    truncation_flags=truncation_flags,
                )
            if shard_plan:
                envelope, shard_count = run_shards_then_collate(
                    ctx,
                    stage_key=stage_key,
                    prompt_rel=prompt_rel,
                    stage_input=stage_input,
                    shard_plan=shard_plan,
                    parent_attempt=attempt,
                    context_cap_boost_round=max(int(context_cap_boost_round), 1)
                    if (truncation_flags or clear_field_truncation)
                    else int(context_cap_boost_round),
                    clear_field_truncation=bool(
                        clear_field_truncation
                        or bool(truncation_flags)
                    ),
                )
                routed_via_collate = True
                schema_errors = validate_stage_artifacts(stage_key, envelope.get("artifacts") or {})
                arbiter_result = run_llm_arbiter(
                    ctx=ctx,
                    stage_key=stage_key,
                    attempt_number=attempt,
                    envelope=envelope,
                    schema_errors=schema_errors,
                    context_chars=sum(len(m.get("content", "")) for m in volley),
                    truncation_flags=truncation_flags,
                    stage_expectations=_arbiter_stage_expectations(stage_key, bump_tier=bump_tier),
                )
                if str(arbiter_result.get("verdict", "")).strip() != "accept":
                    envelope["status"] = "blocked"
            else:
                envelope.setdefault("follow_up_investigations", [])
                envelope["follow_up_investigations"].append(
                    {
                        "kind": "decompose_no_plan",
                        "question": f"{stage_key}: decompose requested but no shard plan available.",
                        "blocking": True,
                    }
                )
                envelope["status"] = "blocked"
        elif verdict == "decompose":
            envelope.setdefault("follow_up_investigations", [])
            envelope["follow_up_investigations"].append(
                arbiter_result.get("suggested_investigation")
                or {
                    "kind": "decompose_ineligible",
                    "question": f"{stage_key} is not shard/collate eligible.",
                    "blocking": True,
                }
            )
            envelope["status"] = "blocked"
        elif verdict == "enqueue_investigation":
            envelope.setdefault("follow_up_investigations", [])
            suggested = arbiter_result.get("suggested_investigation")
            if suggested:
                envelope["follow_up_investigations"].append(suggested)
            envelope["status"] = "blocked"

        _maybe_enqueue_truncation(ctx, stage_key, truncation_flags, envelope, arbiter_result)
        lint_errors = _post_arbiter_hardening(
            ctx,
            stage_key,
            envelope,
            arbiter_result,
            schema_errors,
            volley=volley,
            truncation_flags=truncation_flags,
            routed_via_collate=routed_via_collate,
            stage_input_obligation=obligation,
        )

        envelope["_routing_meta"] = {
            "routed_via_collate": routed_via_collate,
            "shard_plan_source": shard_plan_source,
            "local_llm": local_framing.to_attempt_meta() if local_framing else None,
            "deterministic_lint_errors": lint_errors,
        }
        if router_outcome is not None:
            attach_router_meta(envelope, router_outcome)
    return envelope, volley, arbiter_result, schema_errors, shard_count, shard_plan_source


def finalize_stage_attempt(
    ctx: RunContext,
    stage_key: str,
    attempt: int,
    envelope: dict[str, Any],
    volley: list[dict[str, str]],
    arbiter_result: dict[str, Any],
    schema_errors: list[str],
    shard_count: int,
    *,
    persist_artifacts: PersistFn | None = None,
    sync_fn: SyncFn | None = None,
) -> None:
    with logged_step(f"{stage_key}/attempt_{attempt}/persist", ctx=ctx, stage=stage_key):
        routing = envelope.get("_routing_meta") or {}
        routed_via_collate = bool(routing.get("routed_via_collate"))
        lint_errors = routing.get("deterministic_lint_errors") or []
        if schema_errors:
            ctx.log(
                f"Stage {stage_key}: validation warnings: {schema_errors[:3]}",
                level="warning",
                stage=stage_key,
            )
        plan = apply_resilience_and_persist(
            ctx,
            stage_key,
            attempt,
            envelope,
            arbiter_result,
            schema_errors,
            lint_errors,
            persist_fn=persist_artifacts,
            sync_fn=sync_fn,
            routed_via_collate=routed_via_collate,
            volley=volley,
        )
        if str((arbiter_result or {}).get("verdict", "")).strip() == "accept":
            from interview_mux.artifact_issue_triage import close_stale_envelope_investigations

            close_stale_envelope_investigations(ctx, stage_key, envelope)
        routing = envelope.get("_routing_meta") or {}
        record_stage_attempt(
            ctx,
            stage_key,
            attempt,
            envelope,
            context_volley=volley,
            task_kind="primary",
            arbiter_result=arbiter_result,
            shard_count=shard_count,
            truncation_flags=truncation_flags_for_volley(volley),
            extra={
                "shard_plan_source": routing.get("shard_plan_source"),
                "routed_via_collate": routed_via_collate,
                "local_llm": routing.get("local_llm"),
                "schema_errors": schema_errors[:8],
                "deterministic_lint_errors": lint_errors,
                "persist_action": routing.get("persist_action"),
                "resilience_report": routing.get("resilience_report"),
                **budget_extra_for_attempt(
                    ctx,
                    stage_key,
                    attempt_signature=build_attempt_signature(
                        envelope, volley, schema_errors, lint_errors
                    ),
                    arbiter_verdict=str((arbiter_result or {}).get("verdict", "")),
                    lint_errors=lint_errors,
                ),
            },
        )
        merge_memory = plan.merge_memory if plan.action in ("partial", "full") else False
        from interview_mux.artifact_issue_triage import run_triage_pipeline, triage_enabled

        if triage_enabled() and plan.action in ("partial", "full"):
            triage_result = run_triage_pipeline(
                ctx,
                stage_key,
                lint_errors=lint_errors,
                schema_errors=schema_errors,
                staged=True,
            )
            routing = envelope.setdefault("_routing_meta", {})
            routing["triage"] = triage_result.summary()
        apply_envelope_to_memory(
            ctx,
            stage_key,
            envelope,
            arbiter_result=arbiter_result,
            merge_memory=merge_memory,
            routed_via_collate=routed_via_collate,
        )
