from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    """Repository root (works for src checkout and non-editable pip install)."""
    env = os.environ.get("INTERVIEW_MUX_ROOT")
    if env:
        return Path(env).resolve()
    start = Path.cwd().resolve()
    for parent in [start, *start.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "config" / "app.defaults.json").is_file():
            return parent
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "config" / "app.defaults.json").is_file():
            return parent
    raise RuntimeError(
        "Cannot find repo root (pyproject.toml + config/app.defaults.json). "
        "Run from the project directory or set INTERVIEW_MUX_ROOT."
    )


def load_defaults() -> dict[str, Any]:
    path = repo_root() / "config" / "app.defaults.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_secrets() -> dict[str, str]:
    """Load secrets.env without polluting os.environ."""
    path = repo_root() / "config" / "secrets" / "secrets.env"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def merged_config() -> dict[str, Any]:
    cfg = load_defaults()
    secrets = load_secrets()
    if secrets.get("INPUT_AUDIO_PATH"):
        cfg["input_audio_path"] = secrets["INPUT_AUDIO_PATH"]
    cfg["secrets"] = secrets
    return cfg


def get_model(stage_key: str) -> str:
    from interview_mux.model_registry import resolve_model

    cfg = merged_config()
    models = cfg.get("models") or {}
    if isinstance(models.get(stage_key), str):
        return str(models[stage_key])
    resolved = resolve_model(stage_key, "primary")
    return resolved.model_id or secrets_model_fallback(cfg, stage_key)


def secrets_model_fallback(cfg: dict[str, Any], stage_key: str) -> str:
    secrets = cfg.get("secrets") or {}
    return secrets.get("OPENAI_MODEL", "gpt-4o-mini")


def require_secret(key: str) -> str:
    val = (merged_config().get("secrets") or {}).get(key, "")
    if not val:
        raise RuntimeError(f"Missing required secret: {key} in config/secrets/secrets.env")
    return val
