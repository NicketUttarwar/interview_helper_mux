#!/usr/bin/env python3
"""Seed private podcast S3 origin after Terraform apply (./scripts/tf-apply.sh).

Bucket + region come from config/app.defaults.json ``podcast`` (non-secret).
AWS credentials come from config/secrets/secrets.env.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.config import repo_root  # noqa: E402
from interview_mux.podcast_rss.feed import build_feed_xml, channel_meta_from_config  # noqa: E402
from interview_mux.podcast_rss.s3_publish import put_bytes, put_file  # noqa: E402
from interview_mux.podcast_rss.settings import podcast_cfg, resolve_publish_targets, s3_layout  # noqa: E402


def main() -> int:
    cfg = podcast_cfg()
    targets = resolve_publish_targets()
    layout = s3_layout(cfg)
    bucket = targets["bucket"]
    base = targets["feed_base_url"]
    region = targets["region"]
    if not bucket:
        print("Need podcast.s3_bucket in config/app.defaults.json", file=sys.stderr)
        return 1
    if not base:
        print(
            "Need PODCAST_FEED_BASE_URL in secrets.env (run ./scripts/tf-apply.sh or sync_podcast_tf_secrets.sh)",
            file=sys.stderr,
        )
        return 1

    art_rel = str(cfg.get("show_artwork_path") or "config/podcast/the-war-room-cover.png")
    art = repo_root() / art_rel
    if not art.is_file():
        print(f"Missing show artwork: {art}", file=sys.stderr)
        return 1

    channel = channel_meta_from_config(cfg)
    feed_key = layout["feed_key"]
    show_prefix = layout["show_prefix"]
    catalog = layout["catalog_prefix"]
    feed_url = f"{base}/{feed_key}"
    art_url = f"{base}/{show_prefix}/artwork.png"
    feed = build_feed_xml(
        channel=channel,
        feed_url=feed_url,
        show_artwork_url=art_url,
        episodes=[],
    )
    put_file(bucket=bucket, key=f"{show_prefix}/artwork.png", path=art, region=region)
    put_bytes(
        bucket=bucket,
        key=f"{show_prefix}/show.json",
        body=json.dumps({**channel, "artwork": f"{show_prefix}/artwork.png"}, indent=2).encode(),
        region=region,
    )
    put_bytes(
        bucket=bucket,
        key=f"{catalog}/sequence.json",
        body=json.dumps({"next_episode_number": 1}, indent=2).encode(),
        region=region,
    )
    put_bytes(
        bucket=bucket,
        key=f"{catalog}/by_source_hash.json",
        body=b"{}",
        region=region,
    )
    put_bytes(
        bucket=bucket,
        key=f"{catalog}/by_execution_id.json",
        body=b"{}",
        region=region,
    )
    put_bytes(
        bucket=bucket,
        key=feed_key,
        body=feed.encode("utf-8"),
        region=region,
        content_type="application/rss+xml",
        cache_control="max-age=0, must-revalidate",
    )
    print(f"Seeded s3://{bucket} — feed {feed_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
