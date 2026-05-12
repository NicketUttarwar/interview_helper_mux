from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mux_secrets import get_config_value, load_repo_config, repo_root_from_here


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str
    model: str  # Chat Completions / JSON ranking (``OPENAI_MODEL`` in ``config/secrets/``).
    speech_model: str  # Reserved for transcription adapters (``OPENAI_SPEECH_MODEL``).


def load_openai_settings(*, repo_root: Path | None = None) -> OpenAISettings:
    """Load OpenAI settings after applying repo ``config/secrets/*.env`` files."""
    root = (repo_root or repo_root_from_here()).resolve()
    load_repo_config(root)

    key = get_config_value("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to config/secrets/secrets.env "
            "(copy from config/templates/secrets.env.example)."
        )
    model = get_config_value("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
    speech = get_config_value("OPENAI_SPEECH_MODEL", "whisper-1") or "whisper-1"
    return OpenAISettings(api_key=key, model=model, speech_model=speech)
