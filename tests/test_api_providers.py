"""API provider registry and consent helpers."""

from __future__ import annotations

from interview_mux.api_providers import (
    missing_consents,
    providers_for_stages,
    stage_api_providers,
)
from interview_mux.gui_api_consent import load_persisted_consents, merge_consents, save_persisted_consent
from interview_mux.web.runner import JobRunner
from interview_mux.run_context import RunContext


def test_stage_api_providers_transcribe_uses_local() -> None:
    assert "local" in stage_api_providers("transcribe")
    assert "openai" in stage_api_providers("speaker_roles")
    assert stage_api_providers("mmaudio_sfx") == ()
    assert stage_api_providers("master_transcript_build") == ()


def test_missing_consents() -> None:
    assert missing_consents("transcribe", {}) == ["local"]
    assert missing_consents("transcribe", {"local": True}) == []


def test_providers_for_stages_union() -> None:
    got = providers_for_stages(["transcribe", "speaker_roles"])
    assert got == {"local", "openai"}


def test_merge_consents() -> None:
    assert merge_consents({"openai": True}, {"openai": False, "aws": True}) == {
        "openai": True,
        "aws": True,
    }


def test_runner_blocks_without_consent(tmp_path, monkeypatch) -> None:
    import shutil

    from interview_mux.config import merged_config, repo_root as real_repo_root
    from run_fixtures import ensure_test_wav, patch_merged_config, plant_seed_complete_through

    from run_fixtures import copy_shipped_config
    copy_shipped_config(tmp_path)
    base_cfg = merged_config()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    monkeypatch.setattr("interview_mux.config.repo_root", lambda: tmp_path)
    cfg = {
        **base_cfg,
        "assets_root": "ASSETS",
        "executions_root": str(tmp_path / "ASSETS" / "executions"),
    }
    patch_merged_config(monkeypatch, cfg)
    monkeypatch.setattr("interview_mux.gui_api_consent.load_persisted_consents", lambda: {})
    monkeypatch.setattr("interview_mux.web.runner.load_persisted_consents", lambda: {})
    (tmp_path / "ASSETS" / "executions").mkdir(parents=True)
    ensure_test_wav(tmp_path, "ASSETS/input/test.wav")
    ctx = RunContext(create=True)
    ctx.init_run_meta("ASSETS/input/test.wav")
    plant_seed_complete_through(ctx, "audio_preclean")
    runner = JobRunner()
    result = runner.start(
        ctx.run_id,
        mode="stage",
        stage="transcribe",
        api_consents={},
    )
    assert result.get("ok") is False
    assert result.get("needs_api_consent") is True or result.get("pinned_to") in {
        "audio_preclean",
        "ingest",
        "audio_probe_build",
    }
    err = str(result.get("error") or result.get("reason") or "")
    assert "local" in err or "audio_preclean" in err or "ingest" in err or "consent" in err.lower()


def test_persisted_consent_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ASSETS").mkdir()
    save_persisted_consent("openai", True)
    grants = load_persisted_consents()
    assert grants.get("openai") is True
