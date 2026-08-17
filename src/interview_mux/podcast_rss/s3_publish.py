"""S3 PutObject with explicit Content-Type / Cache-Control + CloudFront invalidation.

AWS access for operators: put credentials in ``config/secrets/secrets.env`` and use
Terraform (``scripts/tf-*.sh``) for infra. This module uses **boto3** only —
never shell out to the AWS CLI and never assume ``aws login``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from interview_mux.podcast_rss.settings import (
    episode_prefix,
    podcast_cfg,
    s3_layout,
    show_artwork_s3_key,
)

logger = logging.getLogger(__name__)

CONTENT_TYPES = {
    "feed.xml": "application/rss+xml",
    ".mp3": "audio/mpeg",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".vtt": "text/vtt; charset=utf-8",
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

    if not access and not profile and not os.environ.get("AWS_ACCESS_KEY_ID") and not os.environ.get("AWS_PROFILE"):
        # Still allow default credential chain, but surface a clear hint on failure
        pass

    if access and secret and not os.environ.get("AWS_ACCESS_KEY_ID"):
        session_kwargs["aws_access_key_id"] = access
        session_kwargs["aws_secret_access_key"] = secret
        if token:
            session_kwargs["aws_session_token"] = token
    elif profile and not os.environ.get("AWS_PROFILE"):
        session_kwargs["profile_name"] = profile

    if not access and not profile and not os.environ.get("AWS_ACCESS_KEY_ID") and not os.environ.get("AWS_PROFILE"):
        # Check secrets had nothing useful
        if not str(secrets.get("AWS_ACCESS_KEY_ID") or "").strip() and not str(
            secrets.get("AWS_PROFILE") or ""
        ).strip():
            # Ambient chain may still work (instance role / env); proceed
            pass

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


def ensure_s3_prefixes(
    *,
    bucket: str,
    prefixes: list[str],
    region: str | None = None,
) -> list[str]:
    """Ensure console-visible zero-byte markers for logical S3 folders.

    S3 accepts nested object keys without folders, but explicit markers make the
    configured layout visible immediately and support S3-compatible tooling that
    expects each parent prefix to exist. Returns the markers created.
    """
    s3 = _client("s3", region=region)
    created: list[str] = []
    for raw_prefix in prefixes:
        prefix = str(raw_prefix or "").strip().strip("/")
        if not prefix:
            continue
        marker = f"{prefix}/"
        try:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=marker, MaxKeys=1)
            if int(response.get("KeyCount") or 0) > 0:
                continue
            s3.put_object(
                Bucket=bucket,
                Key=marker,
                Body=b"",
                ContentType="application/x-directory",
                CacheControl="max-age=0, must-revalidate",
            )
            created.append(marker)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to ensure S3 prefix s3://{bucket}/{marker}: {exc}. "
                "Check S3 ListBucket and PutObject permissions."
            ) from exc
    return created


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
    try:
        _client("s3", region=region).put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=ctype,
            CacheControl=cache,
        )
    except Exception as exc:
        raise RuntimeError(
            f"S3 PutObject failed for s3://{bucket}/{key}: {exc}. "
            "Check AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in secrets.env."
        ) from exc


def put_file(
    *,
    bucket: str,
    key: str,
    path: Path,
    region: str | None = None,
) -> None:
    data = path.read_bytes()
    put_bytes(bucket=bucket, key=key, body=data, region=region)


def object_content_length(
    bucket: str,
    key: str,
    *,
    region: str | None = None,
) -> int | None:
    """Return remote ContentLength, or None if the object is missing."""
    try:
        resp = _client("s3", region=region).head_object(Bucket=bucket, Key=key)
        return int(resp.get("ContentLength") or 0)
    except Exception as exc:
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", "") or "")
        status = getattr(exc, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
            return None
        # Some endpoints surface 404 only in the message
        if "404" in str(exc) and "Not Found" in str(exc):
            return None
        logger.warning("head_object %s/%s failed: %s", bucket, key, exc)
        return None


def put_file_if_changed(
    *,
    bucket: str,
    key: str,
    path: Path,
    region: str | None = None,
) -> bool:
    """PutObject only when missing or size differs. Returns True if uploaded."""
    if not path.is_file():
        raise FileNotFoundError(f"Local file missing for upload: {path}")
    local_size = path.stat().st_size
    remote = object_content_length(bucket, key, region=region)
    if remote is not None and remote == local_size:
        logger.info("skip unchanged s3://%s/%s (%s bytes)", bucket, key, local_size)
        return False
    put_file(bucket=bucket, key=key, path=path, region=region)
    return True


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


def invalidate_paths(
    *,
    distribution_id: str,
    paths: list[str],
    region: str | None = None,
    project_name: str | None = None,
) -> str:
    cfg = podcast_cfg()
    project = (project_name or str(cfg.get("project_name") or "the_war_room_001")).strip()
    items = []
    for p in paths:
        p = str(p).strip()
        if not p:
            continue
        if not p.startswith("/"):
            p = "/" + p
        items.append(p)
    if not items:
        raise RuntimeError("No CloudFront invalidation paths provided")
    if not distribution_id:
        raise RuntimeError("PODCAST_CLOUDFRONT_DISTRIBUTION_ID required for invalidation")
    cf = _client("cloudfront", region=region)
    try:
        resp = cf.create_invalidation(
            DistributionId=distribution_id,
            InvalidationBatch={
                "Paths": {"Quantity": len(items), "Items": items},
                "CallerReference": f"{project}-inv-{time.time_ns()}",
            },
        )
    except Exception as exc:
        raise RuntimeError(
            f"CloudFront CreateInvalidation failed: {exc}. "
            "Check AWS credentials and PODCAST_CLOUDFRONT_DISTRIBUTION_ID."
        ) from exc
    return str((resp.get("Invalidation") or {}).get("Id") or "")


def invalidate_feed(
    *,
    distribution_id: str,
    region: str | None = None,
    project_name: str | None = None,
) -> str:
    layout = s3_layout(podcast_cfg())
    feed_path = "/" + layout["feed_key"].lstrip("/")
    return invalidate_paths(
        distribution_id=distribution_id,
        paths=[feed_path],
        region=region,
        project_name=project_name,
    )


def wait_invalidation(
    *,
    distribution_id: str,
    invalidation_id: str,
    region: str | None = None,
    timeout_sec: int = 300,
    poll_sec: float = 5.0,
) -> str:
    cf = _client("cloudfront", region=region)
    deadline = time.time() + max(30, int(timeout_sec))
    status = ""
    while time.time() < deadline:
        resp = cf.get_invalidation(DistributionId=distribution_id, Id=invalidation_id)
        status = str((resp.get("Invalidation") or {}).get("Status") or "")
        if status == "Completed":
            return status
        time.sleep(max(1.0, float(poll_sec)))
    raise RuntimeError(
        f"CloudFront invalidation {invalidation_id} not Completed within {timeout_sec}s "
        f"(last status={status or 'unknown'})"
    )


def empty_bucket(bucket: str, *, region: str | None = None) -> int:
    """Delete all objects (and delete markers) in a bucket. Returns deleted count."""
    s3 = _client("s3", region=region)
    deleted = 0

    def _delete_batch(objects: list[dict[str, str]]) -> None:
        nonlocal deleted
        if not objects:
            return
        for i in range(0, len(objects), 1000):
            chunk = objects[i : i + 1000]
            response = s3.delete_objects(Bucket=bucket, Delete={"Objects": chunk, "Quiet": True})
            errors = response.get("Errors") or []
            if errors:
                details = ", ".join(
                    f"{row.get('Key', '<unknown>')}: {row.get('Code', 'Error')}"
                    for row in errors
                )
                raise RuntimeError(f"S3 rejected one or more deletes in {bucket}: {details}")
            deleted += len(chunk)

    try:
        while True:
            page = s3.list_object_versions(Bucket=bucket, MaxKeys=1000)
            to_delete: list[dict[str, str]] = []
            for row in page.get("Versions") or []:
                key = row.get("Key")
                vid = row.get("VersionId")
                if key:
                    entry: dict[str, str] = {"Key": key}
                    if vid:
                        entry["VersionId"] = vid
                    to_delete.append(entry)
            for row in page.get("DeleteMarkers") or []:
                key = row.get("Key")
                vid = row.get("VersionId")
                if key:
                    entry = {"Key": key}
                    if vid:
                        entry["VersionId"] = vid
                    to_delete.append(entry)
            _delete_batch(to_delete)
            if not to_delete:
                break
    except Exception as exc:
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", "") or "")
        if code not in {"AccessDenied", "NotImplemented", "InvalidRequest"}:
            raise
        logger.info("list_object_versions unavailable for %s (%s); using list_objects_v2", bucket, exc)

    while True:
        page = s3.list_objects_v2(Bucket=bucket, MaxKeys=1000)
        objs = [{"Key": row["Key"]} for row in (page.get("Contents") or []) if row.get("Key")]
        _delete_batch(objs)
        if not objs:
            break
    return deleted


def upload_episode_files(
    *,
    bucket: str,
    episode_number: int,
    local_dir: Path,
    episode_meta: dict[str, Any],
    region: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Upload one episode folder with size-based skip. Never deletes remote objects."""
    cfg = podcast_cfg()
    layout = s3_layout(cfg)
    files = layout["episode_files"]
    prefix = episode_prefix(episode_number, cfg=cfg)

    required_locals = [files["audio"], files["master"], files["cover"], files["chapters"]]
    transcript_name = str(files.get("transcript") or "transcript.vtt")
    if transcript_name:
        required_locals.append(transcript_name)
    for name in required_locals:
        path = local_dir / name
        if not path.is_file() or path.stat().st_size < 1:
            raise RuntimeError(f"Required publish artifact missing or empty: {name}")

    ensure_s3_prefixes(
        bucket=bucket,
        prefixes=[layout["episodes_prefix"], prefix],
        region=region,
    )

    local_to_remote = {
        files["audio"]: f"{prefix}/{files['audio']}",
        files["cover"]: f"{prefix}/{files['cover']}",
        files["chapters"]: f"{prefix}/{files['chapters']}",
        files["master"]: f"{prefix}/{files['master']}",
    }
    if files.get("transcript"):
        local_to_remote[files["transcript"]] = f"{prefix}/{files['transcript']}"

    uploaded: list[str] = []
    skipped: list[str] = []
    for local_name, key in local_to_remote.items():
        path = local_dir / local_name
        if not path.is_file():
            continue
        if force:
            put_file(bucket=bucket, key=key, path=path, region=region)
            uploaded.append(key)
        elif put_file_if_changed(bucket=bucket, key=key, path=path, region=region):
            uploaded.append(key)
        else:
            skipped.append(key)

    meta_key = f"{prefix}/{files['meta']}"
    put_bytes(
        bucket=bucket,
        key=meta_key,
        body=json.dumps(episode_meta, indent=2).encode("utf-8"),
        region=region,
    )
    uploaded.append(meta_key)

    description = str(episode_meta.get("description") or episode_meta.get("title") or "").strip()
    desc_key = f"{prefix}/{files['description']}"
    put_bytes(
        bucket=bucket,
        key=desc_key,
        body=(description + "\n").encode("utf-8"),
        region=region,
        content_type="text/plain; charset=utf-8",
    )
    uploaded.append(desc_key)

    return {
        "uploaded": uploaded,
        "skipped_unchanged": skipped,
        "s3_prefix": prefix,
        "episode_number": episode_number,
    }


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
    write_feed: bool = True,
    invalidate: bool = True,
    force_files: bool = False,
) -> dict[str, Any]:
    """Upload one episode folder + catalogs (+ optional feed.xml / CloudFront invalidate).

    Episode folder layout (see podcast.s3 in app.defaults.json)::

        episodes/NNNN/
          episode.json
          description.txt
          audio.mp3
          master.wav
          cover.jpg
          chapters.json

    Never deletes remote objects.
    """
    cfg = podcast_cfg()
    layout = s3_layout(cfg)
    files = layout["episode_files"]

    file_result = upload_episode_files(
        bucket=bucket,
        episode_number=episode_number,
        local_dir=local_dir,
        episode_meta=episode_meta,
        region=region,
        force=force_files,
    )
    uploaded: list[str] = list(file_result["uploaded"])
    skipped: list[str] = list(file_result.get("skipped_unchanged") or [])
    prefix = str(file_result["s3_prefix"])

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

    art_key = show_artwork_s3_key(cfg)
    if show_artwork and show_artwork.is_file():
        if force_files:
            put_file(bucket=bucket, key=art_key, path=show_artwork, region=region)
            uploaded.append(art_key)
        elif put_file_if_changed(bucket=bucket, key=art_key, path=show_artwork, region=region):
            uploaded.append(art_key)
        else:
            skipped.append(art_key)

    feed_key = layout["feed_key"]
    inv_id = ""
    if write_feed:
        put_bytes(
            bucket=bucket,
            key=feed_key,
            body=feed_xml.encode("utf-8"),
            region=region,
            content_type="application/rss+xml",
            cache_control="max-age=0, must-revalidate",
        )
    if invalidate:
        inv_id = invalidate_feed(
            distribution_id=distribution_id,
            region=region,
            project_name=project_name,
        )
    base = feed_base_url.rstrip("/")
    return {
        "uploaded": uploaded,
        "skipped_unchanged": skipped,
        "s3_prefix": prefix,
        "feed_url": f"{base}/{feed_key}" if not base.endswith(feed_key) else base,
        "enclosure_url": f"{base}/{prefix}/{files['audio']}",
        "cover_url": f"{base}/{prefix}/{files['cover']}",
        "description_url": f"{base}/{prefix}/{files['description']}",
        "chapters_url": f"{base}/{prefix}/{files['chapters']}",
        "transcript_url": f"{base}/{prefix}/{files['transcript']}" if files.get("transcript") else "",
        "invalidation_id": inv_id,
        "episode_number": episode_number,
    }
