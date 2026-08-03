"""Build Apple/Spotify-compatible RSS 2.0 + iTunes + Podcasting 2.0 tags."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape


def channel_meta_from_config(podcast_cfg: dict[str, Any]) -> dict[str, str]:
    return {
        "title": str(podcast_cfg.get("show_title") or "The War Room"),
        "author": str(podcast_cfg.get("show_author") or "Nicket Uttarwar"),
        "email": str(podcast_cfg.get("show_email") or "contact.nicketuttarwar@gmail.com"),
        "website": str(podcast_cfg.get("show_website") or "https://nicketuttarwar.com/").rstrip("/")
        + "/",
        "language": str(podcast_cfg.get("language") or "en-us"),
        "category": str(podcast_cfg.get("category") or "Business"),
        "subcategory": str(podcast_cfg.get("subcategory") or "Entrepreneurship"),
        "show_type": str(podcast_cfg.get("show_type") or "episodic").lower(),
        "explicit": str(podcast_cfg.get("explicit") or "false").lower(),
        "subtitle": str(
            podcast_cfg.get("show_subtitle")
            or "Long-form business interviews on building, judgment, and decisions."
        ),
        "description": str(
            podcast_cfg.get("show_description")
            or "The War Room is a long-form business interview podcast."
        ),
        "podcast_guid": str(podcast_cfg.get("podcast_guid") or "").strip(),
        "season": str(int(podcast_cfg.get("season") or 1)),
    }


def rfc2822(dt: datetime | None = None) -> str:
    when = dt or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.strftime("%a, %d %b %Y %H:%M:%S %z")


def _esc(text: str) -> str:
    return escape(text or "", {"'": "&apos;", '"': "&quot;"})


def _content_encoded(text: str) -> str:
    """Wrap plain description as minimal HTML for content:encoded."""
    body = _esc(text).replace("\n", "<br/>")
    return f"<![CDATA[<p>{body}</p>]]>"


def build_feed_xml(
    *,
    channel: dict[str, str],
    feed_url: str,
    show_artwork_url: str,
    episodes: list[dict[str, Any]],
) -> str:
    """Build RSS XML for Apple Podcasts / Spotify.

    Each episode needs title, description, guid, pub_date, enclosure_url,
    enclosure_length, duration_seconds, cover_url, episode_number, season,
    chapters_url (optional).
    """
    title = _esc(channel["title"])
    author = _esc(channel["author"])
    email = _esc(channel["email"])
    language = _esc(channel.get("language") or "en-us")
    category = _esc(channel.get("category") or "Business")
    subcategory = _esc(channel.get("subcategory") or "")
    show_type = _esc(channel.get("show_type") or "episodic")
    explicit = _esc(channel.get("explicit") or "false")
    subtitle = _esc(channel.get("subtitle") or channel["title"])
    description = _esc(channel.get("description") or channel["title"])
    website = _esc(channel.get("website") or (feed_url.rsplit("/", 1)[0] + "/"))
    self_link = _esc(feed_url)
    art = _esc(show_artwork_url)
    podcast_guid = _esc(channel.get("podcast_guid") or "")
    default_season = int(channel.get("season") or 1)

    if subcategory:
        category_xml = (
            f'    <itunes:category text="{category}">\n'
            f'      <itunes:category text="{subcategory}"/>\n'
            f"    </itunes:category>"
        )
    else:
        category_xml = f'    <itunes:category text="{category}"/>'

    guid_xml = f"    <podcast:guid>{podcast_guid}</podcast:guid>\n" if podcast_guid else ""

    items: list[str] = []
    for ep in episodes:
        etitle = _esc(str(ep.get("title") or "Episode"))
        edesc_raw = str(ep.get("description") or "")
        edesc = _esc(edesc_raw)
        guid = _esc(str(ep.get("guid") or ep.get("execution_id") or etitle))
        pub = _esc(str(ep.get("pub_date") or rfc2822()))
        enc_url = _esc(str(ep.get("enclosure_url") or ""))
        enc_len = int(ep.get("enclosure_length") or 0)
        dur = int(ep.get("duration_seconds") or 0)
        cover = _esc(str(ep.get("cover_url") or show_artwork_url))
        ep_num = int(ep.get("episode_number") or 0)
        season = int(ep.get("season") or default_season)
        item_link = _esc(str(ep.get("link") or ep.get("enclosure_url") or enc_url))
        chapters_url = str(ep.get("chapters_url") or "").strip()
        hh = dur // 3600
        mm = (dur % 3600) // 60
        ss = dur % 60
        itunes_dur = f"{hh}:{mm:02d}:{ss:02d}" if hh else f"{mm}:{ss:02d}"
        chapters_xml = ""
        if chapters_url:
            chapters_xml = (
                f'\n      <podcast:chapters url="{_esc(chapters_url)}" '
                f'type="application/json+chapters"/>'
            )
        items.append(
            f"""    <item>
      <title>{etitle}</title>
      <description>{edesc}</description>
      <content:encoded>{_content_encoded(edesc_raw)}</content:encoded>
      <link>{item_link}</link>
      <guid isPermaLink="false">{guid}</guid>
      <pubDate>{pub}</pubDate>
      <enclosure url="{enc_url}" length="{enc_len}" type="audio/mpeg"/>
      <itunes:title>{etitle}</itunes:title>
      <itunes:summary>{edesc}</itunes:summary>
      <itunes:duration>{itunes_dur}</itunes:duration>
      <itunes:explicit>{explicit}</itunes:explicit>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:season>{season}</itunes:season>
      <itunes:episode>{ep_num}</itunes:episode>
      <itunes:image href="{cover}"/>{chapters_xml}
    </item>"""
        )

    body = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:atom="http://www.w3.org/2005/Atom"
  xmlns:podcast="https://podcastindex.org/namespace/1.0">
  <channel>
    <title>{title}</title>
    <link>{website}</link>
    <description>{description}</description>
    <language>{language}</language>
    <atom:link href="{self_link}" rel="self" type="application/rss+xml"/>
{guid_xml}    <itunes:author>{author}</itunes:author>
    <itunes:summary>{description}</itunes:summary>
    <itunes:subtitle>{subtitle}</itunes:subtitle>
    <itunes:explicit>{explicit}</itunes:explicit>
    <itunes:type>{show_type}</itunes:type>
    <itunes:owner>
      <itunes:name>{author}</itunes:name>
      <itunes:email>{email}</itunes:email>
    </itunes:owner>
{category_xml}
    <itunes:image href="{art}"/>
{body}
  </channel>
</rss>
"""
