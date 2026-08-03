"""Unit tests for podcast RSS catalog, feed, cover theme, and OpenAI cover mocks."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

from interview_mux.podcast_rss.catalog import (
    allocate_episode_number,
    apply_version_suffix,
    prior_publish_count,
    record_execution,
    record_publish,
)
from interview_mux.podcast_rss.cover_prompt import (
    STYLE_CONTRACT_VERSION,
    STYLE_HEAD,
    assemble_prompt,
    build_style_head,
    contains_realism,
    harvest_motif_context,
    load_cover_theme,
    prompt_max_chars,
    refresh_style_head,
    validate_prompt,
)
from interview_mux.podcast_rss.cover_vision import pick_cover_winner
from interview_mux.podcast_rss.feed import build_feed_xml, channel_meta_from_config
from interview_mux.podcast_rss.openai_cover import generate_cover_candidates, resolve_cover_image_settings
from interview_mux.podcast_rss.s3_publish import cache_control_for_key, content_type_for_key
from interview_mux.podcast_rss.settings import episode_prefix, s3_layout


def test_apply_version_suffix_v2():
    assert apply_version_suffix("Hello World", prior_count=0) == "Hello World"
    assert apply_version_suffix("Hello World", prior_count=1) == "Hello World V2"
    assert apply_version_suffix("Hello World V2", prior_count=2) == "Hello World V3"


def test_allocate_and_record():
    n, seq = allocate_episode_number({"next_episode_number": 1})
    assert n == 1
    assert seq["next_episode_number"] == 2
    by = record_publish(
        {},
        source_audio_hash="abc",
        episode_number=1,
        title="T",
        execution_id="exec_1",
        published_at="2026-01-01T00:00:00Z",
        s3_prefix="episodes/0001",
    )
    assert prior_publish_count(by, "abc") == 1
    assert by["abc"][0]["s3_prefix"] == "episodes/0001"
    by_exec = record_execution(
        {},
        execution_id="exec_1",
        episode_number=1,
        title="T",
        source_audio_hash="abc",
        published_at="2026-01-01T00:00:00Z",
        s3_prefix="episodes/0001",
    )
    assert by_exec["exec_1"]["s3_prefix"] == "episodes/0001"


def test_episode_layout_prefix():
    assert episode_prefix(7) == "episodes/0007"
    layout = s3_layout(
        {
            "s3": {
                "episodes_prefix": "episodes",
                "episode_files": {"description": "description.txt"},
            }
        }
    )
    assert layout["episode_files"]["description"] == "description.txt"
    assert layout["episode_files"]["meta"] == "episode.json"


def test_feed_xml_contains_itunes_and_enclosure():
    channel = channel_meta_from_config(
        {
            "show_title": "The War Room",
            "show_author": "Nicket Uttarwar",
            "show_email": "contact.nicketuttarwar@gmail.com",
            "category": "Business",
        }
    )
    xml = build_feed_xml(
        channel=channel,
        feed_url="https://d111.cloudfront.net/feed.xml",
        show_artwork_url="https://d111.cloudfront.net/show/artwork.png",
        episodes=[
            {
                "title": "Ep One",
                "description": "Desc",
                "guid": "exec_1",
                "pub_date": "Mon, 01 Jan 2026 00:00:00 +0000",
                "enclosure_url": "https://d111.cloudfront.net/episodes/0001/audio.mp3",
                "enclosure_length": 1234,
                "duration_seconds": 125,
                "cover_url": "https://d111.cloudfront.net/episodes/0001/cover.png",
            }
        ],
    )
    assert "The War Room" in xml
    assert 'type="audio/mpeg"' in xml
    assert "itunes:category" in xml
    assert "Business" in xml
    assert "exec_1" in xml


def test_content_types():
    assert content_type_for_key("feed.xml") == "application/rss+xml"
    assert content_type_for_key("episodes/0001/audio.mp3") == "audio/mpeg"
    assert content_type_for_key("episodes/0001/cover.png") == "image/png"
    assert content_type_for_key("episodes/0001/description.txt") == "text/plain; charset=utf-8"
    assert "max-age=0" in cache_control_for_key("feed.xml")


def test_cover_theme_and_style_head_v2():
    theme = load_cover_theme()
    assert theme.get("version") == 2
    assert "cerulean" in (theme.get("required_accents") or [])
    head = refresh_style_head()
    assert STYLE_CONTRACT_VERSION == 2
    assert "cerulean" in head.lower()
    assert "crimson" in head.lower()
    assert "asterisk" in head.lower() or "***" in head
    assert "microphone" not in head.lower()
    assert "war room map" not in head.lower()
    assert build_style_head(theme).startswith("Square podcast")


def test_assemble_prompt_no_default_mic_map():
    refresh_style_head()
    prompt = assemble_prompt(["sealed envelope constellation", "fractured seal"])
    assert "ribbon" not in prompt.lower()
    assert "war room map" not in prompt.lower()
    assert "cerulean" in prompt.lower() and "crimson" in prompt.lower()
    assert "without" in prompt.lower()
    assert validate_prompt(prompt) == []
    assert not contains_realism(prompt)
    assert STYLE_HEAD  # module head present


def test_validate_prompt_rejects_realism_and_budget():
    refresh_style_head()
    bad = assemble_prompt(["x"]) + " photorealistic portrait"
    assert "realism_language" in validate_prompt(bad)
    huge = "cerulean crimson without photorealism " + ("motif " * 20000)
    errs = validate_prompt(huge, max_chars=100)
    assert any(e.startswith("over_budget") for e in errs)


def test_prompt_max_chars_from_cover_image_config():
    assert prompt_max_chars() >= 1000


def test_harvest_motif_context_from_artifacts():
    class _Ctx:
        def __init__(self):
            self._data = {
                "publish/episode_meta.json": {
                    "title": "Sealed Trust",
                    "description": "A talk about sealed deals.",
                },
                "understanding/content_brief.json": {
                    "thesis": "Trust fractures under opacity",
                    "topics": [{"name": "opacity"}, {"name": "contracts"}],
                },
                "master/selection.json": {"chapters": [{"title": "The seal"}]},
            }

        def artifact_exists(self, rel: str) -> bool:
            return rel in self._data

        def read_json(self, rel: str):
            return self._data[rel]

    h = harvest_motif_context(_Ctx())
    assert h["episode_title"] == "Sealed Trust"
    assert "opacity" in h["themes"]
    assert h["forbid_default_props"] is True
    assert "war-room" in h["note"].lower() or "map" in h["note"].lower()


def test_openai_cover_settings_pin():
    s = resolve_cover_image_settings()
    assert s["provider"] == "openai"
    assert s["model"] == "gpt-image-1"
    assert s["quality"] == "high"
    assert int(s["candidate_count"]) == 3


def test_generate_cover_candidates_n3_mock(tmp_path: Path):
    png = base64.b64encode(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    ).decode("ascii")

    class _Img:
        def __init__(self):
            self.b64_json = png

    class _Result:
        data = [_Img(), _Img(), _Img()]

    client = MagicMock()
    client.images.generate.return_value = _Result()

    settings = {
        "model": "gpt-image-1",
        "size": "1024x1024",
        "quality": "high",
        "candidate_count": 3,
        "min_output_px": 64,
        "style_reference": {"enabled": False},
    }
    with (
        patch("interview_mux.podcast_rss.openai_cover._client", return_value=client),
        patch("interview_mux.podcast_rss.openai_cover.ensure_square_min"),
    ):
        paths = generate_cover_candidates(
            prompt="test prompt cerulean crimson without letters",
            dest_dir=tmp_path / "cands",
            settings=settings,
        )
    assert len(paths) == 3
    assert all(p.is_file() for p in paths)
    client.images.generate.assert_called()
    call_kw = client.images.generate.call_args.kwargs
    assert call_kw.get("n") == 3
    assert call_kw.get("quality") == "high"


def test_vision_pick_brilliance_and_letter_disqualify(tmp_path: Path):
    paths = []
    for i in range(3):
        p = tmp_path / f"{i}.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([i]) * 32)
        paths.append(p)

    vision_payload = {
        "winner_index": 2,
        "ranking": [2, 0, 1],
        "brilliance_scores": [
            {"index": 0, "score": 0.7, "notes": "ok"},
            {"index": 1, "score": 0.6, "notes": "ok"},
            {"index": 2, "score": 0.95, "notes": "brilliant but lettered"},
        ],
        "disqualified": [{"index": 2, "reasons": ["readable_text"]}],
        "rationale": "2 is brilliant but lettered",
    }

    class _Msg:
        content = __import__("json").dumps(vision_payload)

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    client = MagicMock()
    client.chat.completions.create.return_value = _Resp()

    with (
        patch("interview_mux.podcast_rss.cover_vision.require_secret", return_value="sk-test"),
        patch("interview_mux.podcast_rss.cover_vision.OpenAI", return_value=client),
        patch(
            "interview_mux.podcast_rss.cover_vision.resolve_model",
            return_value=MagicMock(model_id="o3"),
        ),
        patch(
            "interview_mux.podcast_rss.cover_vision.load_system_prompt",
            return_value="pick brilliance",
        ),
    ):
        pick = pick_cover_winner(candidate_paths=paths, episode_title="T")

    # Lettered winner adjusted off index 2
    assert pick["winner_index"] != 2
    assert pick["winner_index"] in (0, 1)
    assert pick["pick_model"] == "o3"
