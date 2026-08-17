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
            "show_website": "https://nicketuttarwar.com/",
            "category": "Business",
            "subcategory": "Entrepreneurship",
            "show_type": "episodic",
            "season": 1,
            "podcast_guid": "62b2d127-c0c7-5c4f-bc0e-a309f2e6de01",
            "show_subtitle": "Business interviews",
        }
    )
    xml = build_feed_xml(
        channel=channel,
        feed_url="https://d111.cloudfront.net/feed.xml",
        show_artwork_url="https://d111.cloudfront.net/show/artwork.jpg",
        episodes=[
            {
                "title": "Ep One",
                "description": "Desc",
                "guid": "exec_1",
                "pub_date": "Mon, 01 Jan 2026 00:00:00 +0000",
                "enclosure_url": "https://d111.cloudfront.net/episodes/0001/audio.mp3",
                "enclosure_length": 1234,
                "duration_seconds": 125,
                "cover_url": "https://d111.cloudfront.net/episodes/0001/cover.jpg",
                "episode_number": 1,
                "season": 1,
                "chapters_url": "https://d111.cloudfront.net/episodes/0001/chapters.json",
                "transcript_url": "https://d111.cloudfront.net/episodes/0001/transcript.vtt",
                "link": "https://d111.cloudfront.net/episodes/0001/audio.mp3",
            }
        ],
    )
    assert "The War Room" in xml
    assert 'type="audio/mpeg"' in xml
    assert "itunes:category" in xml
    assert "Business" in xml
    assert "Entrepreneurship" in xml
    assert "<itunes:type>episodic</itunes:type>" in xml
    assert "<itunes:episode>1</itunes:episode>" in xml
    assert "<itunes:season>1</itunes:season>" in xml
    assert "podcast:guid" in xml
    assert "podcast:chapters" in xml
    assert 'type="text/vtt"' in xml
    assert "podcast:transcript" in xml
    assert "transcript.vtt" in xml
    assert "nicketuttarwar.com" in xml
    assert "content:encoded" in xml
    assert "exec_1" in xml


def test_content_types():
    assert content_type_for_key("feed.xml") == "application/rss+xml"
    assert content_type_for_key("episodes/0001/audio.mp3") == "audio/mpeg"
    assert content_type_for_key("episodes/0001/cover.jpg") == "image/jpeg"
    assert content_type_for_key("episodes/0001/cover.png") == "image/png"
    assert content_type_for_key("episodes/0001/description.txt") == "text/plain; charset=utf-8"
    assert content_type_for_key("episodes/0001/transcript.vtt") == "text/vtt; charset=utf-8"
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


def test_validate_prompt_rejects_person_likeness():
    refresh_style_head()
    base = assemble_prompt(["sealed envelope constellation"])
    assert validate_prompt(base) == []
    assert "person_likeness" in validate_prompt(
        base + " portrait of the founder"
    )
    # Missing dedicated no-person without-clause
    stripped = base.replace(
        "without any person likeness, human face, portrait, or identifiable people",
        "",
    )
    assert "missing_no_person_without_clause" in validate_prompt(stripped)


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
    assert int(s["min_output_px"]) == 3000
    assert str(s.get("output_format") or "").lower() in {"jpeg", "jpg"}


def test_timed_chapters_from_edl(tmp_path: Path):
    from interview_mux.podcast_rss.chapters import build_timed_chapters

    class _Ctx:
        def __init__(self):
            self._data = {
                "master/edl.json": {
                    "clips": [
                        {"type": "speech", "segment_id": "s1", "timeline_start_ms": 0},
                        {"type": "speech", "segment_id": "s2", "timeline_start_ms": 125000},
                    ]
                },
                "master/selection.json": {
                    "chapters": [
                        {"title": "Open", "segment_ids": ["s1"]},
                        {"title": "Turn", "anchor_segment_id": "s2"},
                    ]
                },
            }

        def artifact_exists(self, rel: str) -> bool:
            return rel in self._data

        def read_json(self, rel: str):
            return self._data[rel]

    doc = build_timed_chapters(_Ctx())
    assert doc["version"] == "1.2.0"
    assert doc["chapters"][0]["startTime"] == 0
    assert doc["chapters"][1]["startTime"] == 125.0
    assert doc["chapters"][1]["title"] == "Turn"


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

    def _fake_square(path: Path, *, min_size: int, output_format: str = "jpeg", jpeg_quality: int = 90, dest: Path | None = None):
        out = dest or path.with_suffix(".jpg")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-jpeg")
        return out

    settings = {
        "model": "gpt-image-1",
        "size": "1024x1024",
        "quality": "high",
        "candidate_count": 3,
        "min_output_px": 64,
        "output_format": "jpeg",
        "jpeg_quality": 85,
        "style_reference": {"enabled": False},
    }
    with (
        patch("interview_mux.podcast_rss.openai_cover._client", return_value=client),
        patch("interview_mux.podcast_rss.openai_cover.ensure_square_cover", side_effect=_fake_square),
    ):
        paths = generate_cover_candidates(
            prompt="test prompt cerulean crimson without letters",
            dest_dir=tmp_path / "cands",
            settings=settings,
        )
    assert len(paths) == 3
    assert all(p.is_file() for p in paths)
    assert all(p.suffix.lower() in {".jpg", ".jpeg"} for p in paths)
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


