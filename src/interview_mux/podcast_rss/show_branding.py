"""Prepare podcast show artwork from config for publish paths.

Canonical default logo: ``settings.DEFAULT_SHOW_ARTWORK_REL``.
G-Publish sync and seed upload the prepared JPEG during normal publish.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.config import repo_root
from interview_mux.podcast_rss.openai_cover import ensure_square_cover, resolve_cover_image_settings
from interview_mux.podcast_rss.settings import (
    podcast_cfg,
    s3_layout,
    show_artwork_source_path,
)

PREPARED_SHOW_ARTWORK_REL = "ASSETS/podcast/show_artwork.jpg"


def prepared_show_artwork_path() -> Path:
    return repo_root() / PREPARED_SHOW_ARTWORK_REL


def publish_invalidation_paths(*, include_episodes: bool = False) -> list[str]:
    layout = s3_layout()
    paths = ["/" + layout["feed_key"].lstrip("/"), "/show/*"]
    if include_episodes:
        paths.append("/episodes/*")
    return paths


def prepare_show_artwork_jpeg(cfg: dict[str, Any] | None = None) -> Path:
    """Upscale config show art to Apple-ready JPEG under ASSETS/podcast/."""
    root = cfg if cfg is not None else podcast_cfg()
    src = show_artwork_source_path(root)
    if not src.is_file():
        raise FileNotFoundError(f"Show artwork missing: {src}")
    settings = resolve_cover_image_settings(root)
    dest = prepared_show_artwork_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    return ensure_square_cover(
        src,
        min_size=int(settings.get("min_output_px") or 3000),
        output_format="jpeg",
        jpeg_quality=int(settings.get("jpeg_quality") or 90),
        dest=dest,
    )
