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


_IMPORT_PROBE: dict[str, str] = {}


def _require_deepfilter_stack() -> None:
    """Refuse before spawning when the DeepFilterNet stack cannot run.

    A repo on disk is not a runnable stack: without Rust the bootstrap skips
    the native ``df`` build, and the batch script then dies on import with an
    error-level runtime failure. Probe the venv once per process instead, so a
    missing build is a quiet DeepFilterUnavailable that the ffmpeg fallback
    handles.
    """
    import subprocess

    from interview_mux.local_runtime import resolve_venv_dir
    from interview_mux.venv_paths import venv_python

    repo = deepfilter_repo_dir()
    if not repo.is_dir():
        raise DeepFilterUnavailable(f"DeepFilterNet repo missing at {repo}")
    py = venv_python(resolve_venv_dir("deepfilter"))
    key = str(py)
    if key not in _IMPORT_PROBE:
        if not Path(py).exists():
            _IMPORT_PROBE[key] = f"venv python missing at {py}"
        else:
            try:
                r = subprocess.run(
                    [str(py), "-c", "import df.enhance"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                _IMPORT_PROBE[key] = "" if r.returncode == 0 else (r.stderr or r.stdout).strip()[-300:]
            except (OSError, subprocess.TimeoutExpired) as exc:
                _IMPORT_PROBE[key] = f"import probe failed: {exc}"
    if _IMPORT_PROBE[key]:
        raise DeepFilterUnavailable(
            "DeepFilterNet not installed (run ./scripts/bootstrap_venv.sh with Rust): "
            + _IMPORT_PROBE[key]
        )


def enhance_wav(
    input_path: Path,
    output_path: Path,
    *,
    ctx: RunContext | None = None,
) -> None:
    _require_deepfilter_stack()
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
        from interview_mux.heavy_task_policy import reclaim_for_same_class_retry

        err0 = (proc.stderr or proc.stdout or "").strip()
        if reclaim_for_same_class_retry(
            ctx,
            consumer="deepfilter",
            fingerprint=f"enhance:{input_path.name}",
            proc=proc,
            returncode=proc.returncode,
            stderr=err0,
            stage="audio_preclean",
        ):
            proc = run_runtime_script(
                "deepfilter",
                "tools/deepfilter_enhance.py",
                args,
                ctx=ctx,
                stage="audio_preclean",
            )
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

    _require_deepfilter_stack()
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

    from interview_mux.hang_escalation import budget_for_work

    base_to = int(cfg.get("request_timeout_sec") or 600)
    max_to = int(cfg.get("max_request_timeout_sec") or 2400)
    unit = float(cfg.get("timeout_sec_per_file") or 90.0)
    timeout = budget_for_work(
        base_timeout_sec=max(base_to, unit * len(pairs)),
        work_units=float(len(pairs)),
        ref_units=1.0,
        max_timeout_sec=float(max_to),
        min_timeout_sec=float(base_to),
    )
    proc = run_runtime_script(
        "deepfilter",
        "tools/deepfilter_enhance_batch.py",
        [],
        stdin_data=json.dumps(payload),
        timeout_sec=timeout,
        ctx=ctx,
        stage="audio_preclean",
    )
    if proc.returncode != 0:
        from interview_mux.heavy_task_policy import reclaim_for_same_class_retry

        err0 = (proc.stderr or proc.stdout or "").strip()
        if reclaim_for_same_class_retry(
            ctx,
            consumer="deepfilter",
            fingerprint=f"batch:{len(pairs)}",
            proc=proc,
            returncode=proc.returncode,
            stderr=err0,
            stage="audio_preclean",
        ):
            proc = run_runtime_script(
                "deepfilter",
                "tools/deepfilter_enhance_batch.py",
                [],
                stdin_data=json.dumps(payload),
                timeout_sec=timeout,
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
