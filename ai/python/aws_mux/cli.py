from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mux_secrets import get_config_value, load_repo_config, repo_root_from_here

_AWS_BIN_CANDIDATES = (
    "aws",
    "/opt/homebrew/bin/aws",
    "/usr/local/bin/aws",
)


def _resolve_aws_bin() -> str:
    for candidate in _AWS_BIN_CANDIDATES:
        if candidate == "aws":
            found = shutil.which("aws")
            if found:
                return found
            continue
        if Path(candidate).is_file():
            return candidate
    raise FileNotFoundError(
        "AWS CLI not found on PATH. Install AWS CLI v2 (e.g. brew install awscli) "
        "and ensure `aws --version` works in your shell."
    )


def _aws_env(repo_root: Path) -> dict[str, str]:
    """
    Subprocess env for AWS CLI: inherit PATH/HOME (and existing AWS_* from the shell),
    then overlay non-empty values from ``config/secrets/secrets.env``.
    Does not mutate ``os.environ`` at import time.
    """
    load_repo_config(repo_root)
    env = os.environ.copy()
    profile = get_config_value("AWS_PROFILE")
    if profile:
        env["AWS_PROFILE"] = profile
    for key in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_DEFAULT_REGION",
        "AWS_REGION",
    ):
        val = get_config_value(key)
        if val:
            env[key] = val
    if not env.get("AWS_DEFAULT_REGION") and not env.get("AWS_REGION"):
        env["AWS_DEFAULT_REGION"] = "us-east-1"
    return env


def run_aws_cli(
    argv: list[str],
    *,
    repo_root: Path | None = None,
    timeout_sec: float | None = 300,
) -> dict[str, Any] | list[Any] | str | None:
    """
    Run ``aws`` with JSON output. ``argv`` is everything after ``aws`` (e.g. ``['sts', 'get-caller-identity']``).
    """
    root = (repo_root or repo_root_from_here()).resolve()
    cmd = [_resolve_aws_bin(), *argv, "--output", "json"]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=_aws_env(root),
        timeout=timeout_sec,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"aws {' '.join(argv)} failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
    out = (proc.stdout or "").strip()
    if not out:
        return None
    return json.loads(out)


def sts_get_caller_identity(*, repo_root: Path | None = None) -> dict[str, Any]:
    data = run_aws_cli(["sts", "get-caller-identity"], repo_root=repo_root)
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected STS response")
    return data
