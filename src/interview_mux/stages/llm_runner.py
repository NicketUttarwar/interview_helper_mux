from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from interview_mux.config import get_model, merged_config, repo_root, require_secret
from interview_mux.run_context import RunContext

PREAMBLE_REL = "_shared/analysis-preamble.system.txt"
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


def prompt_path(*parts: str) -> Path:
    return repo_root().joinpath("docs", "prompts", *parts)


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


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"No JSON object in model response: {text[:200]}")
    return json.loads(match.group())


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
) -> dict[str, Any]:
    """
    Call OpenAI with either:
    - `messages`: full user/assistant volley (recommended; system added here), or
    - `user_content`: legacy single user JSON blob.
    """
    client = OpenAI(api_key=require_secret("OPENAI_API_KEY"))
    system = load_system_prompt(prompt_rel, include_preamble=include_preamble)
    chosen = model or get_model(stage_key)

    if messages:
        chat_messages: list[dict[str, str]] = [{"role": "system", "content": system}, *messages]
    elif user_content is not None:
        chat_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
    else:
        raise ValueError("Provide messages volley or user_content")

    resp = client.chat.completions.create(
        model=chosen,
        messages=chat_messages,
        temperature=0.2,
    )
    content = resp.choices[0].message.content or ""
    envelope = normalize_envelope(_extract_json(content))
    if ctx:
        turns = len(messages) if messages else 1
        chars = sum(len(m.get("content", "")) for m in (messages or []))
        ctx.log(
            f"LLM {stage_key}: status={envelope.get('status')} "
            f"needs={len(envelope.get('needs') or [])} "
            f"context_turns={turns} context_chars≈{chars}",
            level="info",
            stage=stage_key,
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
