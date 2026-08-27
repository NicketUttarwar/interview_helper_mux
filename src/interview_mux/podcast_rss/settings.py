"""Resolve podcast runtime settings: git catalog + shared app.defaults + secrets.

Split:
  - Per-show identity and destinations → ``config/podcast/catalog.json``
    (id, title, artwork, s3_bucket, cloudfront_distribution_id, feed_base_url)
  - Shared pipeline defaults → config/app.defaults.json ``podcast``
    (S3 key layout, mp3 settings, OpenAI cover cascade)
  - Credentials only → config/secrets/secrets.env (AWS_*)

Catalog is the source of truth for the Start picker and for which S3 bucket /
CloudFront distribution a run publishes to. The GUI never creates AWS resources.

Whenever a public RSS ``feed_url`` is printed or shown, also emit Apple's
Podcasts Connect pass-through (``apple_podcasts_passthrough_url``) plus the
empty-feed notice. Scripts source ``scripts/lib/apple_podcasts_passthrough.sh``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import quote, urlparse

from interview_mux.config import load_secrets, merged_config, repo_root

PODCAST_CATALOG_REL = "config/podcast/catalog.json"
DEFAULT_PODCAST_ID = "zero_shot_podcast_demo"
DEFAULT_SHOW_ARTWORK_REL = "config/podcast/shows/zero_shot_podcast_demo/artwork.png"
_PODCAST_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

# Apple's documented add-show pass-through. ``submitfeed`` is the public RSS
# URL (https://podcasters.apple.com/support/829-validate-your-podcast).
# Encode the query value so a copy-paste / href cannot inject extra params.
APPLE_PODCASTS_CONNECT_NEW_FEED = "https://podcastsconnect.apple.com/my-podcasts/new-feed"

# Extra notice printed after every pass-through URL. Apple validates the live
# feed; an empty seed (no <item>) is rejected even when this URL is used.
APPLE_PODCASTS_PASSTHROUGH_NOTICE = (
    "Notice: Apple Podcasts Connect rejects an empty seed feed (no episodes). "
    "Publish at least one episode or a trailer, then open the pass-through URL. "
    "It only pre-fills the RSS field; it does not skip validation."
)

_IDENTITY_KEYS = (
    "project_name",
    "s3_bucket",
    "aws_region",
    "show_title",
    "show_author",
    "show_email",
    "show_website",
    "language",
    "category",
    "subcategory",
    "show_type",
    "season",
    "explicit",
    "show_subtitle",
    "show_description",
    "podcast_guid",
    "show_artwork_path",
    "cover_theme_path",
    "cloudfront_distribution_id",
    "feed_base_url",
)


def shared_podcast_cfg() -> dict[str, Any]:
    cfg = merged_config().get("podcast") or {}
    return dict(cfg) if isinstance(cfg, dict) else {}


def load_podcast_catalog() -> dict[str, Any]:
    path = repo_root() / PODCAST_CATALOG_REL
    if not path.is_file():
        return {"version": 1, "default_podcast_id": DEFAULT_PODCAST_ID, "shows": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "default_podcast_id": DEFAULT_PODCAST_ID, "shows": []}
    return data if isinstance(data, dict) else {"version": 1, "default_podcast_id": DEFAULT_PODCAST_ID, "shows": []}


def default_podcast_id() -> str:
    catalog = load_podcast_catalog()
    raw = str(catalog.get("default_podcast_id") or DEFAULT_PODCAST_ID).strip()
    return raw or DEFAULT_PODCAST_ID


def list_catalog_shows() -> list[dict[str, Any]]:
    catalog = load_podcast_catalog()
    shows = catalog.get("shows")
    if not isinstance(shows, list):
        return []
    return [dict(row) for row in shows if isinstance(row, dict) and str(row.get("id") or "").strip()]


def get_catalog_show(podcast_id: str | None = None) -> dict[str, Any]:
    pid = normalize_podcast_id(podcast_id)
    for row in list_catalog_shows():
        if str(row.get("id") or "").strip() == pid:
            return dict(row)
    raise ValueError(f"Unknown podcast_id {pid!r} — add it to {PODCAST_CATALOG_REL}")


def normalize_podcast_id(raw: str | None) -> str:
    text = str(raw or "").strip()
    if not text:
        return default_podcast_id()
    if not _PODCAST_ID_RE.match(text):
        raise ValueError(f"Invalid podcast_id {text!r}")
    ids = {str(row.get("id") or "").strip() for row in list_catalog_shows()}
    if text not in ids:
        raise ValueError(f"Unknown podcast_id {text!r} — add it to {PODCAST_CATALOG_REL}")
    return text


def podcast_id_from_meta(meta: dict[str, Any] | None) -> str:
    if not isinstance(meta, dict):
        return default_podcast_id()
    raw = meta.get("podcast_id")
    if raw is None or str(raw).strip() == "":
        return default_podcast_id()
    try:
        return normalize_podcast_id(str(raw))
    except ValueError:
        return default_podcast_id()


def podcast_id_from_ctx(ctx: Any) -> str:
    meta: dict[str, Any] = {}
    try:
        if ctx.artifact_exists("run_meta.json"):
            loaded = ctx.read_json("run_meta.json") or {}
            if isinstance(loaded, dict):
                meta = loaded
    except Exception:
        meta = {}
    return podcast_id_from_meta(meta)


def podcast_id_from_execution(execution_id: str | None, *, exec_root: Path | None = None) -> str:
    eid = str(execution_id or "").strip()
    if not eid:
        return default_podcast_id()
    root = exec_root
    if root is None:
        from interview_mux.assets_ephemeral_cleanup import executions_root

        root = executions_root()
    path = Path(root) / eid / "run_meta.json"
    if not path.is_file():
        return default_podcast_id()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_podcast_id()
    return podcast_id_from_meta(data if isinstance(data, dict) else {})


def stamp_podcast_meta(ctx: Any, raw: str | None = None) -> str:
    """Persist podcast_id on a new run. Never overwrite mid-run."""
    existing = ""
    if ctx.artifact_exists("run_meta.json"):
        existing = str((ctx.read_json("run_meta.json") or {}).get("podcast_id") or "").strip()
    if existing:
        try:
            return normalize_podcast_id(existing)
        except ValueError:
            pass
    pid = normalize_podcast_id(raw)
    show = get_catalog_show(pid)
    title = str(show.get("title") or show.get("show_title") or pid)

    def _stamp(meta: dict[str, Any]) -> None:
        if str(meta.get("podcast_id") or "").strip():
            return
        meta["podcast_id"] = pid
        meta["podcast_title"] = title

    ctx.mutate_run_meta(_stamp)
    return pid


def _map_catalog_show(show: dict[str, Any]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    pid = str(show.get("id") or "").strip()
    if pid:
        mapped["podcast_id"] = pid
    title = str(show.get("title") or show.get("show_title") or "").strip()
    if title:
        mapped["show_title"] = title
    art = str(show.get("artwork_path") or show.get("show_artwork_path") or "").strip()
    if art:
        mapped["show_artwork_path"] = art
    theme = str(show.get("cover_theme_path") or "").strip()
    if theme:
        mapped["cover_theme_path"] = theme
    for key in _IDENTITY_KEYS:
        if key in mapped:
            continue
        if key in show and show[key] not in (None, ""):
            mapped[key] = show[key]
    return mapped


def show_cfg(podcast_id: str | None = None) -> dict[str, Any]:
    """Merge shared pipeline defaults with one catalog show."""
    shared = shared_podcast_cfg()
    show = get_catalog_show(podcast_id)
    out = {k: v for k, v in shared.items() if not str(k).startswith("_")}
    out.update(_map_catalog_show(show))
    art = str(out.get("show_artwork_path") or DEFAULT_SHOW_ARTWORK_REL)
    cover = out.get("cover_image") if isinstance(out.get("cover_image"), dict) else {}
    if cover:
        cover = dict(cover)
        ref = dict(cover.get("style_reference") or {}) if isinstance(cover.get("style_reference"), dict) else {}
        if art:
            ref["path"] = art
        cover["style_reference"] = ref
        out["cover_image"] = cover
    if not out.get("show_artwork_path"):
        out["show_artwork_path"] = DEFAULT_SHOW_ARTWORK_REL
    if not out.get("cover_theme_path"):
        out["cover_theme_path"] = "config/podcast/shows/zero_shot_podcast_demo/cover_theme.json"
    return out


def podcast_cfg(podcast_id: str | None = None) -> dict[str, Any]:
    """Alias for ``show_cfg`` — default show when ``podcast_id`` is omitted."""
    return show_cfg(podcast_id)


def list_shows_public() -> dict[str, Any]:
    default_id = default_podcast_id()
    shows: list[dict[str, Any]] = []
    for row in list_catalog_shows():
        pid = str(row.get("id") or "").strip()
        if not pid:
            continue
        art_rel = str(row.get("artwork_path") or row.get("show_artwork_path") or "").strip()
        art_path = (repo_root() / art_rel) if art_rel else None
        has_art = bool(art_path and art_path.is_file())
        shows.append(
            {
                "id": pid,
                "title": str(row.get("title") or row.get("show_title") or pid),
                "is_default": pid == default_id,
                "has_artwork": has_art,
                "feed_base_url": str(row.get("feed_base_url") or "").rstrip("/"),
                "artwork_url": f"/api/podcasts/{pid}/artwork" if has_art else None,
            }
        )
    return {"default": default_id, "shows": shows}


def show_artwork_file(podcast_id: str | None = None) -> Path:
    cfg = show_cfg(podcast_id)
    return show_artwork_source_path(cfg)


def show_artwork_source_rel(cfg: dict[str, Any] | None = None) -> str:
    root = cfg if cfg is not None else show_cfg()
    return str(root.get("show_artwork_path") or DEFAULT_SHOW_ARTWORK_REL)


def show_artwork_source_path(cfg: dict[str, Any] | None = None) -> Path:
    return repo_root() / show_artwork_source_rel(cfg)


def s3_layout(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    root = cfg if cfg is not None else show_cfg()
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


def resolve_publish_targets(podcast_id: str | None = None) -> dict[str, str]:
    """Bucket/CF/feed from the catalog show; AWS creds remain in secrets.

    Secrets ``PODCAST_CLOUDFRONT_*`` / ``PODCAST_FEED_BASE_URL`` are a one-release
    fallback for the default show only.
    """
    cfg = show_cfg(podcast_id)
    secrets = load_secrets()
    pid = str(cfg.get("podcast_id") or default_podcast_id())
    bucket = str(cfg.get("s3_bucket") or "").strip()
    if pid == default_podcast_id() and not bucket:
        bucket = str(secrets.get("PODCAST_S3_BUCKET") or "").strip()
    region = str(
        cfg.get("aws_region")
        or secrets.get("AWS_DEFAULT_REGION")
        or secrets.get("AWS_REGION")
        or "us-east-1"
    ).strip()
    dist_id = str(cfg.get("cloudfront_distribution_id") or "").strip()
    feed_base = str(cfg.get("feed_base_url") or "").rstrip("/")
    if pid == default_podcast_id():
        if not dist_id:
            dist_id = str(secrets.get("PODCAST_CLOUDFRONT_DISTRIBUTION_ID") or "").strip()
        if not feed_base:
            feed_base = str(secrets.get("PODCAST_FEED_BASE_URL") or "").rstrip("/")
        if secrets.get("PODCAST_S3_BUCKET") and not cfg.get("s3_bucket"):
            bucket = str(secrets.get("PODCAST_S3_BUCKET") or "").strip()
    project = str(cfg.get("project_name") or pid or "podcast").strip()
    return {
        "podcast_id": pid,
        "bucket": bucket,
        "region": region,
        "distribution_id": dist_id,
        "feed_base_url": feed_base,
        "project_name": project,
    }


def feed_url_from_base(feed_base: str | None = None, *, cfg: dict[str, Any] | None = None) -> str:
    if feed_base is None:
        pid = None
        if isinstance(cfg, dict):
            pid = cfg.get("podcast_id")
        base = resolve_publish_targets(pid if isinstance(pid, str) else None)["feed_base_url"]
    else:
        base = feed_base
    base = base.rstrip("/")
    layout = s3_layout(cfg)
    key = layout["feed_key"]
    if not base:
        return ""
    if base.endswith(key):
        return base
    return f"{base}/{key}"


def normalize_public_feed_url(feed_url: str | None) -> str:
    """Return a public http(s) RSS URL safe to print / put in an href, else ``""``.

    Rejects credentials, non-http schemes, and characters that would break a
    shell or HTML attribute. Does not fetch the URL.
    """
    text = str(feed_url or "").strip()
    if not text or any(ch in text for ch in "\r\n\t \"'<>\\"):
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in ("https", "http"):
        return ""
    if parsed.username or parsed.password or not parsed.netloc:
        return ""
    return text


def apple_podcasts_passthrough_url(feed_url: str | None) -> str:
    """Apple Podcasts Connect pass-through that pre-fills ``submitfeed``.

    Safe to display: only http(s) public feeds; ``submitfeed`` is percent-encoded.
    Returns ``""`` when ``feed_url`` is missing or not a public RSS URL.
    """
    feed = normalize_public_feed_url(feed_url)
    if not feed:
        return ""
    return f"{APPLE_PODCASTS_CONNECT_NEW_FEED}?submitfeed={quote(feed, safe='')}"


def format_apple_passthrough_notice(feed_url: str | None, *, include_feed: bool = True) -> str:
    """Operator-facing block: feed URL, pass-through, then the empty-feed notice."""
    feed = normalize_public_feed_url(feed_url)
    passthrough = apple_podcasts_passthrough_url(feed)
    if not passthrough:
        return ""
    lines: list[str] = []
    if include_feed:
        lines.append(f"RSS feed URL: {feed}")
    lines.append("Apple Podcasts Connect pass-through (copy this; pre-fills the RSS field):")
    lines.append(f"  {passthrough}")
    lines.append("")
    lines.append(APPLE_PODCASTS_PASSTHROUGH_NOTICE)
    return "\n".join(lines)


def print_apple_passthrough_notice(
    feed_url: str | None,
    *,
    include_feed: bool = True,
    file: TextIO | None = None,
) -> None:
    """Print the pass-through + notice whenever a new/public RSS URL is shown."""
    block = format_apple_passthrough_notice(feed_url, include_feed=include_feed)
    if block:
        print(block, file=file)


def attach_apple_passthrough(payload: dict[str, Any]) -> dict[str, Any]:
    """Add ``apple_podcasts_passthrough_url`` next to ``feed_url`` on a payload."""
    feed = str(payload.get("feed_url") or "")
    payload["apple_podcasts_passthrough_url"] = apple_podcasts_passthrough_url(feed)
    return payload


def require_publish_ready(
    *,
    local_dir: Path | None = None,
    podcast_id: str | None = None,
) -> dict[str, str]:
    """Fail fast before any S3 PutObject. Returns resolved targets."""
    cfg = show_cfg(podcast_id)
    if not bool(cfg.get("enabled", True)):
        raise RuntimeError("podcast.enabled is false — enable it in config/app.defaults.json")
    email = str(cfg.get("show_email") or "").strip()
    if not email or "@" not in email:
        raise RuntimeError(
            f"show_email missing or invalid for podcast_id={cfg.get('podcast_id')!r} "
            f"in {PODCAST_CATALOG_REL}"
        )

    targets = resolve_publish_targets(podcast_id)
    bucket = targets["bucket"]
    dist_id = targets["distribution_id"]
    base = targets["feed_base_url"]
    pid = targets.get("podcast_id") or default_podcast_id()
    if not bucket:
        raise RuntimeError(
            f"s3_bucket missing for podcast_id={pid!r} in {PODCAST_CATALOG_REL}"
        )
    if not dist_id:
        raise RuntimeError(
            f"cloudfront_distribution_id missing for podcast_id={pid!r} in {PODCAST_CATALOG_REL} "
            "— record it after a terminal terraform apply"
        )
    if not base:
        raise RuntimeError(
            f"feed_base_url missing for podcast_id={pid!r} in {PODCAST_CATALOG_REL} "
            "— record it after a terminal terraform apply"
        )

    override = str(load_secrets().get("PODCAST_S3_BUCKET") or "").strip()
    if pid == default_podcast_id() and override and override != bucket:
        raise RuntimeError(
            f"PODCAST_S3_BUCKET={override!r} disagrees with catalog s3_bucket={bucket!r}. "
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
        _require_cover_min_px(local_dir / files["cover"], min_px=1400, cfg=cfg)

    return targets


def _require_cover_min_px(path: Path, *, min_px: int = 1400, cfg: dict[str, Any] | None = None) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to validate cover dimensions") from exc
    with Image.open(path) as im:
        w, h = im.size
    root = cfg if cfg is not None else show_cfg()
    if w < min_px or h < min_px:
        raise RuntimeError(
            f"Cover art {path.name} is {w}x{h}; Apple requires at least {min_px}x{min_px} "
            f"(target {root.get('cover_image', {}).get('min_output_px', 3000)}px)"
        )


def episode_prefix(episode_number: int, *, cfg: dict[str, Any] | None = None) -> str:
    layout = s3_layout(cfg)
    folder = f"{int(episode_number):04d}"
    return f"{layout['episodes_prefix']}/{folder}"
