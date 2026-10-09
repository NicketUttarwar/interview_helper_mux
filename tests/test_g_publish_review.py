"""Tests for G-Publish operator review helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.g_publish_review import (
    ensure_local_package_for_upload,
    load_g_publish_review,
    refresh_local_package_meta,
    save_g_publish_review,
)
from interview_mux.run_context import RunContext

RUN_ID = "exec_199_abcdefabcdef_20260828T120000Z"


def _seed_publish_tree(run_dir: Path) -> None:
    publish = run_dir / "publish"
    publish.mkdir(parents=True, exist_ok=True)
    (publish / "cover.jpg").write_bytes(b"fake-jpeg")
    (publish / "audio.mp3").write_bytes(b"mp3")
    (publish / "master.wav").write_bytes(b"wav")
    (publish / "chapters.json").write_text("{}", encoding="utf-8")
    (publish / "transcript.vtt").write_text("WEBVTT\n", encoding="utf-8")
    (run_dir / "master" / "master.wav").parent.mkdir(parents=True, exist_ok=True)
    (run_dir / "master" / "master.wav").write_bytes(b"master")
    (publish / "episode_meta.json").write_text(
        json.dumps({"title": "Old Title", "description": "Old description text."}),
        encoding="utf-8",
    )
    (run_dir / "run_meta.json").write_text(
        json.dumps({"execution_id": run_dir.name, "source_audio_hash": "abc"}),
        encoding="utf-8",
    )


@pytest.fixture
def review_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setattr(
        "interview_mux.g_publish_review.show_cfg",
        lambda podcast_id=None: {"season": 1, "show_title": "Test Show", "enabled": True},
    )
    monkeypatch.setattr(
        "interview_mux.g_publish_review.podcast_id_from_ctx",
        lambda ctx: "zero_shot_podcast_demo",
    )
    ctx = RunContext(RUN_ID, create=True)
    _seed_publish_tree(ctx.run_dir)
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "transcript.vtt").write_text("WEBVTT\n", encoding="utf-8")
    ctx.write_json(
        "publish/episode_meta.json",
        {"title": "Old Title", "description": "Old description text."},
    )
    return ctx


def test_cover_candidates_are_three_unique_images(review_ctx: RunContext) -> None:
    root = review_ctx.run_dir / "publish" / "cover_candidates"
    batch = root / "batch_0"
    batch.mkdir(parents=True)
    for index, payload in enumerate((b"cover-a", b"cover-b", b"cover-c")):
        (batch / f"{index}.png").write_bytes(payload + b"-png")
        (batch / f"{index}.jpg").write_bytes(payload)
        (root / f"{index}.jpg").write_bytes(payload)
    (review_ctx.run_dir / "publish" / "cover.jpg").write_bytes(b"cover-b")
    review_ctx.write_json("publish/cover_meta.json", {"winner_index": 1, "cover_source": "openai_generated"})

    review = load_g_publish_review(review_ctx)
    candidates = review["cover"]["candidates"]
    assert [row["label"] for row in candidates] == ["Candidate 1", "Candidate 2", "Candidate 3"]
    assert [row["path"] for row in candidates] == [
        "publish/cover_candidates/0.jpg",
        "publish/cover_candidates/1.jpg",
        "publish/cover_candidates/2.jpg",
    ]
    assert [row["selected"] for row in candidates] == [False, True, False]


def test_load_g_publish_review_paths(review_ctx: RunContext) -> None:
    review = load_g_publish_review(review_ctx)
    assert review["title"] == "Old Title"
    assert "Old description" in review["description"]
    assert review["editable"] is True


def test_save_g_publish_review_updates_package(review_ctx: RunContext) -> None:
    saved = save_g_publish_review(
        review_ctx,
        title="New Episode Title",
        description="Updated show notes for the episode.",
    )
    assert saved["title"] == "New Episode Title"
    run_dir = review_ctx.run_dir
    meta = json.loads((run_dir / "publish" / "episode_meta.json").read_text(encoding="utf-8"))
    assert meta["title"] == "New Episode Title"
    assert meta["operator_edited"] is True
    ready = json.loads((run_dir / "publish" / "package_ready.json").read_text(encoding="utf-8"))
    assert ready["ready"] is True
    assert ready["title"] == "New Episode Title"


def test_upload_click_packages_when_files_are_missing_then_returns_ready(review_ctx: RunContext, monkeypatch) -> None:
    """One Upload click must not wait on a second prepare button."""
    called: list[str] = []

    def _publish(ctx: RunContext) -> None:
        called.append(ctx.run_id)
        publish = ctx.run_dir / "publish"
        for name in (
            "audio.mp3",
            "master.wav",
            "cover.jpg",
            "chapters.json",
            "transcript.vtt",
            "episode.json",
            "description.txt",
        ):
            target = publish / name
            if not target.is_file():
                target.write_bytes(b"x")

    monkeypatch.setattr("interview_mux.stages.podcast_publish.run_podcast_publish", _publish)
    publish = review_ctx.run_dir / "publish"
    (publish / "chapters.json").unlink(missing_ok=True)
    (publish / "transcript.vtt").unlink(missing_ok=True)

    missing = ensure_local_package_for_upload(review_ctx)

    assert called == [review_ctx.run_id]
    assert missing == []
    assert review_ctx.read_json("run_meta.json").get("g_publish_cleared") is True


def test_upload_click_skips_repackage_when_the_package_is_already_complete(
    review_ctx: RunContext, monkeypatch
) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        "interview_mux.stages.podcast_publish.run_podcast_publish",
        lambda ctx: called.append(ctx.run_id),
    )
    # episode.json and description.txt are the remaining required names.
    (review_ctx.run_dir / "publish" / "episode.json").write_text("{}", encoding="utf-8")
    (review_ctx.run_dir / "publish" / "description.txt").write_text("notes", encoding="utf-8")

    missing = ensure_local_package_for_upload(review_ctx)

    assert called == []
    assert missing == []


def test_refresh_local_package_meta_writes_episode_json(review_ctx: RunContext) -> None:
    refresh_local_package_meta(review_ctx, title="Ship Title", description="Ship notes.")
    episode = json.loads((review_ctx.run_dir / "publish" / "episode.json").read_text(encoding="utf-8"))
    assert episode["title"] == "Ship Title"
    assert (review_ctx.run_dir / "publish" / "description.txt").read_text(encoding="utf-8").startswith(
        "Ship notes"
    )
