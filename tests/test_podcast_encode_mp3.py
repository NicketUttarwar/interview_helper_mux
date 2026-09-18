"""PEM-B1: podcast_encode_mp3 incompleteness honesty (no real ffmpeg encode)."""

from __future__ import annotations

from interview_mux.stage_completion import heal_or_raise, stage_artifact_incompleteness
from run_fixtures import isolated_run_ctx


def test_missing_mp3_is_incomplete(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pem_missing_mp3")
    reason = stage_artifact_incompleteness(ctx, "podcast_encode_mp3")
    assert reason is not None
    assert "encode_missing" in reason
    assert "publish/audio.mp3" in reason


def test_empty_mp3_is_incomplete(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pem_empty_mp3")
    dest = ctx.path("publish/audio.mp3")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"")
    reason = stage_artifact_incompleteness(ctx, "podcast_encode_mp3")
    assert reason is not None
    assert "encode_missing" in reason
    assert "empty" in reason or "incomplete" in reason


def test_tiny_mp3_is_incomplete(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pem_tiny_mp3")
    dest = ctx.path("publish/audio.mp3")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"x" * 100)
    reason = stage_artifact_incompleteness(ctx, "podcast_encode_mp3")
    assert reason is not None
    assert "encode_missing" in reason


def test_nonempty_mp3_completes(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pem_ok_mp3")
    dest = ctx.path("publish/audio.mp3")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"x" * 1025)
    assert stage_artifact_incompleteness(ctx, "podcast_encode_mp3") is None


def test_heal_refuses_empty_mp3(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "pem_heal_empty")
    dest = ctx.path("publish/audio.mp3")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"")
    try:
        heal_or_raise(ctx, "podcast_encode_mp3")
        raise AssertionError("expected heal_or_raise to refuse empty mp3")
    except RuntimeError as exc:
        assert "encode_missing" in str(exc)