def _write_ready_package(exec_dir: Path, *, title: str = "Ready Ep") -> Path:
    publish = exec_dir / "publish"
    publish.mkdir(parents=True, exist_ok=True)
    for name in ("audio.mp3", "master.wav", "cover.jpg", "chapters.json", "transcript.vtt"):
        (publish / name).write_bytes(b"x" * 64)
    (publish / "episode_meta.json").write_text(
        __import__("json").dumps({"title": title, "description": "desc"}),
        encoding="utf-8",
    )
    (publish / "package_ready.json").write_text(
        __import__("json").dumps({"ready": True, "title": title}),
        encoding="utf-8",
    )
    (exec_dir / "run_meta.json").write_text(
        __import__("json").dumps(
            {
                "execution_id": exec_dir.name,
                "source_audio_hash": "abc123",
            }
        ),
        encoding="utf-8",
    )
    return publish


def test_package_is_complete_and_discover(tmp_path: Path):
    from interview_mux.podcast_rss.sync_assets import (
        discover_ready_packages,
        package_is_complete,
    )

    good = tmp_path / "exec_001_abcdefabcdef_20260101T000000Z"
    _write_ready_package(good)
    assert package_is_complete(good / "publish")

    incomplete = tmp_path / "exec_002_abcdefabcdef_20260101T000001Z"
    incomplete.mkdir()
    (incomplete / "publish").mkdir()
    (incomplete / "publish" / "audio.mp3").write_bytes(b"x")

    ready, already, incomplete_ids = discover_ready_packages(
        exec_root=tmp_path,
        by_execution_id={},
    )
    assert [p.execution_id for p in ready] == [good.name]
    assert incomplete.name in incomplete_ids
    assert already == []

    ready_one, _, incomplete_one = discover_ready_packages(
        exec_root=tmp_path,
        by_execution_id={},
        execution_id=good.name,
    )
    assert [p.execution_id for p in ready_one] == [good.name]
    assert incomplete_one == []

    ready2, already2, _ = discover_ready_packages(
        exec_root=tmp_path,
        by_execution_id={good.name: {"s3_prefix": "episodes/0001"}},
    )
    assert ready2 == []
    assert good.name in already2


def test_put_file_if_changed_skips_matching_size(tmp_path: Path):
    from interview_mux.podcast_rss import s3_publish

    local = tmp_path / "audio.mp3"
    local.write_bytes(b"0123456789")

    with (
        patch.object(s3_publish, "object_content_length", return_value=10),
        patch.object(s3_publish, "put_file") as put,
    ):
        changed = s3_publish.put_file_if_changed(
            bucket="b",
            key="episodes/0001/audio.mp3",
            path=local,
        )
    assert changed is False
    put.assert_not_called()

    with (
        patch.object(s3_publish, "object_content_length", return_value=None),
        patch.object(s3_publish, "put_file") as put2,
    ):
        changed2 = s3_publish.put_file_if_changed(
            bucket="b",
            key="episodes/0001/audio.mp3",
            path=local,
        )
    assert changed2 is True
    put2.assert_called_once()


