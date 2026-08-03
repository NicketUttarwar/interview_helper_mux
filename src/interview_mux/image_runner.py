"""Local MLX text-to-image runner — retired for War Room episode covers.

Episode covers use ``interview_mux.podcast_rss.openai_cover`` (OpenAI Images ×3 +
vision pick). This module remains only so orphan imports fail loudly.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_cover_image(
    *,
    prompt: str,
    negative_prompt: str,
    dest: Path,
    min_size: int = 1400,
) -> Path:
    """Deprecated — podcast covers use OpenAI via episode_cover_generate."""
    raise RuntimeError(
        "Local cover generation retired. Use podcast.cover_image (OpenAI) via "
        "episode_cover_generate / interview_mux.podcast_rss.openai_cover."
    )
