"""Subprocess runners for isolated local AI venvs (MLX, DeepFilterNet, MMAudio)."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RUNTIME_IDS = frozenset({"mlx", "deepfilter", "mmaudio"})


class LocalRuntimeUnavailable(RuntimeError):
    """Raised when a local runtime venv or script is missing."""


def repo_root() -> Path:
    from interview_mux.config import repo_root as _repo_root

    return _repo_root()


def runtime_cfg(runtime_id: str) -> dict[str, Any]:
    from interview_mux.config import merged_config

    if runtime_id not in RUNTIME_IDS:
        raise ValueError(f"Unknown runtime_id: {runtime_id}")
    runtimes = merged_config().get("local_runtimes") or {}
    row = runtimes.get(runtime_id) or {}
    if not isinstance(row, dict):
        return {}
    return row


def runtime_enabled(runtime_id: str) -> bool:
    return bool(runtime_cfg(runtime_id).get("enabled", True))


def resolve_venv_dir(runtime_id: str) -> Path:
    from interview_mux.config import merged_config, repo_root

    cfg = runtime_cfg(runtime_id)
    rel = cfg.get("venv_dir")
    if not rel:
        defaults = {
            "mlx": "ASSETS/local_llm/venv",
            "deepfilter": "ASSETS/local_deepfilter/venv",
            "mmaudio": "ASSETS/local_mmaudio/venv",
        }
        rel = defaults.get(runtime_id, f"ASSETS/local_{runtime_id}/venv")
    path = Path(str(rel))
    if not path.is_absolute():
        path = repo_root() / path
    return path


def resolve_venv_python(runtime_id: str) -> Path:
    if not runtime_enabled(runtime_id):
        raise LocalRuntimeUnavailable(f"Local runtime {runtime_id} is disabled in config")
    py = resolve_venv_dir(runtime_id) / "bin" / "python"
    if not py.is_file():
        raise LocalRuntimeUnavailable(
            f"Missing venv python for {runtime_id}: {py}. Run ./scripts/bootstrap_venv.sh"
        )
    return py


def _default_timeout(runtime_id: str) -> int:
    from interview_mux.config import merged_config

    cfg = merged_config()
    if runtime_id == "mlx":
        block = cfg.get("local_llm") or {}
        return int(block.get("request_timeout_sec", 600))
    if runtime_id == "deepfilter":
        block = cfg.get("deepfilter") or {}
        return int(block.get("request_timeout_sec", 600))
    if runtime_id == "mmaudio":
        block = cfg.get("mmaudio") or {}
        return int(block.get("request_timeout_sec", 900))
    return 600


def run_runtime_script(
    runtime_id: str,
    script_rel: str,
    args: list[str],
    *,
    timeout_sec: int | None = None,
    cwd: Path | None = None,
    env_extra: dict[str, str] | None = None,
    stdin_data: str | None = None,
) -> subprocess.CompletedProcess[str]:
    python = resolve_venv_python(runtime_id)
    script = repo_root() / script_rel
    if not script.is_file():
        raise LocalRuntimeUnavailable(f"Missing runtime script: {script}")
    cmd = [str(python), str(script), *args]
    env = None
    if env_extra:
        import os

        env = os.environ.copy()
        env.update(env_extra)
    timeout = timeout_sec if timeout_sec is not None else _default_timeout(runtime_id)
    try:
        return subprocess.run(
            cmd,
            input=stdin_data,
            cwd=str(cwd or repo_root()),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LocalRuntimeUnavailable(f"Local runtime {runtime_id} timed out after {timeout}s") from exc


def run_runtime_json(
    runtime_id: str,
    script_rel: str,
    payload: dict[str, Any],
    *,
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    python = resolve_venv_python(runtime_id)
    script = repo_root() / script_rel
    if not script.is_file():
        raise LocalRuntimeUnavailable(f"Missing runtime script: {script}")
    timeout = timeout_sec if timeout_sec is not None else _default_timeout(runtime_id)
    try:
        proc = subprocess.run(
            [str(python), str(script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LocalRuntimeUnavailable(f"Local runtime {runtime_id} timed out after {timeout}s") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        raise LocalRuntimeUnavailable(f"Local runtime {runtime_id} failed: {err}")
    raw = (proc.stdout or "").strip()
    if not raw:
        raise LocalRuntimeUnavailable(f"Local runtime {runtime_id} returned empty stdout")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LocalRuntimeUnavailable(f"Local runtime {runtime_id} returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise LocalRuntimeUnavailable(f"Local runtime {runtime_id} JSON must be an object")
    return data


def write_install_manifest(
    stack_dir: Path,
    *,
    runtime_id: str,
    repo_url: str,
    repo_dir: Path,
    venv_dir: Path,
    verified: bool,
) -> Path:
    """Write ASSETS/local_*/install.json after bootstrap verify."""
    from datetime import datetime, timezone

    commit = ""
    git_dir = repo_dir / ".git"
    if git_dir.is_dir():
        try:
            proc = subprocess.run(
                ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if proc.returncode == 0:
                commit = proc.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    payload = {
        "runtime_id": runtime_id,
        "repo_url": repo_url,
        "repo_dir": str(repo_dir),
        "repo_commit": commit,
        "venv_dir": str(venv_dir),
        "verified": verified,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    dest = stack_dir / "install.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest
