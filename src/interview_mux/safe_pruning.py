"""One-shot safe-prune escalation after flagship context-window failure."""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

_SAFE_PRUNE_RETRY: ContextVar[bool] = ContextVar("safe_prune_retry", default=False)

_ARRAY_KEYS = (
    "segments",
    "turns",
    "excerpts",
    "pairs",
    "talking_points",
    "gaps",
    "interviewer_lines",
    "nuggets",
    "cuts",
    "boundaries",
    "words",
    "claims",
    "topics",
    "chapters",
)

SAFE_PRUNE_EXTRACT_KIND = "safe_prune_extract"
SAFE_PRUNE_PROMPT = "_shared/safe-prune-chunk.system.txt"


class SafePruneExhausted(RuntimeError):
    """Packed volley still over budget, or flagship failed context_length after prune."""


def safe_pruning_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    base = (cfg or merged_config()).get("analysis") or {}
    raw = base.get("safe_pruning") if isinstance(base.get("safe_pruning"), dict) else {}
    return {
        "enabled": True,
        "extract_tier": "economy",
        "economy_chunk_char_budget": 80000,
        "flagship_input_token_budget": 900000,
        "max_chunks": 24,
        **raw,
    }


def safe_pruning_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(safe_pruning_cfg(cfg).get("enabled", True))


def is_safe_prune_retry() -> bool:
    return bool(_SAFE_PRUNE_RETRY.get())


def is_context_length_error(exc: BaseException) -> bool:
    blob = str(exc).lower()
    if any(
        s in blob
        for s in (
            "context_length",
            "maximum context",
            "too many tokens",
            "max_tokens",
            "context window",
        )
    ):
        return True
    # A 429 "Request too large ... on tokens per min (TPM)" is an oversized
    # single request, not a burst: the provider says outright that "the input or
    # output tokens must be reduced", which is precisely what safe pruning does.
    # Without this the stage hard-fails instead of pruning and retrying, which is
    # how boundary_detection died 233 tokens over a 30k TPM cap on a real run.
    #
    # Deliberately narrow. A plain "rate limit reached" for requests per minute
    # needs backoff, not pruning, and must not match here.
    if "request too large" in blob or "tokens must be reduced" in blob:
        return True
    code = str(getattr(exc, "code", "") or "").lower()
    if code in {"context_length_exceeded", "context_length"}:
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        return "context_length" in json.dumps(body).lower()
    return False


def estimate_tokens(*parts: str) -> int:
    n = sum(len(p) for p in parts if p)
    return max(1, n // 4)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        bits: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                bits.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                bits.append(item)
        return "\n".join(bits)
    return str(content or "")


def source_text_from_call(
    *,
    user_content: str | None,
    messages: list[dict[str, Any]] | None,
) -> str:
    if user_content:
        return user_content
    parts: list[str] = []
    for msg in messages or []:
        role = str(msg.get("role") or "")
        if role == "system":
            continue
        parts.append(_content_text(msg.get("content")))
    return "\n\n".join(p for p in parts if p)


def _chunk_text(text: str, budget: int) -> list[str]:
    if len(text) <= budget:
        return [text] if text else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + budget)
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl > start + budget // 4:
                end = nl
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end
    return chunks


