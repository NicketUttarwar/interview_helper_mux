"""Provider secret preflight before pipeline execute."""

from __future__ import annotations

from interview_mux.api_providers import missing_secrets


def test_missing_secrets_openai(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {"secrets": {"OPENAI_API_KEY": "", "AWS_S3_BUCKET": "b"}},
    )
    assert "openai" in missing_secrets(["speaker_roles"])


def test_missing_secrets_transcribe_uses_local_not_aws(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {"secrets": {"OPENAI_API_KEY": "", "AWS_S3_BUCKET": ""}},
    )
    assert "aws" not in missing_secrets(["transcribe"])
    assert missing_secrets(["transcribe"]) == []
