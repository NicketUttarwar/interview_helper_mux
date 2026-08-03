#!/usr/bin/env python3
"""Seed private podcast S3 origin after Terraform apply (./scripts/tf-apply.sh).

Bucket + region come from config/app.defaults.json ``podcast`` (non-secret).
AWS credentials come from config/secrets/secrets.env (boto3 — no AWS CLI).
Infra must already exist via Terraform (scripts/tf-*.sh updates terraform/state/).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.config import repo_root  # noqa: E402
from interview_mux.podcast_rss.feed import build_feed_xml, channel_meta_from_config  # noqa: E402
from interview_mux.podcast_rss.openai_cover import ensure_square_cover, resolve_cover_image_settings  # noqa: E402
from interview_mux.podcast_rss.s3_publish import invalidate_feed, put_bytes, put_file  # noqa: E402
from interview_mux.podcast_rss.settings import (  # noqa: E402
    feed_url_from_base,
    podcast_cfg,
    require_publish_ready,
    s3_layout,
    show_artwork_s3_key,
)


def main() -> int:
    cfg = podcast_cfg()
    layout = s3_layout(cfg)
    try:
        targets = require_publish_ready()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    bucket = targets["bucket"]
    base = targets["feed_base_url"]
    region = targets["region"]
    dist_id = targets["distribution_id"]

    art_rel = str(cfg.get("show_artwork_path") or "config/podcast/the-war-room-cover.png")
    art_src = repo_root() / art_rel
    if not art_src.is_file():
        print(f"Missing show artwork: {art_src}", file=sys.stderr)
        return 1

    settings = resolve_cover_image_settings(cfg)
    art_jpg = repo_root() / "ASSETS" / "podcast" / "show_artwork.jpg"
    art_jpg.parent.mkdir(parents=True, exist_ok=True)
    ensure_square_cover(
        art_src,
        min_size=int(settings.get("min_output_px") or 3000),
        output_format="jpeg",
        jpeg_quality=int(settings.get("jpeg_quality") or 90),
        dest=art_jpg,
    )

    channel = channel_meta_from_config(cfg)
    feed_key = layout["feed_key"]
    catalog = layout["catalog_prefix"]
    art_key = show_artwork_s3_key(cfg)
    feed_url = feed_url_from_base(base, cfg=cfg)
    art_url = f"{base}/{art_key}"
    feed = build_feed_xml(
        channel=channel,
        feed_url=feed_url,
        show_artwork_url=art_url,
        episodes=[],
    )
    put_file(bucket=bucket, key=art_key, path=art_jpg, region=region)
    put_bytes(
        bucket=bucket,
        key=f"{layout['show_prefix']}/show.json",
        body=json.dumps({**channel, "artwork": art_key}, indent=2).encode(),
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
    inv_id = ""
    try:
        inv_id = invalidate_feed(
            distribution_id=dist_id,
            region=region,
            project_name=targets["project_name"],
        )
    except Exception as exc:
        print(f"Seeded but invalidation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Seeded s3://{bucket} — feed {feed_url} — invalidation {inv_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
