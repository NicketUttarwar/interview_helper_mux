"""Resolve podcast runtime settings: committed app.defaults + gitignored secrets.

Split:
  - Non-secret / operator-chosen → config/app.defaults.json ``podcast``
    (s3_bucket, aws_region, project_name, show meta, S3 layout)
  - Credentials + AWS-derived IDs → config/secrets/secrets.env
    (AWS_*, PODCAST_CLOUDFRONT_DISTRIBUTION_ID, PODCAST_FEED_BASE_URL)
  - Optional secrets override: PODCAST_S3_BUCKET (prefer app.defaults)
"""

from __future__ import annotations

from pathlib import Path
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
        "show_artwork_key": str(layout.get("show_artwork_key") or "artwork.jpg"),
        "catalog_prefix": str(layout.get("catalog_prefix") or "catalog").rstrip("/"),
        "episodes_prefix": str(layout.get("episodes_prefix") or "episodes").rstrip("/"),
        "episode_files": {
            "audio": str(files.get("audio") or "audio.mp3"),
            "master": str(files.get("master") or "master.wav"),
            "cover": str(files.get("cover") or "cover.jpg"),
            "meta": str(files.get("meta") or "episode.json"),
            "description": str(files.get("description") or "description.txt"),
            "chapters": str(files.get("chapters") or "chapters.json"),
            "transcript": str(files.get("transcript") or "transcript.vtt"),
        },
    }


def show_artwork_s3_key(cfg: dict[str, Any] | None = None) -> str:
    layout = s3_layout(cfg)
    return f"{layout['show_prefix']}/{layout['show_artwork_key']}"


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


def feed_url_from_base(feed_base: str | None = None, *, cfg: dict[str, Any] | None = None) -> str:
    base = (feed_base if feed_base is not None else resolve_publish_targets()["feed_base_url"]).rstrip("/")
    layout = s3_layout(cfg)
    key = layout["feed_key"]
    if not base:
        return ""
    if base.endswith(key):
        return base
    return f"{base}/{key}"


def require_publish_ready(*, local_dir: Path | None = None) -> dict[str, str]:
    """Fail fast before any S3 PutObject. Returns resolved targets."""
    cfg = podcast_cfg()
    if not bool(cfg.get("enabled", True)):
        raise RuntimeError("podcast.enabled is false — enable it in config/app.defaults.json")
    email = str(cfg.get("show_email") or "").strip()
    if not email or "@" not in email:
        raise RuntimeError("podcast.show_email missing or invalid in config/app.defaults.json")

    targets = resolve_publish_targets()
    bucket = targets["bucket"]
    dist_id = targets["distribution_id"]
    base = targets["feed_base_url"]
    if not bucket:
        raise RuntimeError(
            "podcast.s3_bucket missing in config/app.defaults.json "
            "(optional override: PODCAST_S3_BUCKET in secrets.env)"
        )
    if not dist_id:
        raise RuntimeError(
            "PODCAST_CLOUDFRONT_DISTRIBUTION_ID missing in secrets.env — "
            "run ./scripts/tf-apply.sh or ./scripts/sync_podcast_tf_secrets.sh"
        )
    if not base:
        raise RuntimeError(
            "PODCAST_FEED_BASE_URL missing in secrets.env — "
            "run ./scripts/tf-apply.sh or ./scripts/sync_podcast_tf_secrets.sh"
        )

    override = str(load_secrets().get("PODCAST_S3_BUCKET") or "").strip()
    if override and override != bucket:
        raise RuntimeError(
            f"PODCAST_S3_BUCKET={override!r} disagrees with podcast.s3_bucket={bucket!r}. "
            "Remove the secrets override or align both."
        )

    if local_dir is not None:
        layout = s3_layout(cfg)
        files = layout["episode_files"]
        for key in ("audio", "master", "cover"):
            path = local_dir / files[key]
            if not path.is_file() or path.stat().st_size < 1:
                raise RuntimeError(
                    f"Required publish file missing or empty: {path.name} "
                    f"(expected under {local_dir})"
                )
        _require_cover_min_px(local_dir / files["cover"], min_px=1400)

    return targets


def _require_cover_min_px(path: Path, *, min_px: int = 1400) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to validate cover dimensions") from exc
    with Image.open(path) as im:
        w, h = im.size
    if w < min_px or h < min_px:
        raise RuntimeError(
            f"Cover art {path.name} is {w}x{h}; Apple requires at least {min_px}x{min_px} "
            f"(target {podcast_cfg().get('cover_image', {}).get('min_output_px', 3000)}px)"
        )


def episode_prefix(episode_number: int, *, cfg: dict[str, Any] | None = None) -> str:
    layout = s3_layout(cfg)
    folder = f"{int(episode_number):04d}"
    return f"{layout['episodes_prefix']}/{folder}"
