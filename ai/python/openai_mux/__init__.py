"""OpenAI-backed helpers for interview_helper_mux (ranking, prompts, future adapters)."""

from openai_mux.client import get_openai_client
from openai_mux.prompts import (
    default_segment_ranking_rubric,
    highlight_noteworthiness_system_prompt,
    segment_ranking_system_prompt,
    smoke_connectivity_system_prompt,
)
from openai_mux.ranking import rank_segments_by_rubric
from openai_mux.settings import OpenAISettings, load_openai_settings
from openai_mux.versions import OPENAI_PYTHON_SDK_MAJOR

__all__ = [
    "OPENAI_PYTHON_SDK_MAJOR",
    "OpenAISettings",
    "default_segment_ranking_rubric",
    "get_openai_client",
    "highlight_noteworthiness_system_prompt",
    "load_openai_settings",
    "rank_segments_by_rubric",
    "segment_ranking_system_prompt",
    "smoke_connectivity_system_prompt",
]
