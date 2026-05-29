"""Unified LLM stage routing: primary, schema, arbiter, uptier, decompose, merge gating."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.analysis_memory import (
    apply_envelope_to_memory,
    enqueue_investigations,
    record_stage_attempt,
    record_uptier_retry,
    should_persist_artifacts,
    uptier_budget_remaining,
)
from interview_mux.config import merged_config
from interview_mux.context_volley import (
    build_message_volley,
    truncation_flags_for_volley,
)
from interview_mux.llm_arbiter import run_llm_arbiter
from interview_mux.llm_shard_plans import DECOMPOSE_ELIGIBLE, build_deterministic_shard_plan
from interview_mux.llm_subtasks import run_shards_then_collate
from interview_mux.model_registry import resolve_model
from interview_mux.prompt_validation import (
    format_validation_feedback,
    validate_envelope,
    validate_stage_artifacts,
)
from interview_mux.run_context import RunContext
from interview_mux.stages.llm_runner import run_prompt_envelope

PersistFn = Callable[[RunContext, dict[str, Any]], None]
SyncFn = Callable[[RunContext, dict[str, Any]], None]


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


def _extend_volley_for_retry(
    volley: list[dict[str, str]],
    envelope: dict[str, Any],
    *,
    schema_errors: list[str] | None = None,
    blocking_needs: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    extended = [*volley, {"role": "assistant", "content": _assistant_summary_from_envelope(envelope)}]
    if schema_errors:
        extended.append({"role": "user", "content": format_validation_feedback(schema_errors)})
    elif blocking_needs:
        lines = ["## Blocking needs from prior attempt", ""]
        for need in blocking_needs:
            lines.append(f"- [{need.get('type')}] {need.get('reason', need.get('question', ''))}")
        extended.append({"role": "user", "content": "\n".join(lines)})
    return extended


def _run_primary_with_volley_retries(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    volley: list[dict[str, str]],
    *,
    bump_tier: bool = False,
) -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
    envelope = run_prompt_envelope(
        stage_key,
        prompt_rel,
        messages=volley,
        ctx=ctx,
        task_kind="primary",
        bump_tier=bump_tier,
    )
    artifacts = envelope.get("artifacts") or {}
    schema_errors = validate_stage_artifacts(stage_key, artifacts)
    envelope_errors = validate_envelope(envelope)
    all_errors = envelope_errors + schema_errors

    retries = 0
    max_retries = _max_volley_retries(ctx)
    while retries < max_retries and all_errors:
        volley = _extend_volley_for_retry(volley, envelope, schema_errors=all_errors)
        envelope = run_prompt_envelope(
            stage_key,
            prompt_rel,
            messages=volley,
            ctx=ctx,
            task_kind="primary",
            bump_tier=bump_tier,
        )
        artifacts = envelope.get("artifacts") or {}
        schema_errors = validate_stage_artifacts(stage_key, artifacts)
        envelope_errors = validate_envelope(envelope)
        all_errors = envelope_errors + schema_errors
        retries += 1

    status = envelope.get("status", "complete")
    blocking_needs = [
        n for n in envelope.get("needs") or [] if n.get("blocking") and n.get("type") != "operator"
    ]
    if retries < max_retries and status in ("partial", "needs_input") and (blocking_needs or not artifacts):
        volley = _extend_volley_for_retry(volley, envelope, blocking_needs=blocking_needs)
        envelope = run_prompt_envelope(
            stage_key,
            prompt_rel,
            messages=volley,
            ctx=ctx,
            task_kind="primary",
            bump_tier=bump_tier,
        )
        artifacts = envelope.get("artifacts") or {}
        schema_errors = validate_stage_artifacts(stage_key, artifacts)
        envelope_errors = validate_envelope(envelope)
        all_errors = envelope_errors + schema_errors

    return envelope, volley, all_errors


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


def run_llm_stage_with_routing(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    stage_input: dict[str, Any],
    *,
    attempt: int = 1,
    bump_tier: bool = False,
) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, Any], list[str], int, str | None]:
    """
    Run primary → validate → arbiter → optional uptier/decompose.
    Returns (envelope, volley, arbiter_result, schema_errors, shard_count, shard_plan_source).
    """
    volley = build_message_volley(ctx, stage_key, stage_input)
    envelope, volley, schema_errors = _run_primary_with_volley_retries(
        ctx, stage_key, prompt_rel, volley, bump_tier=bump_tier
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

    default_tier = resolve_model(stage_key, "primary").tier
    arbiter_result = run_llm_arbiter(
        stage_key=stage_key,
        attempt_number=attempt,
        envelope=envelope,
        schema_errors=schema_errors,
        context_chars=sum(len(m.get("content", "")) for m in volley),
        truncation_flags=truncation_flags,
        stage_expectations={
            "severity": "high" if default_tier == "flagship" else "medium",
            "default_tier": default_tier,
            "decompose_eligible": stage_key in DECOMPOSE_ELIGIBLE,
        },
    )

    shard_count = 0
    routed_via_collate = False
    shard_plan_source: str | None = None
    verdict = arbiter_result.get("verdict")

    if verdict == "retry_uptier" and uptier_budget_remaining(ctx, stage_key) > 0:
        record_uptier_retry(ctx, stage_key)
        envelope, volley, schema_errors = _run_primary_with_volley_retries(
            ctx, stage_key, prompt_rel, volley, bump_tier=True
        )
        truncation_flags = truncation_flags_for_volley(volley)
        arbiter_result = run_llm_arbiter(
            stage_key=stage_key,
            attempt_number=attempt,
            envelope=envelope,
            schema_errors=schema_errors,
            context_chars=sum(len(m.get("content", "")) for m in volley),
            truncation_flags=truncation_flags,
            stage_expectations={
                "severity": "high" if default_tier == "flagship" else "medium",
                "default_tier": resolve_model(stage_key, "primary", bump_tier=True).tier,
                "decompose_eligible": stage_key in DECOMPOSE_ELIGIBLE,
            },
        )
        verdict = arbiter_result.get("verdict")
    elif verdict == "retry_uptier":
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
            )
            routed_via_collate = True
            schema_errors = validate_stage_artifacts(stage_key, envelope.get("artifacts") or {})
            arbiter_result = {**arbiter_result, "verdict": "accept", "reasoning_summary": "Collate merged shards."}
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

    envelope["_routing_meta"] = {
        "routed_via_collate": routed_via_collate,
        "shard_plan_source": shard_plan_source,
    }
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
    routing = envelope.get("_routing_meta") or {}
    routed_via_collate = bool(routing.get("routed_via_collate"))
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
        },
    )
    artifacts = envelope.get("artifacts") or {}
    if schema_errors:
        ctx.log(
            f"Stage {stage_key}: validation warnings: {schema_errors[:3]}",
            level="warning",
            stage=stage_key,
        )
    if persist_artifacts and should_persist_artifacts(
        arbiter_result,
        envelope,
        schema_errors,
        routed_via_collate=routed_via_collate,
    ):
        persist_artifacts(ctx, artifacts)
        if sync_fn:
            sync_fn(ctx, artifacts)
    apply_envelope_to_memory(
        ctx,
        stage_key,
        envelope,
        arbiter_result=arbiter_result,
        routed_via_collate=routed_via_collate,
    )
