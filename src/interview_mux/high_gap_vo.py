"""Secondary succinct VO generator for uncovered high-severity gaps."""

from __future__ import annotations

import json
from typing import Any

from interview_mux.run_context import RunContext

PROMPT_REL = "interviewer-gap/high-gap-vo-fill.system.txt"


def _seg_text(ctx: RunContext, sid: str) -> str:
    if not sid or not ctx.artifact_exists("segments/manifest.json"):
        return ""
    try:
        man = ctx.read_json("segments/manifest.json")
        for row in (man or {}).get("segments") or []:
            if isinstance(row, dict) and str(row.get("segment_id") or "") == sid:
                return str(row.get("text") or "")[:400]
    except Exception:
        return ""
    return ""


def fill_uncovered_high_gaps(
    ctx: RunContext,
    out: dict[str, Any],
    *,
    applied: list[dict[str, Any]],
    origin: str = "high_gap_vo_fill",
) -> int:
    """Append interviewer lines for high-severity evals with no targeting line."""
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return 0
    try:
        evals = ctx.read_json("understanding/gap_evaluations.json")
    except Exception:
        return 0
    lines = out.setdefault("interviewer_lines", [])
    if not isinstance(lines, list):
        lines = []
        out["interviewer_lines"] = lines
    targeted: set[str] = set()
    for ln in lines:
        if not isinstance(ln, dict):
            continue
        for key in ("targets_segment_id", "segment_id"):
            sid = str(ln.get(key) or "")
            if sid:
                targeted.add(sid)
        lid = str(ln.get("line_id") or "")
        if lid.startswith("vo_seed_") and len(lid) > 8:
            targeted.add(lid[8:])
        for sid in ln.get("supports_segment_ids") or []:
            if sid:
                targeted.add(str(sid))
    high = [
        r
        for r in (evals.get("evaluations") or [])
        if isinstance(r, dict)
        and str(r.get("severity") or "").lower() == "high"
        and str(r.get("segment_id") or "")
        and str(r.get("segment_id")) not in targeted
    ]
    if not high:
        return 0
    try:
        from interview_mux.stages.llm_runner import run_prompt_envelope
    except Exception:
        return 0
    import os

    if not str(os.environ.get("OPENAI_API_KEY") or "").strip():
        return 0
    added = 0
    for row in high[:12]:
        sid = str(row.get("segment_id") or "")
        payload = {
            "task": "Write one succinct interviewer line covering this high-severity gap.",
            "segment_id": sid,
            "gap_type": row.get("gap_type"),
            "severity": "high",
            "listener_confusion": str(row.get("listener_confusion") or "")[:240],
            "segment_excerpt": _seg_text(ctx, sid),
            "word_caps": {"question": 60, "setup": 20, "bridge": 50},
        }
        text = ""
        for tier in ("standard", "economy"):
            try:
                env = run_prompt_envelope(
                    "high_gap_vo_fill",
                    PROMPT_REL,
                    json.dumps(payload, indent=2, ensure_ascii=False),
                    ctx=ctx,
                    include_preamble=False,
                    task_kind="advisory",
                    explicit_tier=tier,
                    response_format={"type": "json_object"},
                )
            except Exception:
                continue
            arts = env.get("artifacts") if isinstance(env, dict) else None
            if isinstance(arts, dict):
                text = str(arts.get("text") or arts.get("line") or "").strip()
            if not text and isinstance(env, dict):
                text = str(env.get("text") or "").strip()
            if text:
                break
        if not text:
            applied.append({"action": "high_gap_vo_fill_empty", "segment_id": sid})
            continue
        lines.append(
            {
                "line_id": f"vo_fill_{sid}",
                "text": text,
                "delivery": "synthesize",
                "targets_segment_id": sid,
                "origin": origin,
                "required": True,
                "category": "story_bridge",
            }
        )
        targeted.add(sid)
        added += 1
        applied.append({"action": "high_gap_vo_fill", "segment_id": sid, "tier_origin": origin})
    return added
