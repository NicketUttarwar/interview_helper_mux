"""Operator review + edit for G-Publish package metadata before S3 upload."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.podcast_rss.settings import podcast_id_from_ctx, s3_layout, show_cfg
from interview_mux.run_context import RunContext

_COVER_CANDIDATE_ROOT = "publish/cover_candidates"
_ALLOWED_COVER_PREFIXES = ("publish/cover_candidates/", "publish/")


def _podcast_cfg(ctx: RunContext) -> dict[str, Any]:
    return show_cfg(podcast_id_from_ctx(ctx))


def _resolve_publish_file(ctx: RunContext, rel: str) -> Path | None:
    staged = ctx.path(rel)
    if staged.is_file() and staged.stat().st_size > 0:
        return staged
    try:
        final = ctx.read_path(rel)
    except Exception:
        return None
    if final.is_file() and final.stat().st_size > 0:
        return final
    return None


def _cover_rel(ctx: RunContext) -> str:
    files = s3_layout(_podcast_cfg(ctx)).get("episode_files") or {}
    return f"publish/{files.get('cover') or 'cover.jpg'}"


def _list_cover_candidates(ctx: RunContext, *, selected_rel: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    selected = selected_rel.replace("\\", "/")
    if selected:
        out.append(
            {
                "path": selected,
                "label": "Current cover",
                "selected": True,
            }
        )
    root = ctx.run_dir / _COVER_CANDIDATE_ROOT
    if not root.is_dir():
        return out
    idx = 0
    seen = {selected} if selected else set()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        rel = path.relative_to(ctx.run_dir).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        idx += 1
        out.append(
            {
                "path": rel,
                "label": f"Candidate {idx}",
                "selected": False,
            }
        )
    return out


def load_g_publish_review(ctx: RunContext) -> dict[str, Any]:
    """Snapshot for the G-Publish review UI."""
    layout = s3_layout(_podcast_cfg(ctx))
    files = layout["episode_files"]
    cover_rel = _cover_rel(ctx)
    meta = (
        ctx.read_json("publish/episode_meta.json")
        if ctx.artifact_exists("publish/episode_meta.json")
        else {}
    )
    if not isinstance(meta, dict):
        meta = {}
    episode_doc = {}
    episode_rel = f"publish/{files['meta']}"
    ep_path = _resolve_publish_file(ctx, episode_rel)
    if ep_path and ep_path.suffix == ".json":
        try:
            raw = ctx.read_json(episode_rel)
            episode_doc = raw if isinstance(raw, dict) else {}
        except Exception:
            episode_doc = {}

    title = str(meta.get("title") or episode_doc.get("title") or "").strip()
    description = str(meta.get("description") or episode_doc.get("description") or "").strip()
    if not description and title:
        description = title

    cover_meta = (
        ctx.read_json("publish/cover_meta.json")
        if ctx.artifact_exists("publish/cover_meta.json")
        else {}
    )
    cover_path = _resolve_publish_file(ctx, cover_rel)
    master_master = _resolve_publish_file(ctx, "master/master.wav")
    master_pub = _resolve_publish_file(ctx, f"publish/{files['master']}")
    audio_mp3 = _resolve_publish_file(ctx, f"publish/{files['audio']}")

    package_ready = (
        ctx.read_json("publish/package_ready.json")
        if ctx.artifact_exists("publish/package_ready.json")
        else {}
    )
    ready = bool(isinstance(package_ready, dict) and package_ready.get("ready"))

    run_dir = str(ctx.run_dir)
    return {
        "title": title,
        "description": description,
        "word_count": len(description.split()) if description else 0,
        "cover": {
            "path": cover_rel if cover_path else None,
            "source": str((cover_meta or {}).get("cover_source") or "unknown"),
            "selected": cover_path is not None,
            "candidates": _list_cover_candidates(ctx, selected_rel=cover_rel if cover_path else ""),
        },
        "master": {
            "relative_path": "master/master.wav" if master_master else None,
            "absolute_path": str(master_master.resolve()) if master_master else None,
            "publish_relative": f"publish/{files['master']}" if master_pub else None,
            "publish_absolute": str(master_pub.resolve()) if master_pub else None,
        },
        "audio_mp3": {
            "relative_path": f"publish/{files['audio']}" if audio_mp3 else None,
            "absolute_path": str(audio_mp3.resolve()) if audio_mp3 else None,
        },
        "package_ready": ready,
        "run_dir": run_dir,
        "editable": True,
    }


def _assert_cover_path_allowed(path: str) -> str:
    normalized = path.replace("\\", "/").strip().lstrip("/")
    if not normalized.startswith(_ALLOWED_COVER_PREFIXES):
        raise ValueError(f"Cover path not allowed: {path}")
    if ".." in normalized.split("/"):
        raise ValueError(f"Cover path not allowed: {path}")
    return normalized


def apply_cover_from_path(ctx: RunContext, source_rel: str) -> str:
    """Copy a candidate (or prior cover) into the package cover slot."""
    from interview_mux.podcast_rss.openai_cover import ensure_square_cover, resolve_cover_image_settings

    source_rel = _assert_cover_path_allowed(source_rel)
    source = _resolve_publish_file(ctx, source_rel)
    if source is None:
        raise FileNotFoundError(f"Cover source missing: {source_rel}")

    cover_rel = _cover_rel(ctx)
    dest = ctx.path(cover_rel)
    settings = resolve_cover_image_settings(_podcast_cfg(ctx))
    ensure_square_cover(
        source,
        min_size=int(settings.get("min_output_px") or 3000),
        output_format=str(settings.get("output_format") or "jpeg"),
        jpeg_quality=int(settings.get("jpeg_quality") or 90),
        dest=dest,
    )
    final_cover = ctx.final_path("publish", cover_rel.split("/", 1)[-1])
    if dest.is_file() and dest.resolve() != final_cover.resolve():
        final_cover.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, final_cover)

    ctx.write_json(
        "publish/cover_meta.json",
        {
            "cover_source": "operator_selected",
            "path": cover_rel.split("/", 1)[-1],
            "operator_source": source_rel,
            "selected_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return cover_rel


def refresh_local_package_meta(ctx: RunContext, *, title: str, description: str) -> None:
    """Rewrite package markers after operator edits (no S3)."""
    layout = s3_layout(_podcast_cfg(ctx))
    files = layout["episode_files"]
    run_meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    source_hash = str((run_meta or {}).get("source_audio_hash") or "")
    execution_id = str((run_meta or {}).get("execution_id") or ctx.run_id)
    season = int(_podcast_cfg(ctx).get("season") or 1)
    prepared_at = datetime.now(timezone.utc).isoformat()

    title = title.strip() or "Untitled Episode"
    description = description.strip() or title

    ctx.write_json(
        "publish/episode_meta.json",
        {
            "title": title,
            "description": description,
            "word_count": len(description.split()),
            "operator_edited": True,
            "edited_at": prepared_at,
        },
    )

    cover_meta = (
        ctx.read_json("publish/cover_meta.json")
        if ctx.artifact_exists("publish/cover_meta.json")
        else {}
    )
    episode_draft = {
        "season": season,
        "title": title,
        "description": description,
        "guid": execution_id,
        "execution_id": execution_id,
        "podcast_id": podcast_id_from_ctx(ctx),
        "source_audio_hash": source_hash,
        "prepared_at": prepared_at,
        "package_status": "ready_local",
        "cover_source": (
            (cover_meta or {}).get("cover_source") if isinstance(cover_meta, dict) else "unknown"
        ),
        "operator_reviewed": True,
    }
    ctx.write_json(f"publish/{files['meta']}", episode_draft)
    ctx.path(f"publish/{files['description']}").write_text(description + "\n", encoding="utf-8")
    ctx.write_json(
        "publish/package_ready.json",
        {
            "ready": True,
            "prepared_at": prepared_at,
            "execution_id": execution_id,
            "title": title,
            "operator_reviewed": True,
            "files": {
                "audio": files["audio"],
                "master": files["master"],
                "cover": files["cover"],
                "chapters": files["chapters"],
                "transcript": files.get("transcript") or "transcript.vtt",
                "meta": files["meta"],
                "description": files["description"],
            },
        },
    )
    ctx.write_json(
        "publish/publish_result.json",
        {
            "local_package": True,
            "uploaded": False,
            "execution_id": execution_id,
            "title": title,
            "prepared_at": prepared_at,
            "operator_reviewed": True,
            "hint": "G-Publish → Upload this run to S3 (or scripts/sync_podcast_episodes.py --execution-id …)",
        },
    )


def save_g_publish_review(
    ctx: RunContext,
    *,
    title: str | None = None,
    description: str | None = None,
    cover_path: str | None = None,
) -> dict[str, Any]:
    """Persist operator edits and refresh local package metadata."""
    current = load_g_publish_review(ctx)
    new_title = str(title if title is not None else current.get("title") or "").strip()
    new_description = str(
        description if description is not None else current.get("description") or ""
    ).strip()
    if not new_title:
        raise ValueError("Episode title is required.")
    if not new_description:
        new_description = new_title

    if cover_path:
        apply_cover_from_path(ctx, cover_path)

    refresh_local_package_meta(ctx, title=new_title, description=new_description)
    ctx.log(
        f"G-Publish review saved — title={new_title[:80]!r}",
        level="action",
        stage="podcast_publish",
        detail={"cover_path": cover_path} if cover_path else None,
    )
    return load_g_publish_review(ctx)


def save_uploaded_cover(ctx: RunContext, uploaded: Path) -> dict[str, Any]:
    """Store an operator-uploaded image as the package cover."""
    from interview_mux.podcast_rss.openai_cover import ensure_square_cover, resolve_cover_image_settings

    if not uploaded.is_file():
        raise FileNotFoundError("Uploaded cover missing")
    settings = resolve_cover_image_settings(_podcast_cfg(ctx))
    staging = ctx.path("publish/_operator_cover_upload" + uploaded.suffix.lower())
    shutil.copy2(uploaded, staging)
    cover_rel = apply_cover_from_path(ctx, staging.relative_to(ctx.run_dir).as_posix())
    return {"ok": True, "cover_path": cover_rel}
