"""Build Apple/Spotify-compatible RSS 2.0 + iTunes tags."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape


def channel_meta_from_config(podcast_cfg: dict[str, Any]) -> dict[str, str]:
    return {
        "title": str(podcast_cfg.get("show_title") or "The War Room"),
        "author": str(podcast_cfg.get("show_author") or "Nicket Uttarwar"),
        "email": str(podcast_cfg.get("show_email") or "contact.nicketuttarwar@gmail.com"),
        "language": str(podcast_cfg.get("language") or "en-us"),
        "category": str(podcast_cfg.get("category") or "Business"),
        "explicit": str(podcast_cfg.get("explicit") or "false").lower(),
        "description": str(
            podcast_cfg.get("show_description")
            or "The War Room — long-form interviews produced for podcast listening."
        ),
    }


def rfc2822(dt: datetime | None = None) -> str:
    when = dt or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.strftime("%a, %d %b %Y %H:%M:%S %z")


def _esc(text: str) -> str:
    return escape(text or "", {"'": "&apos;", '"': "&quot;"})


def build_feed_xml(
    *,
    channel: dict[str, str],
    feed_url: str,
    show_artwork_url: str,
    episodes: list[dict[str, Any]],
) -> str:
    """Build RSS XML. Each episode needs title, description, guid, pub_date,
    enclosure_url, enclosure_length, duration_seconds, cover_url (optional).
    """
    title = _esc(channel["title"])
    author = _esc(channel["author"])
    email = _esc(channel["email"])
    language = _esc(channel.get("language") or "en-us")
    category = _esc(channel.get("category") or "Business")
    explicit = _esc(channel.get("explicit") or "false")
    description = _esc(channel.get("description") or channel["title"])
    link = _esc(feed_url.rsplit("/", 1)[0] + "/")
    self_link = _esc(feed_url)
    art = _esc(show_artwork_url)

    items: list[str] = []
    for ep in episodes:
        etitle = _esc(str(ep.get("title") or "Episode"))
        edesc = _esc(str(ep.get("description") or ""))
        guid = _esc(str(ep.get("guid") or ep.get("execution_id") or etitle))
        pub = _esc(str(ep.get("pub_date") or rfc2822()))
        enc_url = _esc(str(ep.get("enclosure_url") or ""))
        enc_len = int(ep.get("enclosure_length") or 0)
        dur = int(ep.get("duration_seconds") or 0)
        cover = _esc(str(ep.get("cover_url") or show_artwork_url))
        hh = dur // 3600
        mm = (dur % 3600) // 60
        ss = dur % 60
        itunes_dur = f"{hh}:{mm:02d}:{ss:02d}" if hh else f"{mm}:{ss:02d}"
        items.append(
            f"""    <item>
      <title>{etitle}</title>
      <description>{edesc}</description>
      <guid isPermaLink="false">{guid}</guid>
      <pubDate>{pub}</pubDate>
      <enclosure url="{enc_url}" length="{enc_len}" type="audio/mpeg"/>
      <itunes:title>{etitle}</itunes:title>
      <itunes:summary>{edesc}</itunes:summary>
      <itunes:duration>{itunes_dur}</itunes:duration>
      <itunes:explicit>{explicit}</itunes:explicit>
      <itunes:image href="{cover}"/>
    </item>"""
        )

    body = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{title}</title>
    <link>{link}</link>
    <description>{description}</description>
    <language>{language}</language>
    <atom:link href="{self_link}" rel="self" type="application/rss+xml"/>
    <itunes:author>{author}</itunes:author>
    <itunes:summary>{description}</itunes:summary>
    <itunes:explicit>{explicit}</itunes:explicit>
    <itunes:owner>
      <itunes:name>{author}</itunes:name>
      <itunes:email>{email}</itunes:email>
    </itunes:owner>
    <itunes:category text="{category}"/>
    <itunes:image href="{art}"/>
{body}
  </channel>
</rss>
"""
