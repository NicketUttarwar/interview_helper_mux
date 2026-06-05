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


def test_stage_api_providers_transcribe_uses_aws() -> None:
    assert "aws" in stage_api_providers("transcribe")
    assert "openai" in stage_api_providers("speaker_roles")
    assert "elevenlabs" in stage_api_providers("elevenlabs_sfx_flow1")


def test_missing_consents() -> None:
    assert missing_consents("transcribe", {}) == ["aws"]
    assert missing_consents("transcribe", {"aws": True}) == []


def test_providers_for_stages_union() -> None:
    got = providers_for_stages(["transcribe", "speaker_roles"])
    assert got == {"aws", "openai"}


def test_merge_consents() -> None:
    assert merge_consents({"openai": True}, {"openai": False, "aws": True}) == {
        "openai": True,
        "aws": True,
    }


def test_runner_blocks_without_consent(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("interview_mux.gui_api_consent.load_persisted_consents", lambda: {})
    monkeypatch.setattr("interview_mux.web.runner.load_persisted_consents", lambda: {})
    (tmp_path / "ASSETS" / "executions").mkdir(parents=True)
    ctx = RunContext(create=True)
    ctx.init_run_meta("ASSETS/input/test.wav")
    runner = JobRunner()
    result = runner.start(
        ctx.run_id,
        mode="stage",
        stage="transcribe",
        api_consents={},
    )
    assert result.get("ok") is False
    assert result.get("needs_api_consent") is True
    job = runner.get_job(ctx.run_id)
    assert job.get("status") == "needs_operator"


def test_persisted_consent_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ASSETS").mkdir()
    save_persisted_consent("openai", True)
    grants = load_persisted_consents()
    assert grants.get("openai") is True
