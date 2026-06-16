from __future__ import annotations

import json
from typing import Any

import numpy as np

from interview_mux.interview_spine.paths import SPINE_EMBEDDINGS_REL, SPINE_PATH


def load_spine(ctx) -> dict[str, Any] | None:
    if not ctx.artifact_exists(SPINE_PATH):
        return None
    doc = ctx.read_json(SPINE_PATH)
    return doc if isinstance(doc, dict) else None


def _load_embeddings(ctx) -> tuple[np.ndarray, list[str]] | None:
    sidecar = ctx.path(*SPINE_EMBEDDINGS_REL.split("/"))
    if not sidecar.is_file():
        return None
    data = np.load(sidecar, allow_pickle=True)
    embeddings = data["embeddings"].astype(np.float32)
    window_ids = [str(x) for x in data["window_ids"].tolist()]
    return embeddings, window_ids


def _embed_query_text(text: str, model_id: str) -> np.ndarray | None:
    from interview_mux.local_runtime import run_runtime_script

    # Reuse clap_similarity text path via similarity tool with dummy wav is awkward;
    # use clap_similarity with full file for text-only: embed via subprocess JSON.
    payload = json.dumps({"text": text, "model_id": model_id, "text_only": True})
    proc = run_runtime_script("mmaudio", "tools/clap_embed_window.py", [], stdin_data=payload)
    if proc.returncode != 0:
        return None
    try:
        result = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    vec = result.get("vector")
    if not isinstance(vec, list):
        return None
    arr = np.array(vec, dtype=np.float32)
    norm = np.linalg.norm(arr)
    return arr / norm if norm > 0 else arr


def query_spine(ctx, query_text: str, *, top_k: int = 5) -> list[dict[str, Any]]:
    spine = load_spine(ctx)
    if not spine or not (spine.get("retrieval") or {}).get("enabled"):
        return []

    packed = _load_embeddings(ctx)
    if packed is None:
        return _text_fallback_query(spine, query_text, top_k=top_k)
    embeddings, window_ids = packed
    if embeddings.size == 0:
        return []

    model_id = str((spine.get("retrieval") or {}).get("model_id") or "laion/clap-htsat-fused")
    query_vec = _embed_query_text(query_text.strip(), model_id)
    if query_vec is None:
        return _text_fallback_query(spine, query_text, top_k=top_k)

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-9)
    normed = embeddings / norms
    scores = normed @ query_vec
    order = np.argsort(scores)[::-1][:top_k]

    by_id = {w["window_id"]: w for w in spine.get("windows") or []}
    hits: list[dict[str, Any]] = []
    for idx in order:
        wid = window_ids[int(idx)]
        win = by_id.get(wid)
        if not win:
            continue
        hits.append(
            {
                "window_id": wid,
                "start_ms": win.get("start_ms"),
                "end_ms": win.get("end_ms"),
                "text_span": win.get("text_span"),
                "score": round(float(scores[int(idx)]), 4),
            }
        )
    return hits


def _text_fallback_query(spine: dict[str, Any], query_text: str, *, top_k: int) -> list[dict[str, Any]]:
    q = query_text.lower().split()
    if not q:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for win in spine.get("windows") or []:
        text = str(win.get("text_span") or "").lower()
        overlap = sum(1 for token in q if token in text)
        if overlap:
            scored.append((overlap / len(q), win))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "window_id": w["window_id"],
            "start_ms": w.get("start_ms"),
            "end_ms": w.get("end_ms"),
            "text_span": w.get("text_span"),
            "score": round(score, 4),
        }
        for score, w in scored[:top_k]
    ]
