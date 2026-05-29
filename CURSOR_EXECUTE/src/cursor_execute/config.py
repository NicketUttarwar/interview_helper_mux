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


def resolve_api_key() -> str:
    return os.environ.get("CURSOR_API_KEY", "").strip()


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
