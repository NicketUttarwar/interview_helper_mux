"""Git snapshot and file change detection."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitSnapshot:
    head: str
    status_porcelain: str


@dataclass(frozen=True)
class FileChangeSummary:
    command_index: int
    command_total: int
    command_id: str
    command_title: str
    total: int
    created: int
    modified: int
    deleted: int
    renamed: int
    paths: list[tuple[str, str]]  # status letter(s), path


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {err}")
    return result.stdout


def validate_git_repo(repo_root: Path) -> None:
    _run_git(repo_root, "rev-parse", "--is-inside-work-tree")


def resolve_repo_root(markdown_path: Path, override: Path | None) -> Path:
    if override is not None:
        root = override.resolve()
        validate_git_repo(root)
        return root
    # Try git toplevel from markdown's directory
    md_dir = markdown_path.resolve().parent
    result = subprocess.run(
        ["git", "-C", str(md_dir), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())
    # Fallback: parent of CURSOR_EXECUTE
    exec_root = Path(__file__).resolve().parents[2]
    candidate = exec_root.parent
    validate_git_repo(candidate)
    return candidate


def take_snapshot(repo_root: Path) -> GitSnapshot:
    head_result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    head = head_result.stdout.strip() if head_result.returncode == 0 else ""
    status = _run_git(repo_root, "status", "--porcelain")
    return GitSnapshot(head=head, status_porcelain=status)


def _parse_status_line(line: str) -> tuple[str, str] | None:
    if len(line) < 4:
        return None
    xy = line[:2]
    path = line[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    if path.startswith("CURSOR_EXECUTE/"):
        return None
    status = xy.strip() or "?"
    return status, path


def diff_since_snapshot(
    repo_root: Path,
    before: GitSnapshot,
    *,
    command_index: int,
    command_total: int,
    command_id: str,
    command_title: str,
) -> FileChangeSummary:
    current_status = _run_git(repo_root, "status", "--porcelain")
    current_lines = [ln for ln in current_status.splitlines() if ln.strip()]

    paths: list[tuple[str, str]] = []
    created = modified = deleted = renamed = 0

    for line in current_lines:
        parsed = _parse_status_line(line)
        if not parsed:
            continue
        status, path = parsed
        paths.append((status, path))
        if status in ("??", "A") or "?" in status:
            created += 1
        elif "D" in status:
            deleted += 1
        elif "R" in status:
            renamed += 1
        else:
            modified += 1

    unique_paths = sorted(set(paths), key=lambda x: x[1])

    return FileChangeSummary(
        command_index=command_index,
        command_total=command_total,
        command_id=command_id,
        command_title=command_title,
        total=len(unique_paths),
        created=created,
        modified=modified,
        deleted=deleted,
        renamed=renamed,
        paths=unique_paths,
    )
