from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from interview_mux.config import merged_config, repo_root, require_secret
from interview_mux.model_registry import resolve_model, temperature_for_chat
from interview_mux.run_context import RunContext

from interview_mux.prompt_examples import (
    COMPACT_EXAMPLE_MAX_CHARS,
    COMPACT_EXAMPLE_MAX_CHARS_BY_STAGE,
    STAGE_EXAMPLE_FILES,
    load_compact_examples,
    prompt_examples_enabled,
    prompt_path,
)

PREAMBLE_REL = "_shared/analysis-preamble.system.txt"
VO_REGISTER_REL = "_shared/synthetic-vo-register.system.txt"
VO_REGISTER_STAGES = frozenset(
    {
        "nugget_layup_compose",
        "gap_framing_compose",
        "gap_framing_recompose",
        "optimal_questions",
        "transitions",
        "vo_line_adjudicate",
        "high_gap_vo_fill",
        "synthetic_framing_plan",
    }
)
ENVELOPE_KEYS = frozenset(
    {
        "status",
        "artifacts",
        "memory_updates",
        "needs",
        "follow_up_investigations",
        "confidence",
        "reasoning_summary",
    }
)


def _synthetic_vo_register_block() -> str:
    """Topic-forward synthetic VO register (shared across compose/adjudicate stages)."""
    path = prompt_path(*VO_REGISTER_REL.split("/"))
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _prompt_thresholds_block() -> str:
    """Canonical numeric limits from config (aligned with logic-tree.md)."""
    th = (merged_config().get("analysis") or {}).get("prompt_thresholds") or {}
    return (
        "## Pipeline thresholds (authoritative)\n"
        f"- Pause-based split: ≥ {th.get('pause_split_ms', 1000)} ms between words\n"
        f"- Short interviewer question (keep with answer): ≤ {th.get('short_question_max_words', 12)} words\n"
        f"- VO question max words: {th.get('interviewer_question_max_words', 60)}\n"
        f"- VO setup max words: {th.get('interviewer_setup_max_words', 20)}\n"
        f"- Highlight setup VO max: {th.get('highlight_setup_max_sec', 8)} seconds\n"
        f"- Max narrative chapters: {th.get('max_chapters', 8)}\n"
        f"- Max highlight clips: {th.get('max_highlight_clips', 5)}\n"
    )


def load_system_prompt(rel_path: str, *, include_preamble: bool = True) -> str:
    p = prompt_path(*rel_path.split("/"))
    if not p.is_file():
        raise FileNotFoundError(f"Prompt not found: {p}")
    body = p.read_text(encoding="utf-8")
    if not include_preamble:
        return body.strip() + "\n\n" + _prompt_thresholds_block()
    pre = prompt_path(*PREAMBLE_REL.split("/"))
    parts = []
    if pre.is_file():
        parts.append(pre.read_text(encoding="utf-8").strip())
    parts.append(_prompt_thresholds_block().strip())
    parts.append(body.strip())
    return "\n\n---\n\n".join(parts)


def load_system_prompt_for_stage(
    rel_path: str,
    stage_key: str,
    *,
    include_preamble: bool = True,
    cfg: dict[str, Any] | None = None,
    task_kind: str = "primary",
    ctx: RunContext | None = None,
) -> str:
    from interview_mux.required_response_format import build_required_response_block

    system = load_system_prompt(rel_path, include_preamble=include_preamble)
    if stage_key in VO_REGISTER_STAGES:
        register = _synthetic_vo_register_block()
        if register:
            system = f"{system}\n\n---\n\n{register}"
    try:
        from interview_mux.homunculus.prompts import perspective_block_for_stage
        from interview_mux.homunculus.runtime import has_homunculus_features

        if ctx is not None and has_homunculus_features(ctx):
            extra = perspective_block_for_stage(stage_key)
            if extra:
                system = f"{system}\n\n---\n\n{extra}"
    except Exception:
        pass
    if prompt_examples_enabled(stage_key, cfg):
        examples = load_compact_examples(stage_key, cfg)
        if examples:
            system = f"{system}\n\n---\n\n{examples}"
    if include_preamble or task_kind == "arbiter":
        system = (
            f"{system}\n\n---\n\n"
            f"{build_required_response_block(stage_key, variant='full', task_kind=task_kind)}"
        )
    return system


