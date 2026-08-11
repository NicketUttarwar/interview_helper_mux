"""Flagship vision pick among cover candidates — brilliance primary."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from interview_mux.config import require_secret
from interview_mux.model_registry import resolve_model, temperature_for_chat
from interview_mux.stages.llm_runner import load_system_prompt

_JSON_FENCE = re.compile(r"^```(?:json)?\s*([\s\S]*?)```\s*$", re.I)


def _strip_fences(text: str) -> str:
    s = text.strip()
    m = _JSON_FENCE.match(s)
    return m.group(1).strip() if m else s


def _b64_data_url(path: Path) -> str:
    raw = path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


def pick_cover_winner(
    *,
    candidate_paths: list[Path],
    episode_title: str | None = None,
    thesis: str | None = None,
    stage_key: str = "episode_cover_vision_pick",
) -> dict[str, Any]:
    """Ask flagship vision to rank candidates. Brilliance is primary among non-disqualified."""
    if not candidate_paths:
        raise ValueError("no candidates")

    system = load_system_prompt(
        "publishing/episode-cover-vision-pick.system.txt",
        include_preamble=False,
    )
    resolved = resolve_model(stage_key, task_kind="primary")
    model = resolved.model_id

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "episode_title": episode_title,
                    "thesis": thesis,
                    "candidate_count": len(candidate_paths),
                    "instructions": (
                        "Rank candidates 0..N-1. Hard-disqualify readable letters/words. "
                        "Among remaining, pick the most brilliant as winner_index."
                    ),
                },
                ensure_ascii=False,
            ),
        }
    ]
    for i, path in enumerate(candidate_paths):
        content.append({"type": "text", "text": f"Candidate index {i}:"})
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": _b64_data_url(path)},
            }
        )

    client = OpenAI(api_key=require_secret("OPENAI_API_KEY"))
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }
    temp = temperature_for_chat(model, "primary")
    if temp is not None:
        kwargs["temperature"] = temp

    from interview_mux.safe_pruning import create_chat_with_context_ladder

    resp = create_chat_with_context_ladder(
        client,
        kwargs,
        stage_key=stage_key,
        original_system=system,
        ctx=None,
    )
    raw = (resp.choices[0].message.content or "").strip()
    data = json.loads(_strip_fences(raw))
    if not isinstance(data, dict):
        raise RuntimeError("vision pick returned non-object")

    winner = data.get("winner_index")
    try:
        winner_i = int(winner)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid winner_index: {winner}") from exc
    if winner_i < 0 or winner_i >= len(candidate_paths):
        raise RuntimeError(f"winner_index out of range: {winner_i}")

    disqualified = data.get("disqualified") or []
    hard_dq: set[int] = set()
    for d in disqualified:
        if not isinstance(d, dict):
            continue
        reasons = " ".join(str(r).lower() for r in (d.get("reasons") or []))
        if any(k in reasons for k in ("letter", "text", "word", "photo", "broken", "empty")):
            try:
                hard_dq.add(int(d["index"]))
            except (KeyError, TypeError, ValueError):
                continue

    ranking = data.get("ranking") or list(range(len(candidate_paths)))
    if winner_i in hard_dq:
        alt = None
        for idx in ranking:
            try:
                ii = int(idx)
            except (TypeError, ValueError):
                continue
            if 0 <= ii < len(candidate_paths) and ii not in hard_dq:
                alt = ii
                break
        if alt is None:
            data["all_hard_failed"] = True
        else:
            winner_i = alt
            data["rationale"] = (
                str(data.get("rationale") or "")
                + f" (winner adjusted off hard-disqualified index)"
            ).strip()

    data["winner_index"] = winner_i
    data["pick_model"] = model
    data["candidate_count"] = len(candidate_paths)
    return data


def local_fallback_pick(candidate_paths: list[Path]) -> dict[str, Any]:
    """Deterministic pick when vision fails — first existing file."""
    for i, p in enumerate(candidate_paths):
        if p.is_file():
            return {
                "winner_index": i,
                "ranking": list(range(len(candidate_paths))),
                "brilliance_scores": [],
                "disqualified": [],
                "rationale": "vision_pick_unavailable_first_candidate",
                "pick_model": "local_fallback",
                "candidate_count": len(candidate_paths),
            }
    raise RuntimeError("no candidate files")
