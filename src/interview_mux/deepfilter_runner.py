"""DeepFilterNet noise reduction via isolated local venv."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.local_install import deepfilter_repo_dir
from interview_mux.local_runtime import LocalRuntimeUnavailable, run_runtime_script
from interview_mux.run_context import RunContext


class DeepFilterUnavailable(LocalRuntimeUnavailable):
    """Raised when DeepFilterNet local stack is missing or enhance fails."""


def deepfilter_cfg() -> dict[str, Any]:
    return merged_config().get("deepfilter") or {}


def enhance_wav(
    input_path: Path,
    output_path: Path,
    *,
    ctx: RunContext | None = None,
) -> None:
    repo = deepfilter_repo_dir()
    if not repo.is_dir():
        raise DeepFilterUnavailable(f"DeepFilterNet repo missing at {repo}")
    cfg = deepfilter_cfg()
    args = [
        "--input-wav",
        str(input_path),
        "--output-wav",
        str(output_path),
        "--model",
        str(cfg.get("model", "DeepFilterNet3")),
    ]
    if cfg.get("postfilter"):
        args.append("--postfilter")
    if cfg.get("compensate_delay"):
        args.append("--compensate-delay")

    proc = run_runtime_script("deepfilter", "tools/deepfilter_enhance.py", args)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        raise DeepFilterUnavailable(f"DeepFilterNet enhance failed: {err}")

    if ctx:
        ctx.log(
            "DeepFilterNet enhanced audio",
            level="debug",
            stage="audio_preclean",
            detail={
                "provider": "deepfilternet",
                "input": str(input_path),
                "output": str(output_path),
                "model": cfg.get("model"),
            },
        )
