from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from interview_mux.interview_spine.paths import SPINE_EMBEDDINGS_REL

# Per-window subprocess reloads CLAP weights + GPU cooldown (~13s each). Only
# acceptable for tiny clips / unit tests — never for a full interview (~700 windows).
_PER_WINDOW_FALLBACK_MAX = 8
_BATCH_VECTORS_REL = "understanding/interview_spine/clap_batch_vectors.json"


def _as_float_vectors(raw_vecs: Any, expected: int) -> list[list[float]]:
    if not isinstance(raw_vecs, list) or len(raw_vecs) != expected:
        return []
    out: list[list[float]] = []
    for vec in raw_vecs:
        if not isinstance(vec, list) or not vec:
            return []
        out.append([float(x) for x in vec])
    return out


def _load_vectors_from_receipt(
    result: dict[str, Any],
    *,
    expected: int,
) -> list[list[float]]:
    """Accept in-stdout vectors or a sidecar file written by clap_embed_window."""
    file_vecs = _as_float_vectors(result.get("vectors"), expected)
    if file_vecs:
        return file_vecs
    out_raw = result.get("output_path")
    if not out_raw:
        return []
    path = Path(str(out_raw))
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    return _as_float_vectors(payload.get("vectors"), expected)


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
    Per-window fallback is capped — a silent 694-call serial reload is a hang.
    """
    from interview_mux.local_runtime import (
        LocalRuntimeUnavailable,
        parse_runtime_json_stdout,
        repo_root,
        resolve_venv_python,
        run_runtime_script,
    )

    if not windows:
        return False, None, None

    vectors: list[list[float]] = []
    batch_timeout = max(int(timeout_sec), 120 + 15 * len(windows))
    out_path = ctx.path(*_BATCH_VECTORS_REL.split("/"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    batch_payload = json.dumps(
        {
            "wav_path": str(wav_path),
            "model_id": model_id,
            "output_path": str(out_path),
            "windows": [
                {
                    "start_ms": int(win["start_ms"]),
                    "end_ms": max(int(win["end_ms"]), int(win["start_ms"]) + 50),
                }
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
        parsed = parse_runtime_json_stdout(proc.stdout or "") or parse_runtime_json_stdout(
            proc.stderr or ""
        )
        if proc.returncode == 0 and isinstance(parsed, dict) and parsed.get("available"):
            vectors = _load_vectors_from_receipt(parsed, expected=len(windows))
            if not vectors and out_path.is_file():
                try:
                    file_payload = json.loads(out_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    file_payload = {}
                if isinstance(file_payload, dict):
                    vectors = _as_float_vectors(file_payload.get("vectors"), len(windows))
            if vectors:
                for i, _vec in enumerate(vectors):
                    windows[i]["embedding_ref"] = i
                ctx.log(
                    f"CLAP batch embed complete ({len(vectors)} vectors).",
                    level="success",
                    stage="interview_spine_build",
                )
            else:
                ctx.log(
                    "CLAP batch embed returned no usable vectors "
                    f"(parsed_keys={sorted(parsed.keys())}, out_exists={out_path.is_file()}).",
                    level="warning",
                    stage="interview_spine_build",
                    detail={"stderr_tail": (proc.stderr or "")[-300:]},
                )
        else:
            ctx.log(
                f"CLAP batch embed failed (exit {proc.returncode}); "
                f"parsed={bool(parsed)}.",
                level="warning",
                stage="interview_spine_build",
                detail={"stderr": (proc.stderr or "")[:300], "stdout_tail": (proc.stdout or "")[-200:]},
            )
    except (LocalRuntimeUnavailable, OSError, subprocess.TimeoutExpired) as exc:
        ctx.log(
            f"CLAP batch embed unavailable ({type(exc).__name__}: {exc}).",
            level="warning",
            stage="interview_spine_build",
        )
        vectors = []

    if len(vectors) != len(windows):
        if len(windows) > _PER_WINDOW_FALLBACK_MAX:
            ctx.log(
                f"CLAP skipping per-window fallback ({len(windows)} windows > "
                f"{_PER_WINDOW_FALLBACK_MAX}); spine continues without embeddings.",
                level="warning",
                stage="interview_spine_build",
            )
            return False, None, None
        ctx.log(
            f"CLAP per-window fallback ({len(windows)} window(s)).",
            level="warning",
            stage="interview_spine_build",
        )
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
            result = parse_runtime_json_stdout(proc.stdout or "") or parse_runtime_json_stdout(
                proc.stderr or ""
            )
            if not isinstance(result, dict) or not result.get("available"):
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
