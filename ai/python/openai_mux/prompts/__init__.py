"""Central system prompts for OpenAI-backed flows (ranking, curation, smoke tests)."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=32)
def load_prompt_text(filename: str) -> str:
    """Return UTF-8 text for a file in this package (e.g. ``segment_ranking.system.txt``)."""
    return resources.files(__package__).joinpath(filename).read_text(encoding="utf-8").strip()


def segment_ranking_system_prompt() -> str:
    """Chat Completions system message for ``rank_segments_by_rubric``."""
    return load_prompt_text("segment_ranking.system.txt")


def highlight_noteworthiness_system_prompt() -> str:
    """
    System message for future flows that score or explain **impactful / noteworthy**
    spans (chaptering, pull-quotes, editorial summaries). Callers should pair this
    with a user message that specifies output shape (JSON schema, bullet list, etc.).
    """
    return load_prompt_text("highlight_noteworthiness.system.txt")


def smoke_connectivity_system_prompt() -> str:
    """Minimal system line for ``tools/openai_smoke.py``."""
    return load_prompt_text("smoke_connectivity.system.txt")


def default_segment_ranking_rubric() -> str:
    """Default rubric string merged into the ranking user JSON unless overridden."""
    return load_prompt_text("segment_ranking_default_rubric.txt")


__all__ = [
    "default_segment_ranking_rubric",
    "highlight_noteworthiness_system_prompt",
    "load_prompt_text",
    "segment_ranking_system_prompt",
    "smoke_connectivity_system_prompt",
]
