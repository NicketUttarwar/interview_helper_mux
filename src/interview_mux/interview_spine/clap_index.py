from __future__ import annotations

import json
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
    """Embed each window; write embeddings.npz. Returns (enabled, sidecar_rel, dim)."""
    from interview_mux.local_runtime import run_runtime_script

    vectors: list[list[float]] = []
    for i, win in enumerate(windows):
        payload = json.dumps(
            {
                "wav_path": str(wav_path),
                "start_ms": int(win["start_ms"]),
                "end_ms": int(win["end_ms"]),
                "model_id": model_id,
            }
        )
        proc = run_runtime_script(
            "mmaudio",
            "tools/clap_embed_window.py",
            [],
            stdin_data=payload,
            timeout_sec=timeout_sec,
        )
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
