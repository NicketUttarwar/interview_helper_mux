"""Resume checkpoint persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class SessionState:
    repo_root: str
    markdown_path: str
    last_completed_index: int
    last_run_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def state_key(repo_root: Path, markdown_path: Path) -> str:
    raw = f"{repo_root.resolve()}|{markdown_path.resolve()}"
    return hashlib.md5(raw.encode()).hexdigest()


def state_path(state_dir: Path, repo_root: Path, markdown_path: Path) -> Path:
    return state_dir / f"{state_key(repo_root, markdown_path)}.json"


def load_state(state_dir: Path, repo_root: Path, markdown_path: Path) -> SessionState | None:
    path = state_path(state_dir, repo_root, markdown_path)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return SessionState(**data)


def save_state(state_dir: Path, state: SessionState) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    key = state_key(Path(state.repo_root), Path(state.markdown_path))
    path = state_dir / f"{key}.json"
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")
