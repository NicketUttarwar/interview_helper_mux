from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interview_mux.run_context import RunContext
from interview_mux.web.server import _assert_artifact_path, create_app
from interview_mux.web.stages import STAGE_BY_ID
from interview_mux.write_staging import expand_audio_output_paths
from run_fixtures import patch_merged_config

_MIN_WAV = b"RIFF----WAVEfmt "


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    executions = root / "ASSETS" / "executions"
    executions.mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    patch_merged_config(
        monkeypatch,
        {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
            "journey_ui": {"require_write_approval_per_stage": False},
        },
    )
    rid = "exec_001_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_serve_speaker_sample_clip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    clip = ctx.run_dir / "understanding" / "speaker_samples" / "spk_0.wav"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(_MIN_WAV)

    client = TestClient(create_app())
    res = client.get(
        f"/api/runs/{ctx.run_id}/audio",
        params={"path": "understanding/speaker_samples/spk_0.wav"},
    )
    assert res.status_code == 200
    assert res.headers.get("content-type", "").startswith("audio/")


def test_serve_audio_rejects_non_allowlisted_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    rogue = ctx.run_dir / "private" / "evil.wav"
    rogue.parent.mkdir(parents=True)
    rogue.write_bytes(_MIN_WAV)

    client = TestClient(create_app(), raise_server_exceptions=False)
    res = client.get(
        f"/api/runs/{ctx.run_id}/audio",
        params={"path": "private/evil.wav"},
    )
    assert res.status_code == 400


def test_assert_artifact_path_allows_speaker_sample_glob() -> None:
    _assert_artifact_path("understanding/speaker_samples/spk_0.wav")


def test_audio_outputs_present_expands_glob(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    clip = ctx.run_dir / "transcript" / "review_clips" / "chunk_001.wav"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(_MIN_WAV)

    expanded = expand_audio_output_paths(ctx, STAGE_BY_ID["transcript_review_build"].audio_outputs)
    assert "transcript/review_clips/chunk_001.wav" in expanded


def test_serve_audio_uses_staged_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    staged = (
        ctx.run_dir
        / ".pending_writes"
        / "ingest"
        / "ingest"
        / "normalized.wav"
    )
    staged.parent.mkdir(parents=True)
    staged.write_bytes(_MIN_WAV)

    client = TestClient(create_app())
    res = client.get(
        f"/api/runs/{ctx.run_id}/audio",
        params={"path": "ingest/normalized.wav"},
    )
    assert res.status_code == 200
    assert res.content == _MIN_WAV
