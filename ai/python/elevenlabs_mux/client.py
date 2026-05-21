from __future__ import annotations

from pathlib import Path

from mux_secrets import get_config_value, load_repo_config, repo_root_from_here


def get_elevenlabs_client(*, repo_root: Path | None = None):
    """Return an ``ElevenLabs`` client using ``ELEVENLABS_API_KEY`` from ``config/secrets/``."""
    root = (repo_root or repo_root_from_here()).resolve()
    load_repo_config(root)
    try:
        from elevenlabs import ElevenLabs
    except ImportError as e:
        raise ImportError(
            "Install ElevenLabs SDK in the active venv: pip install -r requirements.txt"
        ) from e

    key = get_config_value("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set. Add it to config/secrets/secrets.env "
            "(see config/templates/secrets.env.example)."
        )
    return ElevenLabs(api_key=key)
