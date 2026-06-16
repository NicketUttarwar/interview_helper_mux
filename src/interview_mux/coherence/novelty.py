from __future__ import annotations

from typing import Any

import numpy as np

from interview_mux.interview_spine.paths import SPINE_EMBEDDINGS_REL


def compute_novelty_scores(windows: list[dict[str, Any]], ctx) -> dict[str, float]:
    """Return window_id -> novelty_score in [0, 1]."""
    if len(windows) < 2:
        return {}

    packed = _load_embeddings(ctx)
    if packed is not None:
        embeddings, window_ids = packed
        by_id = {w["window_id"]: w for w in windows}
        scores: dict[str, float] = {}
        for i in range(1, len(window_ids)):
            wid = window_ids[i]
            if wid not in by_id:
                continue
            prev_idx = i - 1
            while prev_idx >= 0 and window_ids[prev_idx] not in by_id:
                prev_idx -= 1
            if prev_idx < 0:
                continue
            a = embeddings[i].astype(np.float32)
            b = embeddings[prev_idx].astype(np.float32)
            na = np.linalg.norm(a)
            nb = np.linalg.norm(b)
            if na < 1e-9 or nb < 1e-9:
                sim = 0.0
            else:
                sim = float(np.dot(a / na, b / nb))
            scores[wid] = round(max(0.0, min(1.0, 1.0 - sim)), 4)
        return scores

    return _prosody_fallback_novelty(windows)


def _load_embeddings(ctx) -> tuple[np.ndarray, list[str]] | None:
    sidecar = ctx.path(*SPINE_EMBEDDINGS_REL.split("/"))
    if not sidecar.is_file():
        return None
    data = np.load(sidecar, allow_pickle=True)
    if "embeddings" not in data or "window_ids" not in data:
        return None
    embeddings = data["embeddings"].astype(np.float32)
    window_ids = [str(x) for x in data["window_ids"].tolist()]
    if embeddings.size == 0:
        return None
    return embeddings, window_ids


def _prosody_fallback_novelty(windows: list[dict[str, Any]]) -> dict[str, float]:
    sorted_wins = sorted(windows, key=lambda w: int(w.get("start_ms", 0)))
    scores: dict[str, float] = {}
    for i in range(1, len(sorted_wins)):
        cur = sorted_wins[i]
        prev = sorted_wins[i - 1]
        cf = cur.get("features") or {}
        pf = prev.get("features") or {}
        rms_delta = abs(float(cf.get("rms_p50") or 0) - float(pf.get("rms_p50") or 0))
        pause_delta = abs(float(cf.get("pause_before_ms") or 0) - float(pf.get("pause_before_ms") or 0))
        f0_a = pf.get("f0_median_hz")
        f0_b = cf.get("f0_median_hz")
        f0_delta = 0.0
        if f0_a and f0_b:
            f0_delta = abs(float(f0_b) - float(f0_a)) / max(float(f0_a), 1.0)
        raw = rms_delta * 2.0 + min(pause_delta / 1200.0, 1.0) + min(f0_delta, 1.0)
        scores[str(cur["window_id"])] = round(max(0.0, min(1.0, raw / 3.0)), 4)
    return scores
