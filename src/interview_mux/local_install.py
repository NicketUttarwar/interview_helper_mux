"""Helpers for local stack repo paths from merged config."""

from __future__ import annotations

from pathlib import Path

from interview_mux.config import merged_config, repo_root


def deepfilter_repo_dir() -> Path:
    cfg = merged_config().get("deepfilter") or {}
    rel = str(cfg.get("repo_dir", "ASSETS/local_deepfilter/DeepFilterNet"))
    path = Path(rel)
    if not path.is_absolute():
        path = repo_root() / path
    return path


def mmaudio_repo_dir() -> Path:
    cfg = merged_config().get("mmaudio") or {}
    rel = str(cfg.get("repo_dir", "ASSETS/local_mmaudio/MMAudio"))
    path = Path(rel)
    if not path.is_absolute():
        path = repo_root() / path
    return path


def deepfilter_stack_dir() -> Path:
    return deepfilter_repo_dir().parent


def mmaudio_stack_dir() -> Path:
    return mmaudio_repo_dir().parent
