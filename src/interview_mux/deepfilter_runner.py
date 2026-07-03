"""DeepFilterNet noise reduction via isolated local venv."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.local_install import deepfilter_repo_dir
from interview_mux.local_runtime import LocalRuntimeUnavailable, run_runtime_script
from interview_mux.run_context import RunContext

_PROGRESS_RE = re.compile(r"^PROGRESS (\d+)/(\d+)\s*$")


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

    if ctx:
        from interview_mux.operator_trace import log_api_call

        log_api_call(
            "DeepFilterNet",
            f"enhance ({cfg.get('model', 'DeepFilterNet3')})",
            ctx=ctx,
            stage="audio_preclean",
            detail={"input": str(input_path), "output": str(output_path)},
        )

    proc = run_runtime_script("deepfilter", "tools/deepfilter_enhance.py", args, ctx=ctx, stage="audio_preclean")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        raise DeepFilterUnavailable(f"DeepFilterNet enhance failed: {err}")

    if ctx:
        ctx.log(
            "DeepFilterNet enhanced audio",
            level="success",
            stage="audio_preclean",
            detail={
                "provider": "deepfilternet",
                "input": str(input_path),
                "output": str(output_path),
                "model": cfg.get("model"),
                "journey_kind": "execute",
            },
        )


def enhance_wav_batch(
    pairs: list[tuple[Path, Path]],
    *,
    ctx: RunContext | None = None,
    progress: Any | None = None,
) -> None:
    """Enhance many WAV files in one subprocess with a single model load."""
    if not pairs:
        return
    if len(pairs) == 1:
        enhance_wav(pairs[0][0], pairs[0][1], ctx=ctx)
        return

    repo = deepfilter_repo_dir()
    if not repo.is_dir():
        raise DeepFilterUnavailable(f"DeepFilterNet repo missing at {repo}")
    cfg = deepfilter_cfg()
    payload: dict[str, Any] = {
        "model": cfg.get("model", "DeepFilterNet3"),
        "postfilter": bool(cfg.get("postfilter")),
        "compensate_delay": bool(cfg.get("compensate_delay", True)),
        "jobs": [{"input": str(src), "output": str(dest)} for src, dest in pairs],
    }

    if ctx:
        from interview_mux.operator_trace import log_api_call

        log_api_call(
            "DeepFilterNet",
            f"batch enhance ({cfg.get('model', 'DeepFilterNet3')}, {len(pairs)} files)",
            ctx=ctx,
            stage="audio_preclean",
            detail={"count": len(pairs)},
        )

    proc = run_runtime_script(
        "deepfilter",
        "tools/deepfilter_enhance_batch.py",
        [],
        stdin_data=json.dumps(payload),
        ctx=ctx,
        stage="audio_preclean",
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        raise DeepFilterUnavailable(f"DeepFilterNet batch enhance failed: {err}")

    if progress is not None and ctx is not None:
        from interview_mux.operator_subprocess import touch_job_progress

        for line in (proc.stderr or "").splitlines():
            match = _PROGRESS_RE.match(line.strip())
            if not match:
                continue
            step_index = int(match.group(1))
            step_total = int(match.group(2))
            touch_job_progress(
                ctx,
                f"Enhancing chunk {step_index}/{step_total} (DeepFilterNet)…",
                phase="deepfilter",
                step_index=step_index,
                step_total=step_total,
            )

    if ctx:
        ctx.log(
            f"DeepFilterNet batch enhanced {len(pairs)} file(s)",
            level="success",
            stage="audio_preclean",
            detail={
                "provider": "deepfilternet",
                "count": len(pairs),
                "model": cfg.get("model"),
                "journey_kind": "execute",
            },
        )