def _strip_json_fences(text: str) -> str:
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)```\s*$", stripped, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return stripped


def _extract_json(text: str) -> dict[str, Any]:
    text = _strip_json_fences(text)
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    candidates: list[tuple[int, dict[str, Any]]] = []
    for match in re.finditer(r"\{[\s\S]*?\}(?=\s*$|\s*```|\s*\{)", text):
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                score = len(match.group())
                if "status" in parsed or "artifacts" in parsed:
                    score += 10_000
                candidates.append((score, parsed))
        except json.JSONDecodeError:
            continue
    if not candidates:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError(f"No JSON object in model response: {text[:200]}")
        return json.loads(match.group())
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _default_response_format(
    stage_key: str,
    task_kind: str,
    explicit: dict[str, Any] | None,
    *,
    cfg: dict[str, Any] | None = None,
    volley_retry_index: int = 0,
) -> dict[str, Any] | None:
    if explicit is not None:
        return explicit
    if task_kind in ("primary", "shard", "collate", "specialist", "arbiter"):
        from interview_mux.openai_structured_output import resolve_response_format

        return resolve_response_format(stage_key, task_kind, cfg=cfg)
    return None


def normalize_envelope(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept full envelope or legacy flat stage JSON."""
    if "artifacts" in raw or "status" in raw:
        from interview_mux.prompt_validation import coerce_envelope_status

        env = dict(raw)
        env.setdefault("status", "complete")
        env.setdefault("artifacts", raw.get("artifacts") or {})
        env.setdefault("memory_updates", raw.get("memory_updates") or {})
        env.setdefault("needs", raw.get("needs") or [])
        env.setdefault("follow_up_investigations", raw.get("follow_up_investigations") or [])
        if not env["artifacts"]:
            legacy = {k: v for k, v in raw.items() if k not in ENVELOPE_KEYS}
            if legacy:
                env["artifacts"] = legacy
        conf = env.get("confidence")
        try:
            env["confidence"] = float(conf) if conf is not None else 0.0
        except (TypeError, ValueError):
            env["confidence"] = 0.0
        return coerce_envelope_status(env)
    conf_raw = raw.get("confidence") if isinstance(raw, dict) else None
    try:
        confidence = float(conf_raw) if conf_raw is not None else 0.0
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "status": "complete",
        "artifacts": raw,
        "memory_updates": {},
        "needs": [],
        "follow_up_investigations": [],
        "confidence": confidence,
        "reasoning_summary": "",
    }


def _truncation_blocked_envelope(
    stage_key: str,
    task_kind: str,
    *,
    flags: list[str],
    esc_meta: Any,
) -> dict[str, Any]:
    need_type = "decompose" if task_kind in ("primary", "shard") else "rerun_stage"
    return {
        "status": "blocked",
        "artifacts": {},
        "memory_updates": {},
        "needs": [
            {
                "type": need_type,
                "stage": stage_key,
                "reason": f"LLM input truncated: {', '.join(flags[:3])}",
                "blocking": True,
            }
        ],
        "follow_up_investigations": [],
        "confidence": 0.0,
        "reasoning_summary": f"Blocked: truncated LLM input ({', '.join(flags[:3])})",
        "_llm_meta": {
            "task_kind": task_kind,
            "truncation_escalation": esc_meta.to_dict(),
        },
    }


def _chat_client() -> Any:
    """The OpenAI client, or an offline stub when MUX_STUB_LLM=1.

    The stub exists so the whole 72-stage pipeline can be traversed with no API
    key and no network: everything around this call (prompt assembly, model
    resolution, response-format selection, envelope normalisation, schema
    validation, the retry ladder, call recording) still runs for real. With the
    env var unset this is exactly the previous expression, including the
    require_secret() failure when no key is configured.
    """
    from interview_mux.stub_llm import stub_enabled

    if stub_enabled():
        from interview_mux.stub_llm import StubOpenAI

        return StubOpenAI()
    return OpenAI(api_key=require_secret("OPENAI_API_KEY"))


def _execute_openai_envelope_call(
    stage_key: str,
    prompt_rel: str,
    user_content: str | None,
    *,
    model: str | None,
    ctx: RunContext | None,
    include_preamble: bool,
    messages: list[dict[str, str]] | None,
    task_kind: str,
    bump_tier: bool,
    explicit_tier: str | None,
    response_format: dict[str, Any] | None,
    call_attempt: int | None,
    record_stage_key: str | None,
    system_override: str | None,
    volley_retry_index: int,
    esc_meta: Any | None = None,
    safe_prune_retry: bool = False,
) -> dict[str, Any]:
    """
    Call OpenAI with either:
    - `messages`: full user/assistant volley (recommended; system added here), or
    - `user_content`: legacy single user JSON blob.
    """
    client = _chat_client()
    cfg = merged_config()
    if system_override is not None:
        system = system_override
    else:
        system = load_system_prompt_for_stage(
            prompt_rel,
            stage_key,
            include_preamble=include_preamble,
            cfg=cfg,
            task_kind=task_kind,
            ctx=ctx,
        )
    resolved = (
        None
        if model
        else resolve_model(
            stage_key,
            task_kind=task_kind,
            bump_tier=bump_tier,
            explicit_tier=explicit_tier,
        )
    )
    chosen = model or (resolved.model_id if resolved else None) or "gpt-4o-mini"

    if messages:
        rest = messages[1:] if messages and messages[0].get("role") == "system" else messages
        chat_messages: list[dict[str, str]] = [{"role": "system", "content": system}, *rest]
    elif user_content is not None:
        chat_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
    else:
        raise ValueError("Provide messages volley or user_content")

    kwargs: dict[str, Any] = {
        "model": chosen,
        "messages": chat_messages,
    }
    temp = temperature_for_chat(chosen, task_kind)
    if (call_attempt or 0) > 1 or volley_retry_index > 0:
        if temp is not None:
            temp = 0.0
    if temp is not None:
        kwargs["temperature"] = temp
    fmt = _default_response_format(
        stage_key,
        task_kind,
        response_format,
        cfg=cfg,
        volley_retry_index=volley_retry_index,
    )
    if fmt:
        kwargs["response_format"] = fmt
    if ctx and task_kind in ("primary", "shard", "collate", "specialist"):
        from interview_mux.llm_preflight import SchemaPreflightError, run_schema_preflight

        schema_errors = run_schema_preflight(stage_key, task_kind)
        if schema_errors:
            msg = "; ".join(schema_errors[:3])
            if ctx:
                ctx.log(
                    f"Schema preflight failed ({stage_key}): {msg}",
                    level="error",
                    stage=stage_key,
                    action_id="llm.schema_preflight_fail",
                )
            raise SchemaPreflightError(msg)
    if ctx:
        from interview_mux.operator_trace import log_api_call

        from interview_mux.stage_input_helpers import truncation_flags_for_volley

        volley_for_flags = messages or []
        log_api_call(
            "OpenAI",
            f"chat.completions ({chosen}, {task_kind})",
            ctx=ctx,
            stage=stage_key,
            detail={
                "model_id": chosen,
                "model": chosen,
                "task_kind": task_kind,
                "stage_key": stage_key,
                "turns": len(chat_messages),
                "context_chars": sum(len(m.get("content", "")) for m in chat_messages),
                "truncation_flags": truncation_flags_for_volley(volley_for_flags),
                "volley_retry_index": volley_retry_index,
            },
        )
    try:
        from interview_mux.homunculus.loop import nested_chat_create

        if ctx is not None:
            resp = nested_chat_create(ctx, record_stage_key or stage_key, client, kwargs)
        else:
            resp = client.chat.completions.create(**kwargs)
    except Exception as exc:
        from interview_mux.safe_pruning import (
            SAFE_PRUNE_EXTRACT_KIND,
            SafePruneExhausted,
            is_context_length_error,
            is_safe_prune_retry,
            maybe_safe_prune_after_context_length,
            safe_pruning_enabled,
        )

        if is_context_length_error(exc) and task_kind != SAFE_PRUNE_EXTRACT_KIND and model is None:
            flagship_id = resolve_model(
                stage_key, task_kind=task_kind, explicit_tier="flagship"
            ).model_id
            already_flagship = chosen == flagship_id or explicit_tier == "flagship"
            if not already_flagship and not safe_prune_retry:
                return _execute_openai_envelope_call(
                    stage_key,
                    prompt_rel,
                    user_content,
                    model=None,
                    ctx=ctx,
                    include_preamble=include_preamble,
                    messages=messages,
                    task_kind=task_kind,
                    bump_tier=False,
                    explicit_tier="flagship",
                    response_format=response_format,
                    call_attempt=call_attempt,
                    record_stage_key=record_stage_key,
                    system_override=system_override,
                    volley_retry_index=volley_retry_index,
                    esc_meta=esc_meta,
                    safe_prune_retry=False,
                )
            if (
                safe_pruning_enabled()
                and not safe_prune_retry
                and not is_safe_prune_retry()
            ):
                return maybe_safe_prune_after_context_length(
                    stage_key=stage_key,
                    prompt_rel=prompt_rel,
                    user_content=user_content,
                    messages=messages,
                    original_system=system,
                    ctx=ctx,
                    include_preamble=include_preamble,
                    task_kind=task_kind,
                    response_format=response_format,
                    call_attempt=call_attempt,
                    record_stage_key=record_stage_key,
                    system_override=system_override,
                    volley_retry_index=volley_retry_index,
                    esc_meta=esc_meta,
                )
            raise SafePruneExhausted(
                f"context window exceeded after safe-prune ladder ({stage_key})"
            ) from exc
        if ctx:
            from interview_mux.operator_trace import log_failure

            log_failure(
                f"OpenAI chat.completions failed ({chosen}, {task_kind})",
                exc,
                ctx=ctx,
                stage=stage_key,
                detail={"provider": "OpenAI", "model": chosen, "task_kind": task_kind},
            )
        raise
    content = resp.choices[0].message.content or ""
    try:
        envelope = normalize_envelope(_extract_json(content))
    except (ValueError, json.JSONDecodeError) as exc:
        if ctx:
            # One attempt's malformed reply, not the stage's failure: the
            # ladder above repairs or retries, and the stage reports its own
            # error if every attempt fails (exec_066: recovered in six
            # seconds, yet the line failed the run verdict; ISSUES 109).
            ctx.log(
                f"LLM parse failed ({stage_key}, {task_kind}): {exc}",
                level="warning",
                stage=stage_key,
                action_id="llm.parse_failed",
                detail={
                    "raw_response_prefix": content[:2000],
                    "model_id": chosen,
                    "task_kind": task_kind,
                    "turns": len(chat_messages),
                },
                origin="pipeline",
            )
        raise

    from interview_mux.llm_interaction_registry import resolve_interaction_id
    from interview_mux.llm_response_verify import verification_to_record_dict, verify_llm_response
    from interview_mux.openai_structured_output import structured_outputs_cfg

    interaction_id = resolve_interaction_id(
        stage_key=stage_key,
        task_kind=task_kind,
        record_stage_key=record_stage_key,
        volley_retry_index=volley_retry_index,
        provider="openai",
    )
    verify_target = envelope if task_kind == "arbiter" else envelope
    if task_kind == "arbiter":
        verify_target = envelope.get("artifacts") or envelope

    from interview_mux.llm_output_normalizer import normalize_llm_response

    norm_result = normalize_llm_response(
        ctx,
        interaction_id=interaction_id,
        parsed=envelope,
        stage_key=record_stage_key or stage_key,
        task_kind=task_kind,
        volley=messages,
    )
    envelope = norm_result.normalized
    verify_target = envelope if task_kind != "arbiter" else (envelope.get("artifacts") or envelope)

    verification = verify_llm_response(
        interaction_id,
        verify_target,
        stage_key=record_stage_key or stage_key,
        task_kind=task_kind,
    )
    so_cfg = structured_outputs_cfg(cfg)
    if not verification.ok:
        envelope.setdefault("_llm_meta", {})
        envelope["_llm_meta"]["verification_errors"] = verification.errors[:10]
        if so_cfg.get("log_verification_to_gui", True) and ctx:
            ctx.log(
                f"LLM verification failed ({stage_key}, {interaction_id}): "
                f"{verification.errors[:2]}",
                level="warning",
                stage=stage_key,
                action_id="llm.verification_failed",
                detail={
                    "interaction_id": interaction_id,
                    "schema_name": verification.schema_name,
                    "errors": verification.errors[:5],
                },
            )
        if so_cfg.get("fail_on_verify_error", True) and task_kind != "safe_prune_extract":
            raise ValueError(
                f"LLM response failed schema verification ({interaction_id}): "
                f"{verification.errors[:3]}"
            )
    tier = resolved.tier if resolved else ("explicit" if model else "economy")
    envelope["_llm_meta"] = {
        **(envelope.get("_llm_meta") or {}),
        "model_id": chosen,
        "model_tier": tier,
        "task_kind": task_kind,
        "interaction_id": interaction_id,
        "verification": verification_to_record_dict(verification),
    }
    if ctx:
        from interview_mux.stage_input_helpers import truncation_flags_for_volley
        from interview_mux.llm_call_record import llm_call_records_enabled, record_llm_call

        if llm_call_records_enabled():
            volley_for_flags = messages or []
            call_record = record_llm_call(
                ctx,
                stage_key=stage_key,
                record_stage_key=record_stage_key,
                prompt_ref=prompt_rel,
                request_messages=chat_messages,
                raw_response=content,
                parsed_envelope=envelope,
                task_kind=task_kind,
                model_id=chosen,
                model_tier=tier,
                provider="openai",
                call_attempt=call_attempt,
                temperature=kwargs.get("temperature"),
                response_format=fmt,
                truncation_flags=truncation_flags_for_volley(volley_for_flags),
                verification=verification_to_record_dict(verification),
                interaction_id=interaction_id,
            )
            llm_path = (call_record.get("links") or {}).get("relative_path")
            if llm_path:
                envelope["_llm_meta"]["llm_call_path"] = llm_path
    if ctx:
        turns = len(messages) if messages else 1
        chars = sum(len(m.get("content", "")) for m in (messages or []))
        llm_path = (envelope.get("_llm_meta") or {}).get("llm_call_path")
        ctx.log(
            f"LLM {stage_key}: status={envelope.get('status')} "
            f"needs={len(envelope.get('needs') or [])} "
            f"context_turns={turns} context_chars≈{chars}",
            level="success",
            stage=stage_key,
            action_id="llm.success",
            detail={
                "journey_kind": "execute",
                "model": chosen,
                "task_kind": task_kind,
                **({"llm_call_path": llm_path} if llm_path else {}),
            },
        )
    if esc_meta is not None:
        from interview_mux.truncation_policy import attach_truncation_meta

        attach_truncation_meta(envelope, esc_meta)
    return envelope


def run_prompt_envelope(
    stage_key: str,
    prompt_rel: str,
    user_content: str | None = None,
    *,
    model: str | None = None,
    ctx: RunContext | None = None,
    include_preamble: bool = True,
    messages: list[dict[str, str]] | None = None,
    task_kind: str = "primary",
    bump_tier: bool = False,
    explicit_tier: str | None = None,
    response_format: dict[str, Any] | None = None,
    call_attempt: int | None = None,
    record_stage_key: str | None = None,
    system_override: str | None = None,
    volley_retry_index: int = 0,
    safe_prune_retry: bool = False,
) -> dict[str, Any]:
    """OpenAI gateway with universal truncation scan and hard block on truncated primary."""
    from interview_mux.truncation_policy import (
        TruncationEscalationMeta,
        TruncationEscalationRequired,
        log_truncation_event,
        scan_llm_input,
        tier_at_ladder_step,
        truncation_integrity_cfg,
        truncation_integrity_enabled,
    )

    cfg = merged_config()
    esc_meta = TruncationEscalationMeta(provider="openai")
    if user_content:
        try:
            from interview_mux.volley_packet_lint import lint_llm_user_payload

            parsed = json.loads(user_content)
            cleaned = lint_llm_user_payload(parsed, require_tape=task_kind in {"primary", "shard"})
            if cleaned != parsed:
                user_content = json.dumps(cleaned, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
        except (TypeError, ValueError) as lint_exc:
            if "tape-derived" in str(lint_exc):
                raise
            pass
    scan = scan_llm_input(messages=messages, user_content=user_content)
    use_bump = bump_tier
    use_explicit = explicit_tier

    if scan.truncated:
        esc_meta.final_flags = list(scan.flags)
        if truncation_integrity_enabled(cfg):
            ti = truncation_integrity_cfg(cfg)
            if ti.get("enforce_at_gateways", True):
                if not model:
                    if use_explicit is None and not use_bump:
                        use_bump = True
                        esc_meta.steps.append("tier_bump")
                        esc_meta.rounds = 1
                    elif use_bump:
                        use_explicit = tier_at_ladder_step(2, cfg)
                        esc_meta.steps.append(f"tier_{use_explicit}")
                        esc_meta.rounds = 2
                    else:
                        esc_meta.rounds = 1
                if ctx:
                    log_truncation_event(
                        ctx,
                        stage_key=record_stage_key or stage_key,
                        event="input_truncated",
                        scan=scan,
                        step=esc_meta.steps[-1] if esc_meta.steps else None,
                    )
                # Tier bump cannot remove truncation markers from the volley — do not
                # call primary/shard with truncated input when integrity requires clean I/O.
                if ti.get("never_accept_truncated_output", True) and task_kind in (
                    "primary",
                    "shard",
                ):
                    esc_meta.steps.append("blocked_truncated_primary")
                    if ctx:
                        log_truncation_event(
                            ctx,
                            stage_key=record_stage_key or stage_key,
                            event="blocked",
                            scan=scan,
                            step="blocked_truncated_primary",
                        )
                    # Surface for outer routing that can force_decompose / rebuild caps.
                    if ti.get("raise_escalation_required", True) and task_kind == "primary":
                        raise TruncationEscalationRequired(
                            flags=list(scan.flags),
                            steps=list(esc_meta.steps),
                            stage_key=record_stage_key or stage_key,
                        )
                    return _truncation_blocked_envelope(
                        record_stage_key or stage_key,
                        task_kind,
                        flags=scan.flags,
                        esc_meta=esc_meta,
                    )

    return _execute_openai_envelope_call(
        stage_key,
        prompt_rel,
        user_content,
        model=model,
        ctx=ctx,
        include_preamble=include_preamble,
        messages=messages,
        task_kind=task_kind,
        bump_tier=use_bump,
        explicit_tier=use_explicit,
        response_format=response_format,
        call_attempt=call_attempt,
        record_stage_key=record_stage_key,
        system_override=system_override,
        volley_retry_index=volley_retry_index,
        esc_meta=esc_meta,
        safe_prune_retry=safe_prune_retry,
    )


def run_prompt(
    stage_key: str,
    prompt_rel: str,
    user_content: str,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Legacy: returns artifacts only (unwraps envelope)."""
    envelope = run_prompt_envelope(stage_key, prompt_rel, user_content, model=model)
    artifacts = envelope.get("artifacts") or {}
    return artifacts if artifacts else envelope
