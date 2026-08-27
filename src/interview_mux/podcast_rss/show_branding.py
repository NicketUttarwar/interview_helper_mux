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
    default_podcast_id,
    s3_layout,
    show_artwork_source_path,
    show_cfg,
)

PREPARED_SHOW_ARTWORK_REL = "ASSETS/podcast/shows/zero_shot_podcast_demo/show_artwork.jpg"


def prepared_show_artwork_path(cfg: dict[str, Any] | None = None) -> Path:
    root = cfg if cfg is not None else show_cfg()
    pid = str(root.get("podcast_id") or default_podcast_id())
    return repo_root() / "ASSETS" / "podcast" / "shows" / pid / "show_artwork.jpg"


def publish_invalidation_paths(*, include_episodes: bool = False, cfg: dict[str, Any] | None = None) -> list[str]:
    layout = s3_layout(cfg)
    paths = ["/" + layout["feed_key"].lstrip("/"), "/show/*"]
    if include_episodes:
        paths.append("/episodes/*")
    return paths


def prepare_show_artwork_jpeg(cfg: dict[str, Any] | None = None) -> Path:
    """Upscale config show art to Apple-ready JPEG under ASSETS/podcast/shows/<id>/."""
    root = cfg if cfg is not None else show_cfg()
    src = show_artwork_source_path(root)
    if not src.is_file():
        raise FileNotFoundError(f"Show artwork missing: {src}")
    settings = resolve_cover_image_settings(root)
    dest = prepared_show_artwork_path(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    return ensure_square_cover(
        src,
        min_size=int(settings.get("min_output_px") or 3000),
        output_format="jpeg",
        jpeg_quality=int(settings.get("jpeg_quality") or 90),
        dest=dest,
    )
