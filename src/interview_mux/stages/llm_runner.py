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
JSON_OBJECT_FORMAT: dict[str, str] = {"type": "json_object"}
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


def _prompt_thresholds_block() -> str:
    """Canonical numeric limits from config (aligned with logic-tree.md)."""
    th = (merged_config().get("analysis") or {}).get("prompt_thresholds") or {}
    return (
        "## Pipeline thresholds (authoritative)\n"
        f"- Pause-based split: ≥ {th.get('pause_split_ms', 700)} ms between words\n"
        f"- Short interviewer question (keep with answer): ≤ {th.get('short_question_max_words', 12)} words\n"
        f"- VO question max words: {th.get('interviewer_question_max_words', 15)}\n"
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
) -> str:
    from interview_mux.required_response_format import build_required_response_block

    system = load_system_prompt(rel_path, include_preamble=include_preamble)
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


def _default_response_format(task_kind: str, explicit: dict[str, str] | None) -> dict[str, str] | None:
    if explicit is not None:
        return explicit
    if task_kind in ("primary", "shard", "collate", "specialist", "arbiter"):
        return JSON_OBJECT_FORMAT
    return None


def normalize_envelope(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept full envelope or legacy flat stage JSON."""
    if "artifacts" in raw or "status" in raw:
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
        return env
    return {
        "status": "complete",
        "artifacts": raw,
        "memory_updates": {},
        "needs": [],
        "follow_up_investigations": [],
        "confidence": None,
        "reasoning_summary": "",
    }


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
    response_format: dict[str, str] | None = None,
    call_attempt: int | None = None,
    record_stage_key: str | None = None,
    system_override: str | None = None,
    volley_retry_index: int = 0,
) -> dict[str, Any]:
    """
    Call OpenAI with either:
    - `messages`: full user/assistant volley (recommended; system added here), or
    - `user_content`: legacy single user JSON blob.
    """
    client = OpenAI(api_key=require_secret("OPENAI_API_KEY"))
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
    fmt = _default_response_format(task_kind, response_format)
    if fmt:
        kwargs["response_format"] = fmt
    if ctx:
        from interview_mux.operator_trace import log_api_call

        from interview_mux.context_volley import truncation_flags_for_volley

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
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:
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
            ctx.log(
                f"LLM parse failed ({stage_key}, {task_kind}): {exc}",
                level="error",
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
    tier = resolved.tier if resolved else ("explicit" if model else "economy")
    envelope["_llm_meta"] = {
        "model_id": chosen,
        "model_tier": tier,
        "task_kind": task_kind,
    }
    if ctx:
        from interview_mux.context_volley import truncation_flags_for_volley
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
            )
            llm_path = (call_record.get("links") or {}).get("relative_path")
            if llm_path:
                envelope["_llm_meta"]["llm_call_path"] = llm_path
    if ctx:
        turns = len(messages) if messages else 1
        chars = sum(len(m.get("content", "")) for m in (messages or []))
        ctx.log(
            f"LLM {stage_key}: status={envelope.get('status')} "
            f"needs={len(envelope.get('needs') or [])} "
            f"context_turns={turns} context_chars≈{chars}",
            level="success",
            stage=stage_key,
            detail={"journey_kind": "execute", "model": chosen},
        )
    return envelope


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
