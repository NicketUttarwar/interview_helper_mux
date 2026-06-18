"""Runtime configuration from environment and CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "composer-2.5"
DEFAULT_MAX_PROMPT_CHARS = 400_000
DEFAULT_MAX_ATTACHMENT_CHARS = 80_000


@dataclass(frozen=True)
class RunConfig:
    markdown_path: Path
    repo_root: Path
    exec_root: Path
    log_dir: Path
    api_key: str
    model: str
    include_legacy_gc: bool
    skip_done: bool
    dry_run: bool
    resume: bool
    no_expand_attachments: bool
    from_index: int | None
    to_index: int | None
    max_prompt_chars: int
    max_attachment_chars: int


def resolve_model() -> str:
    return os.environ.get("CURSOR_EXECUTE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _read_secrets_env_value(key: str) -> str:
    """Read one key from config/secrets/secrets.env without importing interview_mux."""
    start = Path.cwd().resolve()
    candidates: list[Path] = [start, *start.parents]
    here = Path(__file__).resolve()
    candidates.extend([here, *here.parents])
    seen: set[Path] = set()
    for base in candidates:
        root = base if base.is_dir() else base.parent
        if root in seen:
            continue
        seen.add(root)
        path = root / "config" / "secrets" / "secrets.env"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, val = line.partition("=")
            if k.strip() != key:
                continue
            return val.strip().strip('"').strip("'")
    return ""


def resolve_api_key() -> str:
    env_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if env_key:
        return env_key
    return _read_secrets_env_value("CURSOR_API_KEY")


def resolve_max_prompt_chars() -> int:
    raw = os.environ.get("CURSOR_EXECUTE_MAX_PROMPT_CHARS", "")
    if not raw:
        return DEFAULT_MAX_PROMPT_CHARS
    return int(raw)


def resolve_max_attachment_chars() -> int:
    raw = os.environ.get("CURSOR_EXECUTE_MAX_ATTACHMENT_CHARS", "")
    if not raw:
        return DEFAULT_MAX_ATTACHMENT_CHARS
    return int(raw)
