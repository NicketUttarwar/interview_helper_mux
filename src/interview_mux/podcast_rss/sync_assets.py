"""Scan ASSETS/executions for ready episode packages and upload to S3 (additive only).

Never deletes remote objects. Skips executions already present in by_execution_id.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.assets_ephemeral_cleanup import executions_root, is_product_execution_dir
from interview_mux.config import repo_root
from interview_mux.podcast_rss.catalog import (
    allocate_episode_number,
    apply_version_suffix,
    episode_folder,
    load_by_source_hash,
    prior_publish_count,
    record_execution,
    record_publish,
)
from interview_mux.podcast_rss.feed import build_feed_xml, channel_meta_from_config, rfc2822
from interview_mux.podcast_rss.s3_publish import (
    ensure_s3_prefixes,
    get_json,
    invalidate_feed,
    list_episode_metas,
    put_bytes,
    put_file_if_changed,
    upload_episode_files,
)
from interview_mux.podcast_rss.settings import (
    episode_prefix,
    feed_url_from_base,
    podcast_cfg,
    require_publish_ready,
    s3_layout,
    show_artwork_s3_key,
)

logger = logging.getLogger(__name__)


@dataclass
class ReadyPackage:
    execution_id: str
    run_dir: Path
    publish_dir: Path
    source_audio_hash: str
    title: str
    description: str
    cover_source: str = "unknown"


@dataclass
class SyncResult:
    dry_run: bool = False
    scanned: int = 0
    ready: int = 0
    uploaded: list[dict[str, Any]] = field(default_factory=list)
    skipped_already_uploaded: list[str] = field(default_factory=list)
    skipped_incomplete: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    invalidation_id: str = ""
    feed_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "scanned": self.scanned,
            "ready": self.ready,
            "uploaded": list(self.uploaded),
            "skipped_already_uploaded": list(self.skipped_already_uploaded),
            "skipped_incomplete": list(self.skipped_incomplete),
            "errors": list(self.errors),
            "invalidation_id": self.invalidation_id,
            "feed_url": self.feed_url,
            "uploaded_count": len(self.uploaded),
            "skipped_already_uploaded_count": len(self.skipped_already_uploaded),
        }


def _probe_duration_seconds(path: Path) -> int:
    import shutil
    import subprocess

    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not path.is_file():
        return 0
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return 0
    try:
        data = json.loads(proc.stdout or "{}")
        return int(float((data.get("format") or {}).get("duration") or 0))
    except Exception:
        return 0


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def package_is_complete(publish_dir: Path, *, layout: dict[str, Any] | None = None) -> bool:
    """True when publish/ has the episode files required for S3 upload."""
    files = (layout or s3_layout())["episode_files"]
    required = [
        files["audio"],
        files["master"],
        files["cover"],
        files["chapters"],
    ]
    for name in required:
        path = publish_dir / name
        if not path.is_file() or path.stat().st_size < 1:
            return False
    meta = _read_json(publish_dir / "episode_meta.json")
    episode = _read_json(publish_dir / files["meta"])
    title = str(meta.get("title") or episode.get("title") or "").strip()
    if not title:
        return False
    ready = publish_dir / "package_ready.json"
    if ready.is_file():
        return True
    # Accept packages that finished the local finalize stage without the marker
    # (legacy) if all required files + title exist.
    return True


def discover_ready_packages(
    *,
    exec_root: Path | None = None,
    by_execution_id: dict[str, Any] | None = None,
) -> tuple[list[ReadyPackage], list[str], list[str]]:
    """Return (ready, already_uploaded_ids, incomplete_ids)."""
    root = exec_root if exec_root is not None else executions_root()
    layout = s3_layout()
    files = layout["episode_files"]
    known = by_execution_id if isinstance(by_execution_id, dict) else {}
    ready: list[ReadyPackage] = []
    already: list[str] = []
    incomplete: list[str] = []

    if not root.is_dir():
        return ready, already, incomplete

    for child in sorted(root.iterdir()):
        if not child.is_dir() or not is_product_execution_dir(child.name):
            continue
        execution_id = child.name
        publish_dir = child / "publish"
        if execution_id in known:
            already.append(execution_id)
            continue
        if not package_is_complete(publish_dir, layout=layout):
            incomplete.append(execution_id)
            continue
        run_meta = _read_json(child / "run_meta.json")
        episode_meta = _read_json(publish_dir / "episode_meta.json")
        episode_doc = _read_json(publish_dir / files["meta"])
        cover_meta = _read_json(publish_dir / "cover_meta.json")
        title = str(
            episode_meta.get("title")
            or episode_doc.get("title")
            or "Untitled Episode"
        ).strip()
        description = str(
            episode_meta.get("description")
            or episode_doc.get("description")
            or title
        ).strip()
        source_hash = str(
            run_meta.get("source_audio_hash")
            or episode_doc.get("source_audio_hash")
            or ""
        )
        ready.append(
            ReadyPackage(
                execution_id=execution_id,
                run_dir=child,
                publish_dir=publish_dir,
                source_audio_hash=source_hash,
                title=title,
                description=description,
                cover_source=str(cover_meta.get("cover_source") or "unknown"),
            )
        )
    return ready, already, incomplete


def last_sync_result_path() -> Path:
    return repo_root() / "ASSETS" / "podcast" / "last_sync_result.json"


def write_last_sync_result(result: SyncResult | dict[str, Any]) -> Path:
    path = last_sync_result_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict() if isinstance(result, SyncResult) else dict(result)
    payload["finished_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def read_last_sync_result() -> dict[str, Any]:
    return _read_json(last_sync_result_path())


def _prepared_show_artwork() -> Path | None:
    from interview_mux.podcast_rss.openai_cover import ensure_square_cover, resolve_cover_image_settings

    cfg = podcast_cfg()
    rel = str(cfg.get("show_artwork_path") or "config/podcast/the-war-room-cover.png")
    src = repo_root() / rel
    if not src.is_file():
        return None
    settings = resolve_cover_image_settings()
    dest = repo_root() / "ASSETS" / "podcast" / "show_artwork.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    return ensure_square_cover(
        src,
        min_size=int(settings.get("min_output_px") or 3000),
        output_format="jpeg",
        jpeg_quality=int(settings.get("jpeg_quality") or 90),
        dest=dest,
    )


def sync_ready_packages(
    *,
    dry_run: bool = False,
    force_files: bool = False,
    exec_root: Path | None = None,
) -> SyncResult:
    """Upload all complete local packages not yet in the S3 execution catalog.

    Never deletes S3 objects. One feed rebuild + one CloudFront invalidation at end
    when any new episode was uploaded.
    """
    result = SyncResult(dry_run=dry_run)
    cfg = podcast_cfg()
    if not bool(cfg.get("enabled", True)):
        result.errors.append({"error": "podcast.enabled is false"})
        return result

    layout = s3_layout(cfg)
    files = layout["episode_files"]
    catalog_prefix = layout["catalog_prefix"]

    try:
        targets = require_publish_ready()
    except RuntimeError as exc:
        result.errors.append({"error": str(exc)})
        return result

    bucket = targets["bucket"]
    region = targets["region"]
    base = targets["feed_base_url"]
    dist_id = targets["distribution_id"]
    project_name = targets["project_name"]
    result.feed_url = feed_url_from_base(base)

    by_exec_raw = get_json(bucket, f"{catalog_prefix}/by_execution_id.json", region=region) or {}
    ready, already, incomplete = discover_ready_packages(
        exec_root=exec_root,
        by_execution_id=by_exec_raw if isinstance(by_exec_raw, dict) else {},
    )
    root = exec_root if exec_root is not None else executions_root()
    result.scanned = sum(
        1
        for child in (root.iterdir() if root.is_dir() else [])
        if child.is_dir() and is_product_execution_dir(child.name)
    )
    result.ready = len(ready)
    result.skipped_already_uploaded = list(already)
    result.skipped_incomplete = list(incomplete)

    if dry_run:
        for pkg in ready:
            result.uploaded.append(
                {
                    "execution_id": pkg.execution_id,
                    "title": pkg.title,
                    "would_upload": True,
                }
            )
        write_last_sync_result(result)
        return result

    if not ready:
        write_last_sync_result(result)
        return result

    ensure_s3_prefixes(
        bucket=bucket,
        prefixes=[
            layout["show_prefix"],
            catalog_prefix,
            layout["episodes_prefix"],
        ],
        region=region,
    )

    sequence = get_json(bucket, f"{catalog_prefix}/sequence.json", region=region) or {
        "next_episode_number": 1
    }
    by_hash_raw = get_json(bucket, f"{catalog_prefix}/by_source_hash.json", region=region) or {}
    by_hash = load_by_source_hash(by_hash_raw)
    by_execution = dict(by_exec_raw) if isinstance(by_exec_raw, dict) else {}
    season = int(cfg.get("season") or 1)
    show_art = _prepared_show_artwork()
    new_episode_docs: list[dict[str, Any]] = []

    for pkg in ready:
        try:
            if pkg.execution_id in by_execution:
                result.skipped_already_uploaded.append(pkg.execution_id)
                continue
            prior = prior_publish_count(by_hash, pkg.source_audio_hash) if pkg.source_audio_hash else 0
            title = apply_version_suffix(pkg.title, prior_count=prior)
            episode_number, sequence = allocate_episode_number(sequence)
            prefix = episode_prefix(episode_number)
            mp3 = pkg.publish_dir / files["audio"]
            duration = _probe_duration_seconds(mp3)
            published_at = datetime.now(timezone.utc).isoformat()
            enclosure_url = f"{base}/{prefix}/{files['audio']}"
            cover_url = f"{base}/{prefix}/{files['cover']}"
            description_url = f"{base}/{prefix}/{files['description']}"
            chapters_url = f"{base}/{prefix}/{files['chapters']}"
            episode_doc = {
                "episode_number": episode_number,
                "season": season,
                "title": title,
                "description": pkg.description,
                "guid": pkg.execution_id,
                "execution_id": pkg.execution_id,
                "source_audio_hash": pkg.source_audio_hash,
                "s3_prefix": prefix,
                "pub_date": rfc2822(),
                "published_at": published_at,
                "enclosure_url": enclosure_url,
                "enclosure_length": mp3.stat().st_size if mp3.is_file() else 0,
                "duration_seconds": duration,
                "cover_url": cover_url,
                "description_url": description_url,
                "chapters_url": chapters_url,
                "link": enclosure_url,
                "cover_source": pkg.cover_source,
            }
            # Persist final episode.json locally for operator reference
            (pkg.publish_dir / files["meta"]).write_text(
                json.dumps(episode_doc, indent=2) + "\n",
                encoding="utf-8",
            )
            (pkg.publish_dir / files["description"]).write_text(
                pkg.description + "\n",
                encoding="utf-8",
            )

            upload = upload_episode_files(
                bucket=bucket,
                episode_number=episode_number,
                local_dir=pkg.publish_dir,
                episode_meta=episode_doc,
                region=region,
                force=force_files,
            )
            by_hash = record_publish(
                by_hash,
                source_audio_hash=pkg.source_audio_hash or pkg.execution_id,
                episode_number=episode_number,
                title=title,
                execution_id=pkg.execution_id,
                published_at=published_at,
                s3_prefix=prefix,
            )
            by_execution = record_execution(
                by_execution,
                execution_id=pkg.execution_id,
                episode_number=episode_number,
                title=title,
                source_audio_hash=pkg.source_audio_hash,
                published_at=published_at,
                s3_prefix=prefix,
            )
            new_episode_docs.append(episode_doc)
            sync_meta = {
                **upload,
                "execution_id": pkg.execution_id,
                "title": title,
                "folder": episode_folder(episode_number),
                "enclosure_url": enclosure_url,
            }
            (pkg.publish_dir / "publish_result.json").write_text(
                json.dumps({**sync_meta, "synced_at": published_at}, indent=2) + "\n",
                encoding="utf-8",
            )
            result.uploaded.append(sync_meta)
            logger.info(
                "Synced %s → %s (%s)",
                pkg.execution_id,
                prefix,
                title,
            )
        except Exception as exc:
            logger.exception("Failed to sync %s", pkg.execution_id)
            result.errors.append({"execution_id": pkg.execution_id, "error": str(exc)})

    if not new_episode_docs:
        write_last_sync_result(result)
        return result

    # Write catalogs once after the batch
    put_bytes(
        bucket=bucket,
        key=f"{catalog_prefix}/sequence.json",
        body=json.dumps(sequence, indent=2).encode("utf-8"),
        region=region,
    )
    put_bytes(
        bucket=bucket,
        key=f"{catalog_prefix}/by_source_hash.json",
        body=json.dumps(by_hash, indent=2).encode("utf-8"),
        region=region,
    )
    put_bytes(
        bucket=bucket,
        key=f"{catalog_prefix}/by_execution_id.json",
        body=json.dumps(by_execution, indent=2).encode("utf-8"),
        region=region,
    )

    if show_art and show_art.is_file():
        art_key = show_artwork_s3_key(cfg)
        if force_files:
            from interview_mux.podcast_rss.s3_publish import put_file

            put_file(bucket=bucket, key=art_key, path=show_art, region=region)
        else:
            put_file_if_changed(bucket=bucket, key=art_key, path=show_art, region=region)

    channel = channel_meta_from_config(cfg)
    existing = list_episode_metas(bucket, region=region)
    new_guids = {str(e.get("guid") or e.get("execution_id") or "") for e in new_episode_docs}
    existing = [e for e in existing if str(e.get("guid") or e.get("execution_id") or "") not in new_guids]
    feed_episodes = list(new_episode_docs) + existing
    art_key = show_artwork_s3_key(cfg)
    feed_xml = build_feed_xml(
        channel=channel,
        feed_url=feed_url_from_base(base),
        show_artwork_url=f"{base}/{art_key}",
        episodes=feed_episodes,
    )
    feed_key = layout["feed_key"]
    put_bytes(
        bucket=bucket,
        key=feed_key,
        body=feed_xml.encode("utf-8"),
        region=region,
        content_type="application/rss+xml",
        cache_control="max-age=0, must-revalidate",
    )
    result.invalidation_id = invalidate_feed(
        distribution_id=dist_id,
        region=region,
        project_name=project_name,
    )
    result.feed_url = feed_url_from_base(base)
    write_last_sync_result(result)
    return result


def sync_status_summary(*, exec_root: Path | None = None) -> dict[str, Any]:
    """Counts for GUI without uploading (uses local discovery + optional remote catalog)."""
    cfg = podcast_cfg()
    if not bool(cfg.get("enabled", True)):
        return {
            "enabled": False,
            "ready_package_count": 0,
            "already_uploaded_count": 0,
            "incomplete_count": 0,
            "last_sync": read_last_sync_result(),
        }
    by_exec: dict[str, Any] = {}
    try:
        targets = require_publish_ready()
        layout = s3_layout()
        by_exec = get_json(
            targets["bucket"],
            f"{layout['catalog_prefix']}/by_execution_id.json",
            region=targets["region"],
        ) or {}
    except Exception as exc:
        logger.info("sync status: catalog unavailable (%s); local-only counts", exc)
    ready, already, incomplete = discover_ready_packages(
        exec_root=exec_root,
        by_execution_id=by_exec if isinstance(by_exec, dict) else {},
    )
    return {
        "enabled": True,
        "ready_package_count": len(ready),
        "already_uploaded_count": len(already),
        "incomplete_count": len(incomplete),
        "ready_execution_ids": [p.execution_id for p in ready],
        "last_sync": read_last_sync_result(),
    }