def chunk_source(source: str, *, budget: int, max_chunks: int) -> list[str]:
    parsed: Any = None
    try:
        parsed = json.loads(source)
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict):
        chunks = _chunk_text(source, budget)
        if len(chunks) > max_chunks:
            raise SafePruneExhausted(
                f"safe prune needs {len(chunks)} text chunks (max {max_chunks})"
            )
        return chunks or [source]

    arrays: dict[str, list[Any]] = {}
    header: dict[str, Any] = {}
    for key, val in parsed.items():
        if key in _ARRAY_KEYS and isinstance(val, list) and val:
            arrays[key] = list(val)
        else:
            header[key] = val

    if not arrays:
        chunks = _chunk_text(json.dumps(parsed, ensure_ascii=False), budget)
        if len(chunks) > max_chunks:
            raise SafePruneExhausted(
                f"safe prune needs {len(chunks)} chunks (max {max_chunks})"
            )
        return chunks or [source]

    header_s = json.dumps(header, ensure_ascii=False)
    items: list[tuple[str, Any]] = []
    for key, rows in arrays.items():
        for row in rows:
            items.append((key, row))

    chunks: list[str] = []
    bucket: dict[str, list[Any]] = {}
    size = len(header_s)

    def flush() -> None:
        nonlocal bucket, size
        if not bucket and not header:
            return
        payload = dict(header)
        payload.update(bucket)
        chunks.append(json.dumps(payload, ensure_ascii=False))
        bucket = {}
        size = len(header_s)

    for key, row in items:
        row_s = json.dumps(row, ensure_ascii=False)
        extra = len(row_s) + len(key) + 8
        if bucket and size + extra > budget:
            flush()
        bucket.setdefault(key, []).append(row)
        size += extra
        if size > budget and len(bucket.get(key) or []) == 1:
            flush()
    if bucket:
        flush()
    if len(chunks) > max_chunks:
        raise SafePruneExhausted(
            f"safe prune needs {len(chunks)} structured chunks (max {max_chunks})"
        )
    return chunks or [source]


def _parse_keeps(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    arts = envelope.get("artifacts") if isinstance(envelope, dict) else None
    blob = arts if isinstance(arts, dict) else envelope
    if not isinstance(blob, dict):
        return []
    keeps = blob.get("keeps")
    if keeps is None and isinstance(blob.get("artifacts"), dict):
        keeps = blob["artifacts"].get("keeps")
    if not isinstance(keeps, list):
        return []
    out: list[dict[str, Any]] = []
    for row in keeps:
        if isinstance(row, dict) and (row.get("quote") or row.get("why_relevant")):
            out.append(row)
        elif isinstance(row, str) and row.strip():
            out.append({"quote": row.strip(), "why_relevant": "chunk"})
    return out


def extract_chunk_keeps(
    *,
    chunk: str,
    original_system: str,
    ctx: RunContext | None,
    stage_key: str,
) -> list[dict[str, Any]]:
    from interview_mux.stages.llm_runner import run_prompt_envelope

    cfg = safe_pruning_cfg()
    user = json.dumps(
        {
            "original_system_prompt": original_system[:24000],
            "chunk": chunk,
        },
        ensure_ascii=False,
    )
    try:
        envelope = run_prompt_envelope(
            stage_key,
            SAFE_PRUNE_PROMPT,
            user,
            ctx=ctx,
            include_preamble=False,
            task_kind=SAFE_PRUNE_EXTRACT_KIND,
            explicit_tier=str(cfg.get("extract_tier") or "economy"),
            response_format={"type": "json_object"},
            system_override=None,
        )
    except Exception as exc:
        if is_context_length_error(exc) and len(chunk) > 400:
            half = chunk[: max(400, len(chunk) // 2)]
            try:
                envelope = run_prompt_envelope(
                    stage_key,
                    SAFE_PRUNE_PROMPT,
                    json.dumps(
                        {
                            "original_system_prompt": original_system[:12000],
                            "chunk": half,
                        },
                        ensure_ascii=False,
                    ),
                    ctx=ctx,
                    include_preamble=False,
                    task_kind=SAFE_PRUNE_EXTRACT_KIND,
                    explicit_tier=str(cfg.get("extract_tier") or "economy"),
                    response_format={"type": "json_object"},
                )
            except Exception:
                return []
        else:
            return []
    keeps = _parse_keeps(envelope if isinstance(envelope, dict) else {})
    try:
        from interview_mux.volley_packet_lint import lint_llm_user_payload

        cleaned = lint_llm_user_payload({"keeps": keeps, "excerpts": keeps}, require_tape=True)
        if isinstance(cleaned, dict) and isinstance(cleaned.get("keeps"), list):
            return [k for k in cleaned["keeps"] if isinstance(k, dict)]
    except Exception:
        return keeps
    return keeps


def pack_pruned_volley(
    *,
    keeps_by_chunk: list[list[dict[str, Any]]],
    header_hint: str,
) -> list[dict[str, str]]:
    all_keeps: list[dict[str, Any]] = []
    for batch in keeps_by_chunk:
        all_keeps.extend(batch)
    packed_user = json.dumps(
        {
            "safe_pruned": True,
            "note": "Evidence extracted to answer the original system prompt; unused tape dropped.",
            "header": header_hint[:4000],
            "keeps": all_keeps,
            "excerpts": [k.get("quote") for k in all_keeps if k.get("quote")],
        },
        ensure_ascii=False,
        indent=2,
    )
    messages: list[dict[str, str]] = [{"role": "user", "content": packed_user}]
    for i, batch in enumerate(keeps_by_chunk):
        if not batch:
            continue
        messages.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    {"chunk_index": i, "keeps": batch},
                    ensure_ascii=False,
                ),
            }
        )
    return messages


