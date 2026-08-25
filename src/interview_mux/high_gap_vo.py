"""Secondary succinct VO generator for uncovered high-severity gaps."""

from __future__ import annotations

import json
import re
from typing import Any

from interview_mux.run_context import RunContext

PROMPT_REL = "interviewer-gap/high-gap-vo-fill.system.txt"

_CHILD_SUFFIX_RE = re.compile(r"^(seg_\d+)([a-z]+)$", re.IGNORECASE)
_SEG_IN_TEXT_RE = re.compile(r"(seg_\d+[a-z]*)", re.IGNORECASE)


def parent_id_of_segment(sid: str) -> str | None:
    m = _CHILD_SUFFIX_RE.match(str(sid or "").strip())
    return m.group(1) if m else None


def expand_targeted_with_parents(
    targeted: set[str],
    ctx: RunContext | None = None,
) -> set[str]:
    """Treat a child target as covering its parent (and vice versa)."""
    out = {str(s) for s in targeted if s}
    for sid in list(out):
        parent = parent_id_of_segment(sid)
        if parent:
            out.add(parent)
    if ctx is None or not ctx.artifact_exists("segments/manifest.json"):
        return out
    try:
        man = ctx.read_json("segments/manifest.json")
    except Exception:
        return out
    for row in (man or {}).get("segments") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or "")
        parent = str(row.get("parent_segment_id") or "") or (parent_id_of_segment(sid) or "")
        if not sid or not parent:
            continue
        if sid in out:
            out.add(parent)
        if parent in out:
            out.add(sid)
    return out


def targeted_segment_ids(
    lines: list[Any] | None,
    ctx: RunContext | None = None,
) -> set[str]:
    """Segment ids already covered by interviewer lines (targets, seeds, supports)."""
    targeted: set[str] = set()
    for ln in lines or []:
        if not isinstance(ln, dict):
            continue
        for key in ("targets_segment_id", "segment_id"):
            sid = str(ln.get(key) or "")
            if sid:
                targeted.add(sid)
        lid = str(ln.get("line_id") or "")
        if lid.startswith("vo_seed_") and len(lid) > len("vo_seed_"):
            targeted.add(lid[len("vo_seed_") :])
        if lid.startswith("vo_fill_") and len(lid) > len("vo_fill_"):
            targeted.add(lid[len("vo_fill_") :])
        for hit in _SEG_IN_TEXT_RE.findall(lid):
            targeted.add(hit)
        for sid in ln.get("supports_segment_ids") or []:
            if sid:
                targeted.add(str(sid))
        extracted = ln.get("extracted_from")
        if isinstance(extracted, dict):
            path = str(extracted.get("path") or "")
            if path.startswith("repair_seed:"):
                targeted.add(path.split(":", 1)[1].strip())
    return expand_targeted_with_parents(targeted, ctx)


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


def demote_uncovered_high_gaps(
    ctx: RunContext,
    *,
    gap_report: dict[str, Any] | None = None,
    origin: str = "uncovered_after_fill",
) -> int:
    """Demote remaining high-severity evals that still have no interviewer line.

    Compose lint rejects ``gap_report`` when a high gap has no targeting line.
    After seed/fill (and skip of blank/contiguous/unspeakable spans), leftover
    high rows cannot ship — demote them to medium with a typed reason so the
    stage can commit instead of looping forever.
    """
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return 0
    try:
        evals = ctx.read_json("understanding/gap_evaluations.json")
    except Exception:
        return 0
    if not isinstance(evals, dict):
        return 0
    report = gap_report
    if report is None and ctx.artifact_exists("understanding/gap_report.json"):
        loaded = ctx.read_json("understanding/gap_report.json")
        report = loaded if isinstance(loaded, dict) else {}
    lines = (report or {}).get("interviewer_lines") if isinstance(report, dict) else []
    targeted = targeted_segment_ids(lines if isinstance(lines, list) else [], ctx)
    demoted = 0
    rows: list[dict[str, Any]] = []
    for row in evals.get("evaluations") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or "")
        sev = str(row.get("severity") or "").lower()
        if sid and sev == "high" and sid not in targeted:
            row = dict(row)
            row["severity"] = "medium"
            row["severity_demotion_reason"] = origin
            demoted += 1
        rows.append(row)
    if not demoted:
        return 0
    out = dict(evals)
    out["evaluations"] = rows
    try:
        from interview_mux.artifact_writes import write_validated_artifact

        write_validated_artifact(
            ctx,
            "understanding/gap_evaluations.json",
            out,
            merge_from_disk=False,
            stage_key="missing_framing",
        )
    except Exception:
        ctx.write_json("understanding/gap_evaluations.json", out)
    return demoted


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
    targeted = targeted_segment_ids(lines, ctx)
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
        from interview_mux.homunculus.budget import (
            LimitExhausted,
            identity_exhausted,
            mark_identity_exhausted,
        )
        from interview_mux.stages.llm_runner import run_prompt_envelope
    except Exception:
        return 0
    import os

    fill_identity = "high_gap_vo_fill"
    if identity_exhausted(ctx, fill_identity):
        applied.append({"action": "high_gap_vo_fill_skip", "reason": "limit_exhausted"})
        demote_uncovered_high_gaps(ctx, gap_report=out, origin="limit_exhausted")
        return 0

    if not str(os.environ.get("OPENAI_API_KEY") or "").strip():
        return 0
    added = 0
    consecutive_empty = 0
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
            except LimitExhausted:
                mark_identity_exhausted(ctx, fill_identity)
                applied.append(
                    {"action": "high_gap_vo_fill_skip", "reason": "limit_exhausted"}
                )
                demote_uncovered_high_gaps(ctx, gap_report=out, origin="limit_exhausted")
                return added
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
            consecutive_empty += 1
            applied.append({"action": "high_gap_vo_fill_empty", "segment_id": sid})
            if consecutive_empty >= 2:
                applied.append({"action": "high_gap_vo_fill_abort", "reason": "consecutive_empty"})
                break
            continue
        consecutive_empty = 0
        lines.append(
            {
                "line_id": f"vo_fill_{sid}",
                "text": text,
                "delivery": "synthesize",
                "placement": "before",
                "targets_segment_id": sid,
                "gap_type": row.get("gap_type") or "missing_setup",
                "origin": origin,
                "required": True,
                "category": "story_bridge",
            }
        )
        targeted.add(sid)
        added += 1
        applied.append({"action": "high_gap_vo_fill", "segment_id": sid, "tier_origin": origin})
    return added
