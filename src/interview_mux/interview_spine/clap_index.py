from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from interview_mux.interview_spine.paths import SPINE_EMBEDDINGS_REL


def build_clap_index(
    ctx,
    windows: list[dict[str, Any]],
    *,
    wav_path: Path,
    model_id: str,
    timeout_sec: int = 120,
) -> tuple[bool, str | None, int | None]:
    """Embed each window; write embeddings.npz. Returns (enabled, sidecar_rel, dim).

    Loads the CLAP model once via a batched local_mmaudio script invocation.
    Falls back to per-window calls if the batch response is unavailable.
    """
    from interview_mux.local_runtime import LocalRuntimeUnavailable, repo_root, resolve_venv_python, run_runtime_script

    if not windows:
        return False, None, None

    vectors: list[list[float]] = []
    # Batch path: direct subprocess so a failure does not abort the stage via
    # active_run_context + run_runtime_script raising, and so vector JSON is not
    # fan-out logged line-by-line into gui_log.
    batch_timeout = max(int(timeout_sec), 120 + 15 * len(windows))
    batch_payload = json.dumps(
        {
            "wav_path": str(wav_path),
            "model_id": model_id,
            "windows": [
                {"start_ms": int(win["start_ms"]), "end_ms": int(win["end_ms"])}
                for win in windows
            ],
        }
    )
    try:
        python = resolve_venv_python("mmaudio")
        script = repo_root() / "tools" / "clap_embed_window.py"
        ctx.log(
            f"CLAP batch embed: {len(windows)} window(s) (single model load)…",
            level="action",
            stage="interview_spine_build",
        )
        proc = subprocess.run(
            [str(python), str(script)],
            input=batch_payload,
            capture_output=True,
            text=True,
            timeout=batch_timeout,
            cwd=str(repo_root()),
            check=False,
        )
        if proc.returncode == 0:
            result = json.loads(proc.stdout or "{}")
            if result.get("available") and isinstance(result.get("vectors"), list):
                raw_vecs = result["vectors"]
                if len(raw_vecs) == len(windows):
                    for i, vec in enumerate(raw_vecs):
                        if not isinstance(vec, list) or not vec:
                            vectors = []
                            break
                        windows[i]["embedding_ref"] = i
                        vectors.append([float(x) for x in vec])
                    if vectors:
                        ctx.log(
                            f"CLAP batch embed complete ({len(vectors)} vectors).",
                            level="success",
                            stage="interview_spine_build",
                        )
        else:
            ctx.log(
                f"CLAP batch embed failed (exit {proc.returncode}); falling back.",
                level="warning",
                stage="interview_spine_build",
                detail={"stderr": (proc.stderr or "")[:300]},
            )
    except (LocalRuntimeUnavailable, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        ctx.log(
            f"CLAP batch embed unavailable ({exc}); falling back to per-window.",
            level="warning",
            stage="interview_spine_build",
        )
        vectors = []

    # Legacy fallback: one subprocess per window (slow; reloads weights each time).
    if len(vectors) != len(windows):
        vectors = []
        for i, win in enumerate(windows):
            payload = json.dumps(
                {
                    "wav_path": str(wav_path),
                    "start_ms": int(win["start_ms"]),
                    "end_ms": int(win["end_ms"]),
                    "model_id": model_id,
                }
            )
            try:
                proc = run_runtime_script(
                    "mmaudio",
                    "tools/clap_embed_window.py",
                    [],
                    stdin_data=payload,
                    timeout_sec=timeout_sec,
                )
            except LocalRuntimeUnavailable:
                return False, None, None
            if proc.returncode != 0:
                return False, None, None
            try:
                result = json.loads(proc.stdout or "{}")
            except json.JSONDecodeError:
                return False, None, None
            if not result.get("available"):
                return False, None, None
            vec = result.get("vector")
            if not isinstance(vec, list) or not vec:
                return False, None, None
            win["embedding_ref"] = i
            vectors.append([float(x) for x in vec])

    if not vectors:
        return False, None, None

    sidecar = ctx.path(*SPINE_EMBEDDINGS_REL.split("/"))
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    window_ids = np.array([w["window_id"] for w in windows], dtype=object)
    matrix = np.array(vectors, dtype=np.float16)
    np.savez_compressed(sidecar, embeddings=matrix, window_ids=window_ids)
    return True, SPINE_EMBEDDINGS_REL, int(matrix.shape[1])
