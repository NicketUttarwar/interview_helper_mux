"""S3 PutObject with explicit Content-Type / Cache-Control + CloudFront invalidation."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from interview_mux.podcast_rss.settings import episode_prefix, podcast_cfg, s3_layout

logger = logging.getLogger(__name__)

CONTENT_TYPES = {
    "feed.xml": "application/rss+xml",
    ".mp3": "audio/mpeg",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".wav": "audio/wav",
}


def _boto3():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required for podcast publish. Install with: pip install boto3"
        ) from exc
    return boto3


def _client(service: str, *, region: str | None = None):
    """Build a boto3 client using ambient AWS auth, with optional secrets.env overlay."""
    from interview_mux.config import load_secrets

    secrets = load_secrets()
    region_name = (
        region
        or os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or str(secrets.get("AWS_DEFAULT_REGION") or secrets.get("AWS_REGION") or "").strip()
        or None
    )
    session_kwargs: dict[str, Any] = {}
    if region_name:
        session_kwargs["region_name"] = region_name

    access = os.environ.get("AWS_ACCESS_KEY_ID") or str(secrets.get("AWS_ACCESS_KEY_ID") or "").strip()
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY") or str(secrets.get("AWS_SECRET_ACCESS_KEY") or "").strip()
    token = os.environ.get("AWS_SESSION_TOKEN") or str(secrets.get("AWS_SESSION_TOKEN") or "").strip()
    profile = os.environ.get("AWS_PROFILE") or str(secrets.get("AWS_PROFILE") or "").strip()

    if access and secret and not os.environ.get("AWS_ACCESS_KEY_ID"):
        session_kwargs["aws_access_key_id"] = access
        session_kwargs["aws_secret_access_key"] = secret
        if token:
            session_kwargs["aws_session_token"] = token
    elif profile and not os.environ.get("AWS_PROFILE"):
        session_kwargs["profile_name"] = profile

    session = _boto3().Session(**session_kwargs)
    return session.client(service)


def content_type_for_key(key: str) -> str:
    name = key.rsplit("/", 1)[-1]
    if name == "feed.xml":
        return CONTENT_TYPES["feed.xml"]
    for suffix, ctype in CONTENT_TYPES.items():
        if suffix.startswith(".") and name.lower().endswith(suffix):
            return ctype
    return "application/octet-stream"


def cache_control_for_key(key: str) -> str:
    name = key.rsplit("/", 1)[-1]
    layout = s3_layout()
    if name == layout["feed_key"].rsplit("/", 1)[-1] or key.startswith(f"{layout['catalog_prefix']}/"):
        return "max-age=0, must-revalidate"
    return "public, max-age=86400"


def put_bytes(
    *,
    bucket: str,
    key: str,
    body: bytes,
    region: str | None = None,
    content_type: str | None = None,
    cache_control: str | None = None,
) -> None:
    ctype = content_type or content_type_for_key(key)
    cache = cache_control or cache_control_for_key(key)
    _client("s3", region=region).put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType=ctype,
        CacheControl=cache,
    )


def put_file(
    *,
    bucket: str,
    key: str,
    path: Path,
    region: str | None = None,
) -> None:
    data = path.read_bytes()
    put_bytes(bucket=bucket, key=key, body=data, region=region)


def get_json(bucket: str, key: str, *, region: str | None = None) -> dict[str, Any]:
    try:
        obj = _client("s3", region=region).get_object(Bucket=bucket, Key=key)
        raw = obj["Body"].read()
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code in {"NoSuchKey", "404", "NotFound"}:
            return {}
        logger.warning("get_json %s/%s failed: %s", bucket, key, exc)
        return {}


def list_episode_metas(bucket: str, *, region: str | None = None) -> list[dict[str, Any]]:
    """Load episodes/*/episode.json newest-first by episode_number."""
    layout = s3_layout()
    meta_name = layout["episode_files"]["meta"]
    prefix = f"{layout['episodes_prefix']}/"
    s3 = _client("s3", region=region)
    paginator = s3.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for row in page.get("Contents") or []:
            key = str(row.get("Key") or "")
            if key.endswith(f"/{meta_name}"):
                keys.append(key)
    episodes: list[dict[str, Any]] = []
    for key in keys:
        meta = get_json(bucket, key, region=region)
        if meta:
            episodes.append(meta)
    episodes.sort(key=lambda m: int(m.get("episode_number") or 0), reverse=True)
    return episodes


def invalidate_feed(
    *,
    distribution_id: str,
    region: str | None = None,
    project_name: str | None = None,
) -> str:
    cfg = podcast_cfg()
    project = (project_name or str(cfg.get("project_name") or "the_war_room_001")).strip()
    layout = s3_layout(cfg)
    feed_path = "/" + layout["feed_key"].lstrip("/")
    cf = _client("cloudfront", region=region)
    resp = cf.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": [feed_path]},
            "CallerReference": f"{project}-feed-{time.time_ns()}",
        },
    )
    return str((resp.get("Invalidation") or {}).get("Id") or "")


def publish_episode_package(
    *,
    bucket: str,
    feed_base_url: str,
    distribution_id: str,
    episode_number: int,
    local_dir: Path,
    episode_meta: dict[str, Any],
    feed_xml: str,
    sequence: dict[str, Any],
    by_source_hash: dict[str, Any],
    by_execution_id: dict[str, Any] | None = None,
    show_artwork: Path | None = None,
    region: str | None = None,
    project_name: str | None = None,
) -> dict[str, Any]:
    """Upload one episode folder + catalogs + feed.xml, then invalidate CloudFront.

    Episode folder layout (see podcast.s3 in app.defaults.json)::

        episodes/NNNN/
          episode.json      # machine-readable meta (guid=execution_id, urls, …)
          description.txt   # plain description for retrieveability
          audio.mp3
          master.wav        # optional archive of the master
          cover.png
          chapters.json     # optional
    """
    cfg = podcast_cfg()
    layout = s3_layout(cfg)
    files = layout["episode_files"]
    prefix = episode_prefix(episode_number, cfg=cfg)
    upload_master = bool(cfg.get("upload_master_wav", True))

    local_to_remote = {
        files["audio"]: f"{prefix}/{files['audio']}",
        files["cover"]: f"{prefix}/{files['cover']}",
        files["meta"]: f"{prefix}/{files['meta']}",
        files["description"]: f"{prefix}/{files['description']}",
        files["chapters"]: f"{prefix}/{files['chapters']}",
    }
    if upload_master:
        local_to_remote[files["master"]] = f"{prefix}/{files['master']}"

    uploaded: list[str] = []
    for local_name, key in local_to_remote.items():
        path = local_dir / local_name
        if path.is_file():
            put_file(bucket=bucket, key=key, path=path, region=region)
            uploaded.append(key)

    # Ensure episode.json from meta even if not written locally
    put_bytes(
        bucket=bucket,
        key=f"{prefix}/{files['meta']}",
        body=json.dumps(episode_meta, indent=2).encode("utf-8"),
        region=region,
    )
    uploaded.append(f"{prefix}/{files['meta']}")

    description = str(episode_meta.get("description") or episode_meta.get("title") or "").strip()
    put_bytes(
        bucket=bucket,
        key=f"{prefix}/{files['description']}",
        body=(description + "\n").encode("utf-8"),
        region=region,
        content_type="text/plain; charset=utf-8",
    )
    uploaded.append(f"{prefix}/{files['description']}")

    catalog = layout["catalog_prefix"]
    put_bytes(
        bucket=bucket,
        key=f"{catalog}/sequence.json",
        body=json.dumps(sequence, indent=2).encode("utf-8"),
        region=region,
    )
    put_bytes(
        bucket=bucket,
        key=f"{catalog}/by_source_hash.json",
        body=json.dumps(by_source_hash, indent=2).encode("utf-8"),
        region=region,
    )
    if by_execution_id is not None:
        put_bytes(
            bucket=bucket,
            key=f"{catalog}/by_execution_id.json",
            body=json.dumps(by_execution_id, indent=2).encode("utf-8"),
            region=region,
        )

    show_prefix = layout["show_prefix"]
    if show_artwork and show_artwork.is_file():
        put_file(bucket=bucket, key=f"{show_prefix}/artwork.png", path=show_artwork, region=region)

    feed_key = layout["feed_key"]
    put_bytes(
        bucket=bucket,
        key=feed_key,
        body=feed_xml.encode("utf-8"),
        region=region,
        content_type="application/rss+xml",
        cache_control="max-age=0, must-revalidate",
    )
    inv_id = invalidate_feed(
        distribution_id=distribution_id,
        region=region,
        project_name=project_name,
    )
    base = feed_base_url.rstrip("/")
    return {
        "uploaded": uploaded,
        "s3_prefix": prefix,
        "feed_url": f"{base}/{feed_key}" if not base.endswith(feed_key) else base,
        "enclosure_url": f"{base}/{prefix}/{files['audio']}",
        "cover_url": f"{base}/{prefix}/{files['cover']}",
        "description_url": f"{base}/{prefix}/{files['description']}",
        "invalidation_id": inv_id,
        "episode_number": episode_number,
    }
