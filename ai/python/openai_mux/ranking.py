from __future__ import annotations

import json
from typing import Any

from openai_mux.prompts import (
    default_segment_ranking_rubric,
    segment_ranking_system_prompt,
)


def rank_segments_by_rubric(
    client: Any,
    *,
    model: str,
    segments: list[dict[str, str]],
    extra_instructions: str = "",
) -> list[str]:
    """
    Order segment_ids using an OpenAI chat model and a fixed rubric (see docs:
    pipeline/scoring-and-selection/llm-assisted-ranking.md).

    Each segment dict must include ``segment_id`` and ``text`` (transcript excerpt).
    """
    if not segments:
        return []
    ids = [s["segment_id"] for s in segments]
    if len(set(ids)) != len(ids):
        raise ValueError("segment_id values must be unique")

    payload = [{"segment_id": s["segment_id"], "text": s["text"]} for s in segments]
    rubric = default_segment_ranking_rubric().rstrip()
    if extra_instructions.strip():
        rubric = rubric + " " + extra_instructions.strip()

    user = json.dumps({"segments": payload, "rubric": rubric}, ensure_ascii=False)

    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": segment_ranking_system_prompt()},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    raw = (resp.choices[0].message.content or "").strip()
    data = json.loads(raw)
    ordered = data.get("ordered_segment_ids")
    if not isinstance(ordered, list):
        raise ValueError("Model response missing ordered_segment_ids list")
    out = [str(x) for x in ordered]
    if set(out) != set(ids) or len(out) != len(ids):
        raise ValueError("Model returned invalid permutation of segment_id values")
    return out
