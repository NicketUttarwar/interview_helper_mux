"""Playability SSOT — reason-coded unplayable classes for keep/impact/order.

Closed reasons only (no live blank heuristics). Callers derive hard-keep drops,
primary-impact exemptions, and lattice order strips from this module so lists
cannot drift.
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

# Lattice step 1–2: these exclude reasons beat hard-keep / primary-impact.
UNPLAYABLE_EXCLUDE_REASONS: frozenset[str] = frozenset(
    {
        "blank_or_unusable_answer_audio",
        "never_touch_unplayable",
        "cta_omit",
        "media_ip_cta",
        "selection_cta_exclude",
        "finale_tail_leftover",
        "opening_skipped_duplicate",
    }
)

BLANK_EXCLUDE_REASON = "blank_or_unusable_answer_audio"


def _reason_map(selection: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(selection, dict):
        return {}
    out: dict[str, str] = {}
    rationales = (
        selection.get("exclude_rationales")
        if isinstance(selection.get("exclude_rationales"), dict)
        else {}
    )
    for sid, reason in rationales.items():
        key = str(sid or "").strip()
        if key:
            out[key] = str(reason or "").strip()
    for row in selection.get("excluded_segment_ids") or []:
        if isinstance(row, dict):
            sid = str(row.get("segment_id") or "").strip()
            if not sid:
                continue
            reason = str(row.get("reason") or out.get(sid) or "").strip()
            if reason:
                out[sid] = reason
        elif isinstance(row, str) and row.strip():
            sid = row.strip()
            if sid not in out and str(rationales.get(sid) or "").strip():
                out[sid] = str(rationales.get(sid) or "").strip()
    return out


def load_selection(
    ctx: RunContext | None,
    selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(selection, dict):
        return selection
    if ctx is None or not ctx.artifact_exists("master/selection.json"):
        return {}
    try:
        doc = ctx.read_json("master/selection.json")
    except Exception:
        return {}
    return doc if isinstance(doc, dict) else {}


def unplayable_reason_by_id(
    ctx: RunContext | None,
    selection: dict[str, Any] | None = None,
) -> dict[str, str]:
    """segment_id → exclude reason for unplayable / packaging classes."""
    sel = load_selection(ctx, selection)
    reasons = {
        sid: reason
        for sid, reason in _reason_map(sel).items()
        if reason in UNPLAYABLE_EXCLUDE_REASONS or reason.startswith("cta_")
    }
    # CTA / never-touch unions even when selection rows are thin.
    if ctx is not None:
        try:
            from interview_mux.media_ip_cta import (
                never_touch_segment_ids,
                ranking_cta_omit_ids,
                selection_cta_exclude_ids,
            )

            for sid in (
                never_touch_segment_ids(ctx)
                | selection_cta_exclude_ids(ctx)
                | ranking_cta_omit_ids(ctx)
            ):
                key = str(sid or "").strip()
                if key and key not in reasons:
                    reasons[key] = "selection_cta_exclude"
        except Exception:
            pass
    return reasons


def unplayable_segment_ids(
    ctx: RunContext | None,
    selection: dict[str, Any] | None = None,
) -> set[str]:
    return set(unplayable_reason_by_id(ctx, selection))


def blank_excluded_ids(
    ctx: RunContext | None,
    selection: dict[str, Any] | None = None,
) -> set[str]:
    """Only blank_or_unusable_answer_audio — safe for primary-impact exemption."""
    sel = load_selection(ctx, selection)
    return {
        sid
        for sid, reason in _reason_map(sel).items()
        if reason == BLANK_EXCLUDE_REASON
    }


def is_unplayable_for_primary_impact(
    ctx: RunContext | None,
    sid: str,
    selection: dict[str, Any] | None = None,
) -> bool:
    """Primary-impact never-exclude does not apply to blank-excluded tape.

    Intentionally narrow (blank reason only) — live heuristics are a footgun
    for short-but-valid speech.
    """
    return str(sid or "").strip() in blank_excluded_ids(ctx, selection)


def is_unplayable_for_hard_keep(
    ctx: RunContext | None,
    sid: str,
    selection: dict[str, Any] | None = None,
) -> bool:
    return str(sid or "").strip() in unplayable_segment_ids(ctx, selection)
