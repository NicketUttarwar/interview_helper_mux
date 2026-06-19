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
) -> tuple[str, dict[str, Any]]:
    """
    Run one local chat completion via subprocess. Returns (raw_text, meta).
    Raises LocalLlmUnavailable on missing deps/weights.
    """
    model_id = resolve_model_id(cfg)
    model_path = resolve_model_path(cfg)
    if not model_path.is_dir():
        raise LocalLlmUnavailable(
            f"Local model weights not found at {model_path}. "
            f"Run: python scripts/select_local_llm.py --download "
            f"(or: python scripts/download_local_llm.py --model {model_id!r})"
        )

    limit = max_tokens_override if max_tokens_override is not None else max_tokens(cfg)
    stdin_payload = json.dumps(
        {
            "system": system,
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
            detail={"model_id": model_id, "max_tokens": limit},
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

    if ctx:
        ctx.log(
            f"Local LLM {stage_key}: {meta.get('latency_ms', '?')}ms, "
            f"~{meta.get('tokens_approx', '?')} tokens",
            level="success",
            stage=stage_key,
            detail={"journey_kind": "execute", "model_id": model_id},
        )
    return text.strip(), meta
