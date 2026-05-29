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
    "elevenlabs": ApiProviderInfo(
        id="elevenlabs",
        label="ElevenLabs",
        description="Optional source pre-clean and sound-effect generation.",
        cost_hint="Billed per generation by your ElevenLabs account.",
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


def stage_api_providers(stage_id: str) -> tuple[str, ...]:
    from interview_mux.web.stages import STAGE_API_PROVIDERS

    return STAGE_API_PROVIDERS.get(stage_id, ())


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
