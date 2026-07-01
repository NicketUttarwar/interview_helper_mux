"""On-device volley framing before OpenAI calls (with fail-safe escalation)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from interview_mux.analysis_memory import load_analysis_state
from interview_mux.config import merged_config
from interview_mux.context_volley import (
    apply_local_framing_to_volley,
    build_message_volley,
    plan_for_stage,
    truncation_flags_for_volley,
)
from interview_mux.local_llm_config import (
    LOCAL_FRAMER_PROMPT,
    force_escalate_stage,
    max_volley_turns,
    min_confidence,
    should_frame_task_kind,
)
from interview_mux.local_llm_runner import generate_local_chat, mlx_available
from interview_mux.truncation_policy import should_skip_framer_injection, validate_framer_turns
from interview_mux.run_context import RunContext
from interview_mux.stages.llm_runner import _extract_json, load_system_prompt


@dataclass
class LocalFramingResult:
    escalate: bool = True
    confidence: float = 0.0
    reason: str = ""
    volley_turns: list[dict[str, str]] = field(default_factory=list)
    used_local: bool = False
    fallback: str | None = None
    model_id: str | None = None
    latency_ms: int | None = None
    tokens_approx: int | None = None
    volley_turn_count: int = 0
    digest_truncated: bool = False

    def to_attempt_meta(self) -> dict[str, Any]:
        return {
            "escalate": self.escalate,
            "confidence": self.confidence,
            "reason": self.reason,
            "used_local": self.used_local,
            "fallback": self.fallback,
            "model_id": self.model_id,
            "volley_turn_count": self.volley_turn_count,
            "latency_ms": self.latency_ms,
            "tokens_approx": self.tokens_approx,
            "digest_truncated": self.digest_truncated,
        }


def parse_framer_response(raw: str, *, max_turns: int) -> dict[str, Any]:
    data = _extract_json(raw)
    turns: list[dict[str, str]] = []
    for item in data.get("volley_turns") or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            turns.append({"role": role, "content": content})
        if len(turns) >= max_turns:
            break
    confidence = data.get("confidence")
    try:
        conf_f = float(confidence) if confidence is not None else 0.0
    except (TypeError, ValueError):
        conf_f = 0.0
    return {
        "escalate": bool(data.get("escalate", True)),
        "confidence": max(0.0, min(1.0, conf_f)),
        "reason": str(data.get("reason", "") or ""),
        "volley_turns": turns,
    }


def must_escalate_to_openai(
    stage_key: str,
    *,
    severity: str,
    truncation_flags: list[str],
    operator_verified: bool,
    parsed: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Code-level escalation rules (in addition to model output)."""
    if severity == "high":
        return True, "high_severity_stage"
    if force_escalate_stage(stage_key):
        return True, "p0_p2_quality_first_stage"
    if truncation_flags:
        return True, f"truncation:{','.join(truncation_flags)}"
    if operator_verified:
        return True, "operator_verified_profile"
    if parsed is not None:
        if parsed.get("confidence", 0) < min_confidence(cfg):
            return True, "low_local_confidence"
        if not parsed.get("volley_turns") and not parsed.get("escalate"):
            return True, "empty_volley_turns"
    return False, ""