def test_ensure_s3_prefixes_creates_only_missing_markers():
    from interview_mux.podcast_rss import s3_publish

    s3 = MagicMock()
    s3.list_objects_v2.side_effect = [
        {"KeyCount": 1},
        {"KeyCount": 0},
    ]

    with patch.object(s3_publish, "_client", return_value=s3):
        created = s3_publish.ensure_s3_prefixes(
            bucket="b",
            prefixes=["show", "/catalog/"],
            region="us-east-1",
        )

    assert created == ["catalog/"]
    s3.put_object.assert_called_once_with(
        Bucket="b",
        Key="catalog/",
        Body=b"",
        ContentType="application/x-directory",
        CacheControl="max-age=0, must-revalidate",
    )


def test_empty_bucket_deletes_versions_markers_and_current_objects():
    from interview_mux.podcast_rss import s3_publish

    s3 = MagicMock()
    s3.list_object_versions.side_effect = [
        {
            "Versions": [{"Key": "feed.xml", "VersionId": "v1"}],
            "DeleteMarkers": [{"Key": "old.xml", "VersionId": "d1"}],
        },
        {},
    ]
    s3.list_objects_v2.side_effect = [
        {"Contents": [{"Key": "catalog/"}]},
        {},
    ]
    s3.delete_objects.return_value = {}

    with patch.object(s3_publish, "_client", return_value=s3):
        deleted = s3_publish.empty_bucket("b", region="us-east-1")

    assert deleted == 3
    assert s3.delete_objects.call_count == 2


def test_sync_ready_packages_dry_run_skips_known_and_never_deletes(tmp_path: Path):
    from interview_mux.podcast_rss import sync_assets

    known = tmp_path / "exec_010_abcdefabcdef_20260101T000000Z"
    fresh = tmp_path / "exec_011_abcdefabcdef_20260101T000001Z"
    _write_ready_package(known, title="Known")
    _write_ready_package(fresh, title="Fresh")

    with (
        patch.object(
            sync_assets,
            "require_publish_ready",
            return_value={
                "bucket": "b",
                "region": "us-east-1",
                "distribution_id": "E123",
                "feed_base_url": "https://d.example",
                "project_name": "the_war_room_001",
            },
        ),
        patch.object(
            sync_assets,
            "get_json",
            return_value={"exec_010_abcdefabcdef_20260101T000000Z": {"s3_prefix": "episodes/0001"}},
        ),
        patch.object(sync_assets, "write_last_sync_result"),
        patch.object(sync_assets, "upload_episode_files") as upload,
    ):
        result = sync_assets.sync_ready_packages(
            dry_run=True, exec_root=tmp_path, all_ready=True
        )

    assert result.dry_run is True
    assert result.ready == 1
    assert result.uploaded[0]["execution_id"] == fresh.name
    assert known.name in result.skipped_already_uploaded
    upload.assert_not_called()
    # sync_assets must never expose/call S3 delete helpers
    assert not hasattr(sync_assets, "empty_bucket")


def test_sync_ready_packages_execution_id_ignores_siblings(tmp_path: Path):
    from interview_mux.podcast_rss import sync_assets

    sibling = tmp_path / "exec_020_abcdefabcdef_20260101T000000Z"
    current = tmp_path / "exec_021_abcdefabcdef_20260101T000001Z"
    _write_ready_package(sibling, title="Sibling")
    _write_ready_package(current, title="Current")

    with (
        patch.object(
            sync_assets,
            "require_publish_ready",
            return_value={
                "bucket": "b",
                "region": "us-east-1",
                "distribution_id": "E123",
                "feed_base_url": "https://d.example",
                "project_name": "the_war_room_001",
            },
        ),
        patch.object(sync_assets, "get_json", return_value={}),
        patch.object(sync_assets, "write_last_sync_result"),
        patch.object(sync_assets, "upload_episode_files") as upload,
    ):
        result = sync_assets.sync_ready_packages(
            dry_run=True,
            exec_root=tmp_path,
            execution_id=current.name,
        )

    assert result.ready == 1
    assert result.uploaded[0]["execution_id"] == current.name
    assert sibling.name not in [row.get("execution_id") for row in result.uploaded]
    assert result.scanned == 1
    upload.assert_not_called()


def test_sync_ready_packages_requires_scope():
    from interview_mux.podcast_rss import sync_assets

    result = sync_assets.sync_ready_packages(dry_run=True)
    assert result.errors
    assert "execution_id" in result.errors[0]["error"]
