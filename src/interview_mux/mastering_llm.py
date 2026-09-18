"""Mastering prompt invokes (A-03 Shape/research LLM cutover).

Canon: docs/prompts/mastering/. Max 2 attempts per stage invoke.
Callers gate via research_llm_enabled / shape_llm_enabled.
Shape LLM default on (Q6B) with packed payloads + response lint; research.llm stays off.
"""

from __future__ import annotations

import json
from typing import Any

from interview_mux.run_context import RunContext


def artifacts_from_envelope(envelope: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize envelope artifacts; None when unusable."""
    if not isinstance(envelope, dict):
        return None
    arts = envelope.get("artifacts")
    if isinstance(arts, dict) and arts:
        return arts
    # Some runners return the artifact object as the envelope body.
    if envelope.get("version") == 1 and (
        "narrative_mode" in envelope
        or "fields" in envelope
        or "candidates" in envelope
        or "mode_candidates" in envelope
        or "steps" in envelope
        or "criteria" in envelope
    ):
        return dict(envelope)
    return None


def invoke_mastering_prompt(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    user_payload: dict[str, Any] | str,
    *,
    max_attempts: int = 2,
) -> dict[str, Any] | None:
    """Call a mastering system prompt; return artifacts dict or None (fail-open)."""
    try:
        from interview_mux.stages.llm_runner import run_prompt_envelope
    except Exception:
        return None

    if isinstance(user_payload, str):
        user_content = user_payload
    else:
        try:
            user_content = json.dumps(user_payload, ensure_ascii=False, default=str)
        except Exception:
            return None

    attempts = max(1, min(int(max_attempts or 2), 2))
    for attempt in range(1, attempts + 1):
        try:
            envelope = run_prompt_envelope(
                stage_key,
                prompt_rel,
                user_content=user_content,
                ctx=ctx,
                include_preamble=True,
                call_attempt=attempt,
            )
        except Exception:
            continue
        arts = artifacts_from_envelope(envelope if isinstance(envelope, dict) else None)
        if arts is not None:
            return arts
        status = ""
        if isinstance(envelope, dict):
            status = str(envelope.get("status") or "").lower()
        if status in ("complete",) and isinstance(envelope, dict):
            nested = envelope.get("artifacts")
            if isinstance(nested, dict):
                return nested
    return None