def frame_volley_with_local(
    ctx: RunContext,
    stage_key: str,
    stage_input: dict[str, Any],
    base_volley: list[dict[str, str]],
    *,
    task_kind: str = "primary",
    profile: str = "full",
    cfg: dict[str, Any] | None = None,
) -> LocalFramingResult:
    """
    Run local MLX framer. Propagates failures; callers fall back to OpenAI only when MLX is unavailable.
    """
    resolved_cfg = cfg or merged_config()
    if not mlx_available():
        return LocalFramingResult(
            escalate=True,
            reason="mlx_unavailable",
            fallback="mlx_unavailable",
        )

    severity = stage_severity(stage_key)
    state = load_analysis_state(ctx)
    operator_verified = bool((state.get("meta") or {}).get("operator_verified"))
    trunc_flags = truncation_flags_for_volley(base_volley)

    force, force_reason = must_escalate_to_openai(
        stage_key,
        severity=severity,
        truncation_flags=trunc_flags,
        operator_verified=operator_verified,
        cfg=resolved_cfg,
    )

    plan = plan_for_stage(stage_key)
    digest, digest_truncated = _build_framer_digest(stage_input, stage_key, cfg=resolved_cfg)
    user_blob = _build_framer_user_blob(
        ctx,
        stage_key,
        stage_input,
        plan=plan,
        severity=severity,
        task_kind=task_kind,
        profile=profile,
        base_volley=base_volley,
        truncation_flags=trunc_flags,
        cfg=resolved_cfg,
        stage_input_digest=digest,
        digest_truncated=digest_truncated,
    )

    try:
        system = load_system_prompt(LOCAL_FRAMER_PROMPT, include_preamble=False)
        raw, run_meta = generate_local_chat(
            system=system,
            user=user_blob,
            ctx=ctx,
            stage_key=stage_key,
            task_kind=f"local_{task_kind}",
            cfg=resolved_cfg,
        )
        parsed = parse_framer_response(raw, max_turns=max_volley_turns(resolved_cfg))
        turns, rejected = validate_framer_turns(
            list(parsed.get("volley_turns") or []),
            stage_input,
            stage_key=stage_key,
        )
        if rejected:
            parsed["volley_turns"] = turns
            if not turns:
                parsed["escalate"] = True
                parsed["reason"] = "framer_turns_rejected"
        _record_local_call(
            ctx, stage_key, system, user_blob, raw, parsed, task_kind=task_kind, run_meta=run_meta
        )

        code_force, code_reason = must_escalate_to_openai(
            stage_key,
            severity=severity,
            truncation_flags=trunc_flags,
            operator_verified=operator_verified,
            parsed=parsed,
            cfg=resolved_cfg,
        )
        escalate = bool(parsed.get("escalate")) or code_force
        reason = code_reason or parsed.get("reason") or ("model_escalate" if parsed.get("escalate") else "")
        return LocalFramingResult(
            escalate=escalate,
            confidence=float(parsed.get("confidence", 0)),
            reason=reason,
            volley_turns=list(parsed.get("volley_turns") or []),
            used_local=True,
            model_id=run_meta.get("model_id"),
            latency_ms=run_meta.get("latency_ms"),
            tokens_approx=run_meta.get("tokens_approx"),
            volley_turn_count=len(parsed.get("volley_turns") or []),
            digest_truncated=digest_truncated,
        )
    except Exception as exc:
        ctx.log(
            f"Local LLM framing failed for {stage_key}: {exc}",
            level="error",
            stage=stage_key,
        )
        raise


def prepare_volley_for_llm(
    ctx: RunContext,
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    profile: str = "full",
    task_kind: str = "primary",
    cfg: dict[str, Any] | None = None,
) -> tuple[list[dict[str, str]], LocalFramingResult | None]:
    """
    Build message volley, optionally compress via local MLX, always suitable for OpenAI fallback.
    """
    resolved_cfg = cfg or merged_config()
    volley = build_message_volley(ctx, stage_key, stage_input, profile=profile)
    if not should_frame_task_kind(task_kind, profile, resolved_cfg):
        return volley, None

    try:
        framing = frame_volley_with_local(
            ctx,
            stage_key,
            stage_input,
            volley,
            task_kind=task_kind,
            profile=profile,
            cfg=resolved_cfg,
        )
    except Exception as exc:
        ctx.log(
            f"Local LLM framing failed for {stage_key}: {exc} — escalating to OpenAI volley",
            level="error",
            stage=stage_key,
            detail={"fallback": "local_framing_failed", "error_class": type(exc).__name__},
        )
        return volley, LocalFramingResult(
            escalate=True,
            reason=f"local_framing_failed:{exc}",
            fallback="local_framing_failed",
        )

    if framing.used_local and framing.volley_turns:
        plan = plan_for_stage(stage_key)
        prior_lines = []
        state = load_analysis_state(ctx)
        summaries = (state.get("meta") or {}).get("stage_summaries") or {}
        for ps in plan.prior_stages[:4]:
            if ps in summaries and summaries[ps]:
                prior_lines.append({ps: summaries[ps][:400]})
        skip, skip_reason = should_skip_framer_injection(
            framing,
            stage_key=stage_key,
            prior_one_liners=prior_lines,
            cfg=resolved_cfg,
        )
        if skip:
            ctx.log(
                f"Local LLM framing skipped injection for {stage_key} ({skip_reason})",
                level="info",
                stage=stage_key,
            )
        else:
            volley = apply_local_framing_to_volley(volley, framing.volley_turns)
            try:
                from interview_mux.context_resolver import (
                    append_local_framing_entry,
                    context_index_enabled,
                    write_on_accept,
                )

                if context_index_enabled() and write_on_accept():
                    attempt = 1
                    orch_path = ctx.path("understanding", "analysis_orchestration.json")
                    if orch_path.is_file():
                        attempt = int(
                            (ctx.read_json("understanding/analysis_orchestration.json").get("stage_attempts") or {}).get(
                                stage_key, 1
                            )
                        )
                    append_local_framing_entry(
                        ctx,
                        stage_key=stage_key,
                        attempt=attempt,
                        turns=framing.volley_turns,
                        model_id=framing.model_id,
                    )
            except Exception:
                pass
            if framing.escalate and framing.reason:
                ctx.log(
                    f"Local LLM framed {stage_key} volley ({framing.volley_turn_count} turns); "
                    f"escalating to OpenAI: {framing.reason}",
                    level="info",
                    stage=stage_key,
                )
    elif framing.fallback:
        ctx.log(
            f"Local LLM skipped for {stage_key} ({framing.fallback}); OpenAI volley unchanged.",
            level="debug",
            stage=stage_key,
        )
    return volley, framing


