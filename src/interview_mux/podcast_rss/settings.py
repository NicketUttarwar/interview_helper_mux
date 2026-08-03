"""Resolve podcast runtime settings: committed app.defaults + gitignored secrets.

Split:
  - Non-secret / operator-chosen → config/app.defaults.json ``podcast``
    (s3_bucket, aws_region, project_name, show meta, S3 layout)
  - Credentials + AWS-derived IDs → config/secrets/secrets.env
    (AWS_*, PODCAST_CLOUDFRONT_DISTRIBUTION_ID, PODCAST_FEED_BASE_URL)
  - Optional secrets override: PODCAST_S3_BUCKET (prefer app.defaults)
"""

from __future__ import annotations

from typing import Any

from interview_mux.config import load_secrets, merged_config


def podcast_cfg() -> dict[str, Any]:
    cfg = merged_config().get("podcast") or {}
    return cfg if isinstance(cfg, dict) else {}


def s3_layout(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    root = cfg if cfg is not None else podcast_cfg()
    layout = root.get("s3") if isinstance(root.get("s3"), dict) else {}
    files = layout.get("episode_files") if isinstance(layout.get("episode_files"), dict) else {}
    return {
        "feed_key": str(layout.get("feed_key") or "feed.xml"),
        "show_prefix": str(layout.get("show_prefix") or "show").rstrip("/"),
        "catalog_prefix": str(layout.get("catalog_prefix") or "catalog").rstrip("/"),
        "episodes_prefix": str(layout.get("episodes_prefix") or "episodes").rstrip("/"),
        "episode_files": {
            "audio": str(files.get("audio") or "audio.mp3"),
            "master": str(files.get("master") or "master.wav"),
            "cover": str(files.get("cover") or "cover.png"),
            "meta": str(files.get("meta") or "episode.json"),
            "description": str(files.get("description") or "description.txt"),
            "chapters": str(files.get("chapters") or "chapters.json"),
        },
    }


def resolve_publish_targets() -> dict[str, str]:
    """Bucket/region from app.defaults; CF/feed from secrets (AWS-derived)."""
    cfg = podcast_cfg()
    secrets = load_secrets()
    bucket = str(cfg.get("s3_bucket") or secrets.get("PODCAST_S3_BUCKET") or "").strip()
    region = str(
        cfg.get("aws_region")
        or secrets.get("AWS_DEFAULT_REGION")
        or secrets.get("AWS_REGION")
        or "us-east-1"
    ).strip()
    dist_id = str(secrets.get("PODCAST_CLOUDFRONT_DISTRIBUTION_ID") or "").strip()
    feed_base = str(secrets.get("PODCAST_FEED_BASE_URL") or "").rstrip("/")
    project = str(cfg.get("project_name") or "the_war_room_001").strip()
    return {
        "bucket": bucket,
        "region": region,
        "distribution_id": dist_id,
        "feed_base_url": feed_base,
        "project_name": project,
    }


def episode_prefix(episode_number: int, *, cfg: dict[str, Any] | None = None) -> str:
    layout = s3_layout(cfg)
    folder = f"{int(episode_number):04d}"
    return f"{layout['episodes_prefix']}/{folder}"
