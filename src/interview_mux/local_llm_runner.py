"""MLX local inference for volley framing (lazy-loaded; optional dependency)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from interview_mux.local_llm_config import (
    max_tokens,
    resolve_model_id,
    resolve_model_path,
)
from interview_mux.run_context import RunContext

_MODEL_CACHE: dict[str, tuple[Any, Any]] = {}


class LocalLlmUnavailable(Exception):
    """Raised when mlx-lm is missing or weights are not on disk."""


def mlx_available() -> bool:
    try:
        import mlx_lm  # noqa: F401

        return True
    except ImportError:
        return False


def load_local_model(model_path: str | None = None, *, cfg: dict[str, Any] | None = None) -> tuple[Any, Any]:
    """Load (or return cached) MLX model + tokenizer."""
    if not mlx_available():
        raise LocalLlmUnavailable("mlx-lm is not installed (Apple Silicon: pip install mlx-lm)")

    from mlx_lm import load

    resolved = Path(model_path) if model_path else resolve_model_path(cfg)
    cache_key = str(resolved)
    if cache_key not in _MODEL_CACHE:
        if not resolved.is_dir():
            raise LocalLlmUnavailable(
                f"Local model weights not found at {resolved}. "
                f"Run: python scripts/select_local_llm.py --download "
                f"(or: python scripts/download_local_llm.py --model {resolve_model_id(cfg)!r})"
            )
        _MODEL_CACHE[cache_key] = load(cache_key)
    return _MODEL_CACHE[cache_key]


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
    Run one local chat completion. Returns (raw_text, meta).
    Always raises LocalLlmUnavailable on missing deps/weights — callers must fall back to OpenAI path.
    """
    from mlx_lm import generate

    model_id = resolve_model_id(cfg)
    model, tokenizer = load_local_model(cfg=cfg)
    limit = max_tokens_override if max_tokens_override is not None else max_tokens(cfg)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if getattr(tokenizer, "chat_template", None):
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    else:
        prompt = f"{system}\n\nUser:\n{user}\n\nAssistant:\n"

    started = time.perf_counter()
    raw = generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=limit,
        verbose=False,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    text = raw if isinstance(raw, str) else str(raw)
    approx_tokens = max(1, len(text) // 4)

    meta = {
        "model_id": model_id,
        "model_path": str(resolve_model_path(cfg)),
        "latency_ms": latency_ms,
        "tokens_approx": approx_tokens,
        "max_tokens": limit,
    }
    if ctx:
        ctx.log(
            f"Local LLM {stage_key}: {latency_ms}ms, ~{approx_tokens} tokens",
            level="debug",
            stage=stage_key,
        )
    return text.strip(), meta