def _build_framer_digest(stage_input: dict[str, Any], stage_key: str, *, cfg: dict[str, Any]) -> tuple[str, bool]:
    from interview_mux.truncation_policy import build_framer_digest

    return build_framer_digest(stage_input, stage_key, cfg=cfg)


def _build_framer_user_blob(
    ctx: RunContext,
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    plan: Any,
    severity: str,
    task_kind: str,
    profile: str,
    base_volley: list[dict[str, str]],
    truncation_flags: list[str],
    cfg: dict[str, Any],
    stage_input_digest: str,
    digest_truncated: bool = False,
) -> str:
    state = load_analysis_state(ctx)
    summaries = (state.get("meta") or {}).get("stage_summaries") or {}
    prior_lines = []
    for ps in plan.prior_stages[:4]:
        if ps in summaries and summaries[ps]:
            prior_lines.append({ps: summaries[ps][:400]})
    digest = stage_input_digest
    if digest_truncated and "framer_digest_truncated" not in truncation_flags:
        truncation_flags = [*truncation_flags, "framer_digest_truncated"]
    spine_hits: list[dict[str, Any]] = []
    from interview_mux.interview_spine.config import spine_enabled
    from interview_mux.interview_spine.retrieval import query_spine

    if spine_enabled():
        query = plan.task_line or stage_key.replace("_", " ")
        spine_hits = query_spine(ctx, query, top_k=3)[:3]
        for hit in spine_hits:
            text = str(hit.get("text_span") or "")
            if len(text) > 120:
                hit["text_span"] = text[:117] + "…"
    payload = {
        "stage_key": stage_key,
        "task_kind": task_kind,
        "profile": profile,
        "severity": severity,
        "task_line": plan.task_line,
        "prior_one_liners": prior_lines,
        "truncation_flags": truncation_flags,
        "volley_budget": max_volley_turns(cfg),
        "base_volley_turn_count": len(base_volley),
        "stage_input_digest": digest,
        "spine_retrieval_hits": spine_hits,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _record_local_call(
    ctx: RunContext,
    stage_key: str,
    system: str,
    user: str,
    raw: str,
    parsed: dict[str, Any],
    *,
    task_kind: str,
    run_meta: dict[str, Any] | None = None,
) -> None:
    from interview_mux.llm_call_record import llm_call_records_enabled, record_llm_call
    from interview_mux.local_llm_config import resolve_model_id

    if not llm_call_records_enabled():
        return
    model_id = resolve_model_id()
    meta = run_meta or {}
    record_llm_call(
        ctx,
        stage_key=stage_key,
        prompt_ref=LOCAL_FRAMER_PROMPT,
        request_messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        raw_response=raw,
        parsed_envelope=parsed,
        task_kind=f"local_{task_kind}",
        model_id=model_id,
        model_tier="local",
        provider="local_mlx",
        truncation_flags=parsed.get("truncation_flags"),
        verification=meta.get("verification") if isinstance(meta.get("verification"), dict) else None,
        interaction_id=meta.get("interaction_id"),
    )
