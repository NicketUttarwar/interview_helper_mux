from __future__ import annotations

import json
from typing import Any


def _heuristic_scores(segments: list[dict[str, Any]]) -> list[tuple[str, float]]:
    """Simple salience: longer + more words → higher score."""
    scored = []
    for s in segments:
        dur = max(1, s["t_end_ms"] - s["t_start_ms"])
        words = len((s.get("text") or "").split())
        score = words * 1000 + dur * 0.01
        scored.append((s["segment_id"], score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def rank_segments_for_interview(
    conn: Any,
    interview_id: str,
    *,
    use_llm: bool = True,
    top_n: int | None = None,
) -> list[str]:
    """
    Load segments from DB, rank via openai_mux or heuristics, update scores_json, return ordered ids.
    """
    from mux_store import upsert_segment

    cur = conn.execute(
        """
        SELECT segment_id, t_start_ms, t_end_ms, text, scores_json
        FROM segment WHERE interview_id = ?
        ORDER BY t_start_ms
        """,
        (interview_id,),
    )
    rows = cur.fetchall()
    segments = [
        {
            "segment_id": r[0],
            "t_start_ms": r[1],
            "t_end_ms": r[2],
            "text": r[3] or "",
        }
        for r in rows
    ]
    if not segments:
        return []

    ordered: list[str]
    if use_llm:
        try:
            from mux_secrets import get_config_value, load_repo_config
            from openai_mux import get_openai_client, rank_segments_by_rubric
            from pipeline.common import repo_root

            load_repo_config(repo_root())
            client = get_openai_client(repo_root=repo_root())
            model = get_config_value("OPENAI_MODEL", "gpt-4o-mini")
            ordered = rank_segments_by_rubric(
                client,
                model=model,
                segments=[{"segment_id": s["segment_id"], "text": s["text"]} for s in segments],
            )
        except Exception:
            ordered = [sid for sid, _ in _heuristic_scores(segments)]
    else:
        ordered = [sid for sid, _ in _heuristic_scores(segments)]

    if top_n is not None:
        ordered = ordered[:top_n]

    rank_map = {sid: i for i, sid in enumerate(ordered)}
    for s in segments:
        scores = {"llm_rank": float(len(ordered) - rank_map.get(s["segment_id"], len(ordered)))}
        upsert_segment(
            conn,
            interview_id=interview_id,
            segment_id=s["segment_id"],
            t_start_ms=s["t_start_ms"],
            t_end_ms=s["t_end_ms"],
            text=s["text"],
            scores=scores,
        )
    return ordered
