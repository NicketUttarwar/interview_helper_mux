"""Resolve run targets: CLI override → secrets.env → config/app.defaults.json."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mux_secrets import get_config_value, load_repo_config
from mux_store.repo_config import _repo_relative_path, default_assets_path, read_json_config

# secrets.env keys (user-provided; see config/templates/secrets.env.example)
_SECRET_INTERVIEW_ID = "INTERVIEW_ID"
_SECRET_INPUT_AUDIO = "INPUT_AUDIO_PATH"
_SECRET_S3_URI = "AWS_S3_URI"
_SECRET_S3_BUCKET = "AWS_S3_BUCKET"
_SECRET_S3_KEY = "AWS_S3_INPUT_KEY"

# app.defaults.json keys (committed paths / defaults)
_DEFAULT_INTERVIEW_ID = "interview_id"
_DEFAULT_INPUT_AUDIO = "input_audio_path"


def _app_defaults(repo_root: Path) -> dict[str, Any]:
    data = read_json_config(repo_root, "app.defaults.json")
    if not isinstance(data, dict):
        raise ValueError("app.defaults.json must be a JSON object")
    return data


def _first_non_empty(*values: str | None) -> str:
    for v in values:
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def resolve_interview_id(repo_root: Path, *, cli: str | None = None) -> str:
    """Interview id: ``--interview-id`` → ``INTERVIEW_ID`` → ``interview_id`` in app.defaults."""
    if cli and cli.strip():
        return cli.strip()
    load_repo_config(repo_root)
    from_secrets = get_config_value(_SECRET_INTERVIEW_ID)
    if from_secrets:
        return from_secrets
    raw = _app_defaults(repo_root).get(_DEFAULT_INTERVIEW_ID)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    raise ValueError(
        "interview id not set. Set INTERVIEW_ID in config/secrets/secrets.env, "
        "interview_id in config/app.defaults.json, or pass --interview-id."
    )


def resolve_input_audio_path(repo_root: Path, *, cli: str | None = None) -> Path:
    """Source WAV for ingest: ``--input`` → ``INPUT_AUDIO_PATH`` → ``input_audio_path`` in app.defaults."""
    raw = _first_non_empty(cli, _secret_path(repo_root, _SECRET_INPUT_AUDIO), _default_path(repo_root, _DEFAULT_INPUT_AUDIO))
    if not raw:
        raise ValueError(
            "input audio not set. Set INPUT_AUDIO_PATH in config/secrets/secrets.env, "
            "input_audio_path in config/app.defaults.json, or pass --input."
        )
    path = _repo_relative_path(repo_root, raw, field="input_audio_path")
    if not path.is_file():
        raise FileNotFoundError(
            f"Input audio not found: {path}. "
            "Place your interview WAV at that path or update INPUT_AUDIO_PATH / input_audio_path."
        )
    return path


def resolve_s3_uri(repo_root: Path, *, cli: str | None = None) -> str:
    """
    S3 media URI for AWS Transcribe: ``--s3-uri`` → ``AWS_S3_URI`` → ``s3://{AWS_S3_BUCKET}/{AWS_S3_INPUT_KEY}``.
    """
    if cli and cli.strip():
        return cli.strip()
    load_repo_config(repo_root)
    direct = get_config_value(_SECRET_S3_URI)
    if direct:
        return direct
    bucket = get_config_value(_SECRET_S3_BUCKET)
    key = get_config_value(_SECRET_S3_KEY)
    if bucket and key:
        return f"s3://{bucket.strip().strip('/')}/{key.strip().lstrip('/')}"
    raise ValueError(
        "AWS S3 URI not set. Set AWS_S3_URI or AWS_S3_BUCKET + AWS_S3_INPUT_KEY in "
        "config/secrets/secrets.env, or pass --s3-uri."
    )


def default_master_wav(repo_root: Path, interview_id: str) -> Path:
    """Preset E default input: ``<assets_root>/<interview_id>/master/highlight_master.wav``."""
    return default_assets_path(repo_root) / interview_id / "master" / "highlight_master.wav"


def _secret_path(repo_root: Path, key: str) -> str:
    load_repo_config(repo_root)
    return get_config_value(key)


def _default_path(repo_root: Path, key: str) -> str:
    raw = _app_defaults(repo_root).get(key)
    return raw.strip() if isinstance(raw, str) else ""
