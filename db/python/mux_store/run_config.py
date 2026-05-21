"""Resolve run targets: CLI override → secrets.env → config/app.defaults.json."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mux_secrets import get_config_value, load_repo_config
from mux_store.repo_config import _repo_relative_path, default_assets_path, read_json_config

# secrets.env keys (user-provided; see config/templates/secrets.env.example)
_SECRET_INPUT_AUDIO = "INPUT_AUDIO_PATH"
_SECRET_S3_URI = "AWS_S3_URI"
_SECRET_S3_BUCKET = "AWS_S3_BUCKET"
_SECRET_S3_KEY = "AWS_S3_INPUT_KEY"

# app.defaults.json keys (committed paths / defaults)
_DEFAULT_INPUT_AUDIO = "input_audio_path"

_SESSION_PREFIX = "run_"
_ACTIVE_SESSION_KV = "pipeline.active_session_id"
_SESSION_DIR_RE = re.compile(r"^run_(\d+)$")


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


def _session_suffix(name: str) -> int | None:
    m = _SESSION_DIR_RE.match(name.strip())
    return int(m.group(1)) if m else None


def _max_session_suffix(repo_root: Path, conn: Any | None) -> int:
    max_n = 0
    assets = default_assets_path(repo_root)
    if assets.is_dir():
        for p in assets.iterdir():
            if p.is_dir():
                n = _session_suffix(p.name)
                if n is not None:
                    max_n = max(max_n, n)
    if conn is not None:
        try:
            cur = conn.execute("SELECT id FROM interview")
            for row in cur:
                n = _session_suffix(str(row[0]))
                if n is not None:
                    max_n = max(max_n, n)
        except Exception:
            pass
    return max_n


def allocate_session_id(repo_root: Path, conn: Any) -> str:
    """Allocate the next sequential session id (``run_001``, ``run_002``, …)."""
    n = _max_session_suffix(repo_root, conn) + 1
    return f"{_SESSION_PREFIX}{n:03d}"


def set_active_session_id(conn: Any, session_id: str) -> None:
    from mux_store.runtime import execution_kv_set

    execution_kv_set(conn, _ACTIVE_SESSION_KV, session_id.strip())


def resolve_active_session_id(repo_root: Path, conn: Any) -> str:
    """
    Session for the current pipeline chain: ``execution_kv`` active id, else the
    newest ``ASSETS/run_NNN`` tree that has ``ingest/normalized.wav``.
    """
    from mux_store.runtime import execution_kv_get

    val = execution_kv_get(conn, _ACTIVE_SESSION_KV)
    if isinstance(val, str) and val.strip():
        return val.strip()

    assets = default_assets_path(repo_root)
    best_suffix = -1
    best_id: str | None = None
    if assets.is_dir():
        for p in assets.iterdir():
            if not p.is_dir():
                continue
            suffix = _session_suffix(p.name)
            if suffix is None:
                continue
            if (p / "ingest" / "normalized.wav").is_file() and suffix > best_suffix:
                best_suffix = suffix
                best_id = p.name
    if best_id:
        return best_id
    raise ValueError(
        "No active pipeline session. Run tools/run_ingest.py first to start a new execution."
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


def default_master_wav(repo_root: Path, session_id: str) -> Path:
    """Polished master default: ``<assets_root>/<session_id>/processed/room_polish_master.wav``."""
    return default_assets_path(repo_root) / session_id / "processed" / "room_polish_master.wav"


def session_ingest_wav(repo_root: Path, session_id: str) -> Path:
    return default_assets_path(repo_root) / session_id / "ingest" / "normalized.wav"


def _secret_path(repo_root: Path, key: str) -> str:
    load_repo_config(repo_root)
    return get_config_value(key)


def _default_path(repo_root: Path, key: str) -> str:
    raw = _app_defaults(repo_root).get(key)
    return raw.strip() if isinstance(raw, str) else ""
