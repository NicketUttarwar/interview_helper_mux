"""MLX local inference for volley framing (subprocess via ASSETS/local_llm/venv)."""

from __future__ import annotations

import json
from typing import Any

from interview_mux.local_llm_config import max_tokens, resolve_model_id, resolve_model_path
from interview_mux.local_runtime import LocalRuntimeUnavailable, run_runtime_script
from interview_mux.run_context import RunContext


class LocalLlmUnavailable(LocalRuntimeUnavailable):
    """Raised when mlx-lm venv is missing or weights are not on disk."""


def mlx_available() -> bool:
    from interview_mux.local_runtime import resolve_venv_python

    try:
        resolve_venv_python("mlx")
        return True
    except LocalRuntimeUnavailable:
        return False


def generate_local_chat(
    *,
    system: str,
    user: str,
    ctx: RunContext | None = None,
    stage_key: str = "_local_framer",
    max_tokens_override: int | None = None,
    cfg: dict[str, Any] | None = None,
    task_kind: str | None = None,
    interaction_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Run one local chat completion via subprocess. Returns (raw_text, meta).
    Raises LocalLlmUnavailable on missing deps/weights.
    """
    from interview_mux.config import merged_config
    from interview_mux.local_structured_output import (
        build_local_schema_appendix,
        local_structured_outputs_cfg,
        resolve_local_interaction,
    )
    from interview_mux.llm_interaction_registry import resolve_interaction_id
    from interview_mux.llm_response_verify import verification_to_record_dict, verify_llm_response

    resolved_cfg = cfg or merged_config()
    interaction = resolve_local_interaction(stage_key, task_kind)
    iid = interaction_id or resolve_interaction_id(
        stage_key=stage_key,
        task_kind=task_kind or f"local_{interaction}",
        provider="local_mlx",
    )
    system_prompt = system + build_local_schema_appendix(interaction, cfg=resolved_cfg)

    model_id = resolve_model_id(resolved_cfg)
    model_path = resolve_model_path(resolved_cfg)
    if not model_path.is_dir():
        raise LocalLlmUnavailable(
            f"Local model weights not found at {model_path}. "
            f"Run: python scripts/select_local_llm.py --download "
            f"(or: python scripts/download_local_llm.py --model {model_id!r})"
        )

    limit = max_tokens_override if max_tokens_override is not None else max_tokens(resolved_cfg)
    stdin_payload = json.dumps(
        {
            "system": system_prompt,
            "user": user,
            "max_tokens": limit,
            "model_path": str(model_path),
        }
    )
    if ctx:
        from interview_mux.operator_trace import log_api_call

        log_api_call(
            "local_llm",
            f"mlx infer ({model_id})",
            ctx=ctx,
            stage=stage_key,
            detail={"model_id": model_id, "max_tokens": limit, "interaction_id": iid},
        )
    proc = run_runtime_script(
        "mlx",
        "tools/local_llm_infer.py",
        [],
        stdin_data=stdin_payload,
        ctx=ctx,
        stage=stage_key,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        raise LocalLlmUnavailable(f"Local LLM subprocess failed: {err}")

    try:
        result = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise LocalLlmUnavailable(f"Local LLM returned invalid JSON: {exc}") from exc

    if result.get("error"):
        raise LocalLlmUnavailable(str(result["error"]))

    text = str(result.get("text") or "")
    meta = dict(result.get("meta") or {})
    meta.setdefault("model_id", model_id)
    meta.setdefault("model_path", str(model_path))
    meta["interaction_id"] = iid

    parsed: dict[str, Any] | None = None
    try:
        from interview_mux.stages.llm_runner import _extract_json

        parsed = _extract_json(text)
        verification = verify_llm_response(iid, parsed, stage_key=stage_key, task_kind=task_kind)
        meta["verification"] = verification_to_record_dict(verification)
        so_cfg = local_structured_outputs_cfg(resolved_cfg)
        if not verification.ok:
            if ctx:
                ctx.log(
                    f"Local LLM verification failed ({stage_key}, {iid}): "
                    f"{verification.errors[:2]}",
                    level="warning",
                    stage=stage_key,
                    action_id="llm.verification_failed",
                    detail={
                        "interaction_id": iid,
                        "errors": verification.errors[:5],
                    },
                )
            if not so_cfg.get("fail_open_on_verify", True):
                raise LocalLlmUnavailable(
                    f"Local LLM response failed verification ({iid}): {verification.errors[:3]}"
                )
    except (ValueError, json.JSONDecodeError):
        so_cfg = local_structured_outputs_cfg(resolved_cfg)
        if not so_cfg.get("fail_open_on_verify", True):
            raise

    if ctx:
        ctx.log(
            f"Local LLM {stage_key}: {meta.get('latency_ms', '?')}ms, "
            f"~{meta.get('tokens_approx', '?')} tokens",
            level="success",
            stage=stage_key,
            detail={"journey_kind": "execute", "model_id": model_id, "interaction_id": iid},
        )
    return text.strip(), meta
