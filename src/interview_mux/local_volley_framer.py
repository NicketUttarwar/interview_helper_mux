"""v2 local volley framer (LX-01): prep user/assistant turns before OpenAI — fail-open."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from interview_mux.analysis_memory import load_analysis_state
from interview_mux.config import merged_config
from interview_mux.local_llm_config import (
    LOCAL_FRAMER_PROMPT,
    local_llm_cfg,
    local_llm_enabled,
    max_volley_turns,
    quality_local_allowlist,
    should_frame_task_kind,
    stage_on_quality_allowlist,
)
from interview_mux.local_llm_runner import LocalLlmUnavailable, generate_local_chat, mlx_available
from interview_mux.llm_response_verify import verify_llm_response
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

    def to_attempt_meta(self) -> dict[str, Any]:
        return {
            "escalate": self.escalate,
            "confidence": self.confidence,
            "reason": self.reason,
            "used_local": self.used_local,
            "fallback": self.fallback,
            "model_id": self.model_id,
            "volley_turn_count": len(self.volley_turns),
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


def _compact_stage_input(stage_input: dict[str, Any], *, max_chars: int = 4000) -> tuple[str, bool]:
    raw = json.dumps(stage_input, ensure_ascii=False)
    if len(raw) <= max_chars:
        return raw, False
    return raw[: max_chars - 24] + "…[digest truncated]", True


def _build_framer_user_blob(
    ctx: RunContext,
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    digest: str,
    digest_truncated: bool,
    cfg: dict[str, Any],
) -> str:
    state = load_analysis_state(ctx)
    meta = state.get("meta") if isinstance(state.get("meta"), dict) else {}
    summaries = meta.get("stage_summaries") if isinstance(meta.get("stage_summaries"), dict) else {}
    prior: list[dict[str, str]] = []
    for key, text in list(summaries.items())[-6:]:
        if text:
            prior.append({str(key): str(text)[:400]})
    payload = {
        "stage_key": stage_key,
        "task_kind": "primary",
        "profile": "full",
        "prior_one_liners": prior,
        "volley_budget": max_volley_turns(cfg),
        "stage_input_digest": digest,
        "digest_truncated": digest_truncated,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def prepare_volley_for_llm(
    ctx: RunContext,
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    task_kind: str = "primary",
) -> LocalFramingResult:
    """
    Run local MLX framer when enabled. Fail-open: returns empty volley_turns on any skip/error.
    OpenAI primary always runs separately — escalate flags are advisory only in v2.
    """
    cfg = merged_config()
    llm_cfg = local_llm_cfg(cfg)
    if not local_llm_enabled(cfg):
        return LocalFramingResult(fallback="disabled", reason="local_llm_disabled")
    if not stage_on_quality_allowlist(stage_key, cfg):
        return LocalFramingResult(fallback="not_allowlisted", reason="stage_not_allowlisted")
    if not should_frame_task_kind(task_kind, "full", cfg):
        return LocalFramingResult(fallback="task_kind", reason=f"skip_task_kind:{task_kind}")
    if not mlx_available():
        return LocalFramingResult(fallback="mlx_unavailable", reason="mlx_unavailable")

    digest, digest_truncated = _compact_stage_input(stage_input)
    user_blob = _build_framer_user_blob(
        ctx,
        stage_key,
        stage_input,
        digest=digest,
        digest_truncated=digest_truncated,
        cfg=cfg,
    )

    try:
        system = load_system_prompt(LOCAL_FRAMER_PROMPT, include_preamble=False)
        raw, run_meta = generate_local_chat(
            system=system,
            user=user_blob,
            ctx=ctx,
            stage_key=stage_key,
            task_kind=f"local_{task_kind}",
            cfg=cfg,
        )
        parsed = parse_framer_response(raw, max_turns=max_volley_turns(cfg))
        verify = verify_llm_response("LX-01", parsed, stage_key=stage_key, task_kind=f"local_{task_kind}")
        if not verify.ok:
            if llm_cfg.get("fail_open", True):
                ctx.log(
                    f"Local framer verify failed for {stage_key} — OpenAI-only volley",
                    level="warning",
                    stage=stage_key,
                    detail={"errors": verify.errors[:4]},
                )
                return LocalFramingResult(
                    fallback="verify_failed",
                    reason="framer_verify_failed",
                    model_id=run_meta.get("model_id"),
                )
            raise LocalLlmUnavailable(f"Framer verify failed: {verify.errors[:2]}")

        turns = list(parsed.get("volley_turns") or [])
        ctx.log(
            f"Local volley framer: {len(turns)} turn(s) for {stage_key}",
            level="info",
            stage=stage_key,
            detail={
                "model_id": run_meta.get("model_id"),
                "confidence": parsed.get("confidence"),
                "reason": parsed.get("reason"),
            },
        )
        return LocalFramingResult(
            escalate=bool(parsed.get("escalate", True)),
            confidence=float(parsed.get("confidence", 0)),
            reason=str(parsed.get("reason") or ""),
            volley_turns=turns,
            used_local=True,
            model_id=str(run_meta.get("model_id") or ""),
        )
    except LocalLlmUnavailable as exc:
        if llm_cfg.get("fail_open", True):
            ctx.log(
                f"Local framer unavailable for {stage_key}: {exc}",
                level="warning",
                stage=stage_key,
            )
            return LocalFramingResult(fallback="local_error", reason=str(exc)[:200])
        raise
    except Exception as exc:
        if llm_cfg.get("fail_open", True):
            ctx.log(
                f"Local framer failed for {stage_key}: {exc}",
                level="warning",
                stage=stage_key,
            )
            return LocalFramingResult(fallback="local_error", reason=str(exc)[:200])
        raise
