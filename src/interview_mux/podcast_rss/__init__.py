"""Podcast RSS package — feed, catalog, S3 publish, encode, chapters."""

from interview_mux.podcast_rss.catalog import (
    apply_version_suffix,
    allocate_episode_number,
    load_by_source_hash,
    record_execution,
    record_publish,
)
from interview_mux.podcast_rss.chapters import build_timed_chapters
from interview_mux.podcast_rss.encode import encode_master_to_mp3
from interview_mux.podcast_rss.feed import build_feed_xml, channel_meta_from_config
from interview_mux.podcast_rss.s3_publish import (
    invalidate_current_feed,
    invalidate_feed,
    put_bytes,
    put_file,
    put_file_if_changed,
    publish_episode_package,
    retarget_public_feed,
    upload_episode_files,
)
from interview_mux.podcast_rss.settings import (
    apple_podcasts_passthrough_url,
    attach_apple_passthrough,
    default_podcast_id,
    episode_prefix,
    feed_url_from_base,
    format_apple_passthrough_notice,
    list_shows_public,
    normalize_podcast_id,
    podcast_cfg,
    print_apple_passthrough_notice,
    resolve_publish_targets,
    s3_layout,
    show_cfg,
)

__all__ = [
    "allocate_episode_number",
    "apple_podcasts_passthrough_url",
    "apply_version_suffix",
    "attach_apple_passthrough",
    "build_feed_xml",
    "build_timed_chapters",
    "channel_meta_from_config",
    "encode_master_to_mp3",
    "episode_prefix",
    "feed_url_from_base",
    "format_apple_passthrough_notice",
    "invalidate_current_feed",
    "print_apple_passthrough_notice",
    "invalidate_feed",
    "retarget_public_feed",
    "load_by_source_hash",
    "publish_episode_package",
    "put_bytes",
    "put_file",
    "put_file_if_changed",
    "record_execution",
    "record_publish",
    "default_podcast_id",
    "list_shows_public",
    "normalize_podcast_id",
    "podcast_cfg",
    "resolve_publish_targets",
    "show_cfg",
    "s3_layout",
    "upload_episode_files",
]