def run_safe_prune_pack(
    *,
    original_system: str,
    source: str,
    ctx: RunContext | None,
    stage_key: str,
) -> list[dict[str, str]]:
    cfg = safe_pruning_cfg()
    budget = int(cfg.get("economy_chunk_char_budget") or 80000)
    max_chunks = int(cfg.get("max_chunks") or 24)
    flagship_budget = int(cfg.get("flagship_input_token_budget") or 900000)
    chunks = chunk_source(source, budget=budget, max_chunks=max_chunks)
    if ctx:
        ctx.log(
            f"Safe prune start ({stage_key}): {len(chunks)} chunk(s)",
            level="warning",
            stage=stage_key,
            action_id="llm.safe_prune.start",
            detail={"chunks": len(chunks), "source_chars": len(source)},
        )
    keeps_by_chunk: list[list[dict[str, Any]]] = []
    for chunk in chunks:
        keeps_by_chunk.append(
            extract_chunk_keeps(
                chunk=chunk,
                original_system=original_system,
                ctx=ctx,
                stage_key=stage_key,
            )
        )
    header_hint = source[:1200]
    messages = pack_pruned_volley(keeps_by_chunk=keeps_by_chunk, header_hint=header_hint)
    packed_chars = sum(len(m.get("content") or "") for m in messages) + len(original_system)
    tokens = estimate_tokens(original_system, *[m.get("content") or "" for m in messages])
    if ctx:
        ctx.log(
            f"Safe prune packed ({stage_key}): tokens≈{tokens} chars={packed_chars}",
            level="info",
            stage=stage_key,
            action_id="llm.safe_prune.packed",
            detail={
                "chunks": len(chunks),
                "keeps": sum(len(k) for k in keeps_by_chunk),
                "tokens_est": tokens,
            },
        )
    if tokens > flagship_budget:
        raise SafePruneExhausted(
            f"safe-pruned pack still over flagship budget ({tokens} > {flagship_budget})"
        )
    return messages


