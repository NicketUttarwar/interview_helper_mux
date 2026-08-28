"""Tests for G-Publish operator review helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.g_publish_review import (
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
    exec_root = tmp_path / "executions"
    exec_root.mkdir()
    run_dir = exec_root / RUN_ID
    run_dir.mkdir()
    _seed_publish_tree(run_dir)
    monkeypatch.setenv("MUX_EXECUTIONS_ROOT", str(exec_root))
    monkeypatch.setattr(
        "interview_mux.g_publish_review.show_cfg",
        lambda podcast_id=None: {"season": 1, "show_title": "Test Show", "enabled": True},
    )
    monkeypatch.setattr(
        "interview_mux.g_publish_review.podcast_id_from_ctx",
        lambda ctx: "zero_shot_podcast_demo",
    )
    ctx = RunContext(RUN_ID, create=False)
    ctx.write_json(
        "publish/episode_meta.json",
        {"title": "Old Title", "description": "Old description text."},
    )
    return ctx


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


def test_refresh_local_package_meta_writes_episode_json(review_ctx: RunContext) -> None:
    refresh_local_package_meta(review_ctx, title="Ship Title", description="Ship notes.")
    episode = json.loads((review_ctx.run_dir / "publish" / "episode.json").read_text(encoding="utf-8"))
    assert episode["title"] == "Ship Title"
    assert (review_ctx.run_dir / "publish" / "description.txt").read_text(encoding="utf-8").startswith(
        "Ship notes"
    )
