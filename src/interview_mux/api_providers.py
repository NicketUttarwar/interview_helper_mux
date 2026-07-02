"""External API provider registry for GUI session consent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ApiProviderInfo:
    id: str
    label: str
    description: str
    cost_hint: str


PROVIDERS: dict[str, ApiProviderInfo] = {
    "openai": ApiProviderInfo(
        id="openai",
        label="OpenAI (LLM)",
        description="Analysis, selection, transitions, and show-description stages use the OpenAI API.",
        cost_hint="Billed per token by your OpenAI account.",
    ),
    "aws": ApiProviderInfo(
        id="aws",
        label="AWS Transcribe",
        description="Speech-to-text with speaker diarization via the AWS CLI.",
        cost_hint="Billed by AWS for audio minutes transcribed.",
    ),
}


def list_providers() -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "label": p.label,
            "description": p.description,
            "cost_hint": p.cost_hint,
        }
        for p in PROVIDERS.values()
    ]


def all_provider_grants() -> dict[str, bool]:
    """All external APIs are auto-consented for GUI sessions (no operator prompt)."""
    return {pid: True for pid in PROVIDERS}


def stage_api_providers(stage_id: str) -> tuple[str, ...]:
    from interview_mux.web.stages import STAGE_API_PROVIDERS

    return STAGE_API_PROVIDERS.get(stage_id, ())


_SECRET_KEYS_BY_PROVIDER: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "aws": ("AWS_S3_BUCKET",),
}


def missing_secrets(stage_ids: list[str]) -> list[str]:
    """Return provider ids whose required secrets.env keys are empty."""
    from interview_mux.config import merged_config

    secrets = merged_config().get("secrets") or {}
    missing: list[str] = []
    for pid in providers_for_stages(stage_ids):
        for key in _SECRET_KEYS_BY_PROVIDER.get(pid, ()):
            if not str(secrets.get(key) or "").strip():
                if pid not in missing:
                    missing.append(pid)
                break
    return missing


def missing_consents(stage_id: str, consents: dict[str, bool]) -> list[str]:
    missing: list[str] = []
    for pid in stage_api_providers(stage_id):
        if not consents.get(pid):
            missing.append(pid)
    return missing


def providers_for_stages(stage_ids: list[str]) -> set[str]:
    out: set[str] = set()
    for sid in stage_ids:
        out.update(stage_api_providers(sid))
    return out