def maybe_safe_prune_after_context_length(
    *,
    stage_key: str,
    prompt_rel: str,
    user_content: str | None,
    messages: list[dict[str, Any]] | None,
    original_system: str,
    ctx: RunContext | None,
    include_preamble: bool,
    task_kind: str,
    response_format: dict[str, Any] | None,
    call_attempt: int | None,
    record_stage_key: str | None,
    system_override: str | None,
    volley_retry_index: int,
    esc_meta: Any | None,
) -> dict[str, Any]:
    """One packed flagship retry. Caller must not invoke this if already spent."""
    from interview_mux.stages.llm_runner import _execute_openai_envelope_call

    if task_kind == SAFE_PRUNE_EXTRACT_KIND or is_safe_prune_retry():
        raise SafePruneExhausted("safe prune already spent for this invocation")
    if not safe_pruning_enabled():
        raise SafePruneExhausted("safe pruning disabled")

    source = source_text_from_call(user_content=user_content, messages=messages)
    packed = run_safe_prune_pack(
        original_system=original_system,
        source=source,
        ctx=ctx,
        stage_key=stage_key,
    )
    token = _SAFE_PRUNE_RETRY.set(True)
    try:
        envelope = _execute_openai_envelope_call(
            stage_key,
            prompt_rel,
            packed[0]["content"] if packed else user_content,
            model=None,
            ctx=ctx,
            include_preamble=include_preamble,
            messages=packed,
            task_kind=task_kind,
            bump_tier=False,
            explicit_tier="flagship",
            response_format=response_format,
            call_attempt=call_attempt,
            record_stage_key=record_stage_key,
            system_override=system_override,
            volley_retry_index=volley_retry_index,
            esc_meta=esc_meta,
            safe_prune_retry=True,
        )
    except Exception as exc:
        if is_context_length_error(exc):
            if ctx:
                ctx.log(
                    f"Safe prune exhausted ({stage_key}): packed flagship still over context",
                    level="error",
                    stage=stage_key,
                    action_id="llm.safe_prune.exhausted",
                )
            raise SafePruneExhausted(
                f"flagship still over context after safe prune ({stage_key})"
            ) from exc
        raise
    finally:
        _SAFE_PRUNE_RETRY.reset(token)

    if isinstance(envelope, dict):
        meta = envelope.setdefault("_llm_meta", {})
        meta["safe_pruning"] = {"spent": True, "chunks": True}
        if esc_meta is not None:
            steps = getattr(esc_meta, "steps", None)
            if isinstance(steps, list):
                steps.append("safe_prune")
    return envelope


def create_chat_with_context_ladder(
    client: Any,
    kwargs: dict[str, Any],
    *,
    stage_key: str,
    original_system: str,
    ctx: RunContext | None = None,
) -> Any:
    """Same ladder for off-gateway Chat Completions (cover vision)."""
    from interview_mux.model_registry import resolve_model

    def _create(kw: dict[str, Any]) -> Any:
        if ctx is not None:
            from interview_mux.homunculus.loop import nested_chat_create

            return nested_chat_create(ctx, stage_key, client, kw)
        return client.chat.completions.create(**kw)

    try:
        return _create(kwargs)
    except Exception as exc:
        if not is_context_length_error(exc):
            raise
        flagship = resolve_model(stage_key, task_kind="primary", explicit_tier="flagship").model_id
        if str(kwargs.get("model") or "") != flagship:
            retry = dict(kwargs)
            retry["model"] = flagship
            try:
                return _create(retry)
            except Exception as exc2:
                if not is_context_length_error(exc2):
                    raise
                kwargs = retry
                exc = exc2
        if is_safe_prune_retry() or not safe_pruning_enabled():
            raise SafePruneExhausted(
                f"safe prune already spent or disabled ({stage_key})"
            ) from exc
        messages = list(kwargs.get("messages") or [])
        source = source_text_from_call(user_content=None, messages=messages)
        packed = run_safe_prune_pack(
            original_system=original_system,
            source=source,
            ctx=ctx,
            stage_key=stage_key,
        )
        new_messages: list[dict[str, Any]] = [{"role": "system", "content": original_system}]
        # Preserve image parts from the original user message.
        images: list[Any] = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                images.extend(
                    item
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "image_url"
                )
        user_content: Any = packed[0]["content"] if packed else source[:8000]
        if images:
            user_content = [{"type": "text", "text": str(user_content)}, *images]
        new_messages.append({"role": "user", "content": user_content})
        for msg in packed[1:]:
            new_messages.append(msg)
        retry_kw = dict(kwargs)
        retry_kw["model"] = flagship
        retry_kw["messages"] = new_messages
        token = _SAFE_PRUNE_RETRY.set(True)
        try:
            return _create(retry_kw)
        except Exception as exc3:
            if is_context_length_error(exc3):
                raise SafePruneExhausted(
                    f"flagship still over context after safe prune ({stage_key})"
                ) from exc3
            raise
        finally:
            _SAFE_PRUNE_RETRY.reset(token)
