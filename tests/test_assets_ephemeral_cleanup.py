"""Tests for fresh-launch ephemeral ASSETS cleanup."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.assets_ephemeral_cleanup import cleanup_ephemeral_assets
from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.stage_execution_reuse import apply_stage_reuse, find_reuse_candidates
from run_fixtures import (
    TEST_SOURCE_AUDIO_HASH,
    TEST_SOURCE_AUDIO_HASH_SHORT,
    init_run_meta_for_test,
)


def _cfg(tmp_path: Path) -> dict:
    assets = tmp_path / "ASSETS"
    executions = assets / "executions"
    executions.mkdir(parents=True)
    (assets / ".gui").mkdir(parents=True)
    (assets / "input").mkdir(parents=True)
    (assets / "local_llm" / "venv").mkdir(parents=True)
    return {
        "assets_root": str(assets),
        "executions_root": str(executions),
    }


def test_cleanup_clears_gui_and_keeps_durable(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    assets = Path(cfg["assets_root"])
    gui = assets / ".gui"
    executions = Path(cfg["executions_root"])

    (gui / "application_state.json").write_text("{}", encoding="utf-8")
    (gui / "api_consent.json").write_text("{}", encoding="utf-8")
    (gui / "sessions" / "abc").mkdir(parents=True)
    (gui / "sessions" / "abc" / "bootstrap.log").write_text("hi\n", encoding="utf-8")
    (gui / "server_session.json.lock").write_text("", encoding="utf-8")

    durable = executions / "exec_012_abcdef012345_20260727T120000Z"
    durable.mkdir()
    (durable / "run_meta.json").write_text("{}", encoding="utf-8")
    (durable / ".run.lock").write_text("", encoding="utf-8")
    (durable / ".pending_writes").mkdir()
    nonempty = executions / "exec_013_abcdef012345_20260727T120100Z"
    nonempty.mkdir()
    pending = nonempty / ".pending_writes" / "gaps"
    pending.mkdir(parents=True)
    (pending / "out.json").write_text("{}", encoding="utf-8")

    orphan = executions / "accept_clean"
    orphan.mkdir()
    (orphan / "junk.txt").write_text("x", encoding="utf-8")
    (executions / ".execution_counter").write_text("13", encoding="utf-8")

    wav = assets / "input" / "interview.wav"
    wav.write_bytes(b"RIFF")
    venv_marker = assets / "local_llm" / "venv" / "keep"
    venv_marker.write_text("1", encoding="utf-8")

    report = cleanup_ephemeral_assets(clear_gui_session=True, cfg=cfg)

    assert not (gui / "application_state.json").exists()
    assert not (gui / "api_consent.json").exists()
    assert not (gui / "sessions" / "abc").exists()
    assert report.removed_operator_sessions == 1
    # Executions/ dirs are durable — orphans are never auto-deleted.
    assert report.removed_orphan_execution_dirs == []
    assert orphan.exists()
    assert durable.is_dir()
    assert (durable / "run_meta.json").is_file()
    assert not (durable / ".run.lock").exists()
    assert not (durable / ".pending_writes").exists()
    assert (nonempty / ".pending_writes" / "gaps" / "out.json").is_file()
    assert (executions / ".execution_counter").read_text(encoding="utf-8") == "13"
    assert wav.is_file()
    assert venv_marker.is_file()


def test_preserve_session_keeps_pointer_and_execution_dirs(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    assets = Path(cfg["assets_root"])
    gui = assets / ".gui"
    executions = Path(cfg["executions_root"])

    (gui / "application_state.json").write_text('{"active":{"run_id":"x"}}', encoding="utf-8")
    (gui / "sessions" / "old").mkdir(parents=True)
    (executions / "cv_seg").mkdir()

    report = cleanup_ephemeral_assets(clear_gui_session=False, cfg=cfg)

    assert (gui / "application_state.json").is_file()
    assert report.cleared_gui_session_files == []
    assert not (gui / "sessions" / "old").exists()
    assert (executions / "cv_seg").is_dir()
    assert report.removed_orphan_execution_dirs == []


def test_cleanup_preserves_stage_reuse_lookback_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Product exec_* stage outputs must survive cleanup so every stage can offer reuse."""
    repo = tmp_path / "repo"
    assets = repo / "ASSETS"
    executions = assets / "executions"
    executions.mkdir(parents=True)
    (assets / ".gui" / "sessions" / "old").mkdir(parents=True)
    (executions / "cv_orphan_debris").mkdir()

    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: repo)
    monkeypatch.setattr("interview_mux.assets_ephemeral_cleanup.repo_root", lambda: repo)
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {
            **merged_config(),
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "journey_ui": {
                **(merged_config().get("journey_ui") or {}),
                "stage_reuse_lookback_executions": 5,
                "enable_stage_reuse_offers": True,
            },
        },
    )

    # Five prior runs (lookback window) + current; only the newest prior matches hash.
    for n in range(1, 6):
        rid = f"exec_{n:03d}_{'b' * 12}_20260727T12000{n}Z"
        ctx = RunContext(rid, create=True)
        init_run_meta_for_test(
            ctx,
            source_audio_hash="b" * 64,
            source_audio_hash_short="b" * 12,
        )
        (ctx.run_dir / ".run.lock").write_text("", encoding="utf-8")

    reusable_id = f"exec_006_{TEST_SOURCE_AUDIO_HASH_SHORT}_20260727T120006Z"
    reusable = RunContext(reusable_id, create=True)
    init_run_meta_for_test(
        reusable,
        source_audio_hash=TEST_SOURCE_AUDIO_HASH,
        source_audio_hash_short=TEST_SOURCE_AUDIO_HASH_SHORT,
    )
    reusable.write_json("transcript/full.json", {"segments": [{"text": "hello"}]})
    reusable.write_json("transcript/speakers.json", {"speakers": [{"id": "A"}]})
    reusable.mark_done("transcribe")
    (reusable.run_dir / ".run.lock").write_text("", encoding="utf-8")
    (reusable.run_dir / ".pending_writes").mkdir(exist_ok=True)

    current_id = f"exec_007_{TEST_SOURCE_AUDIO_HASH_SHORT}_20260727T120007Z"
    current = RunContext(current_id, create=True)
    init_run_meta_for_test(
        current,
        source_audio_hash=TEST_SOURCE_AUDIO_HASH,
        source_audio_hash_short=TEST_SOURCE_AUDIO_HASH_SHORT,
    )

    cfg = {
        "assets_root": str(assets),
        "executions_root": str(executions),
    }
    report = cleanup_ephemeral_assets(clear_gui_session=True, cfg=cfg)

    assert report.removed_orphan_execution_dirs == []
    assert (executions / "cv_orphan_debris").is_dir()
    assert reusable.run_dir.is_dir()
    assert (reusable.run_dir / "transcript" / "full.json").is_file()
    assert (reusable.run_dir / ".stage_done" / "transcribe").is_file()
    assert not (reusable.run_dir / ".run.lock").exists()
    assert not (reusable.run_dir / ".pending_writes").exists()

    candidates = find_reuse_candidates(current, "transcribe")
    assert len(candidates) == 1
    assert candidates[0].run_id == reusable_id

    copied = apply_stage_reuse(current, "transcribe", reusable_id)
    assert "transcript/full.json" in copied
    assert current.artifact_exists("transcript/full.json")
    assert current.is_done("transcribe")
