"""Sanitize understanding/nugget_layup_plan.json — refuse-hollow (W2)."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_sanitize.halt import sanitize_refused_message
from interview_mux.artifact_sanitize.reentry import (
    stamp_matches,
    stamp_sanitize_meta,
)
from interview_mux.artifact_sanitize.types import SanitizeResult

REL = "understanding/nugget_layup_plan.json"
_CONTENT_KEYS = ["ordered_segment_ids", "layups", "status"]


def _selection_order(ctx: Any) -> list[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return []
    try:
        sel = ctx.read_json("master/selection.json")
    except Exception:
        return []
    if not isinstance(sel, dict):
        return []
    return [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]


def sanitize_nugget_layup_plan(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    actions: list[dict[str, Any]] = []
    errors: list[str] = []
    out = dict(doc or {})

    if stamp_matches(out, content_keys=_CONTENT_KEYS):
        meta = out.get("_meta") if isinstance(out.get("_meta"), dict) else {}
        stamp = meta.get("sanitize") if isinstance(meta.get("sanitize"), dict) else {}
        if stamp.get("ok") is True and not out.get("_meta", {}).get("needs_recompose"):
            return SanitizeResult(
                doc=out,
                ok=True,
                artifact_rel=REL,
                metrics={"skipped": "sanitary_hash_match"},
            )

    order = _selection_order(ctx)
    order_set = set(order)

    # compose_restart / empty
    if out.get("compose_restart") is True:
        errors.append("compose_restart_active")
    plan_ids = out.get("ordered_segment_ids")
    layups = out.get("layups")
    if not isinstance(layups, list):
        layups = []
        out["layups"] = layups
        actions.append({"action": "init_layups"})

    if order and (not isinstance(plan_ids, list) or not plan_ids) and not layups:
        errors.append("empty_layup_plan_with_selection")

    # Align order to selection — but refuse if that would fake freshness without rows
    if isinstance(plan_ids, list) and order:
        filtered = [str(s) for s in plan_ids if str(s) in order_set]
        if filtered != [str(s) for s in plan_ids]:
            out["ordered_segment_ids"] = filtered
            actions.append(
                {
                    "action": "align_layup_order_to_selection",
                    "before": len(plan_ids),
                    "after": len(filtered),
                }
            )
        if set(filtered) != set(order):
            # Do NOT silently adopt full selection to fake freshness
            meta = dict(out.get("_meta") or {}) if isinstance(out.get("_meta"), dict) else {}
            meta["needs_recompose"] = True
            out["_meta"] = meta
            errors.append("layup_order_mismatch_needs_recompose")
            actions.append({"action": "flag_needs_recompose_order_mismatch"})

    # Drop blank non-skip rows; strip never-touch CTA
    banned: set[str] = set()
    try:
        from interview_mux.media_ip_cta import never_touch_segment_ids

        banned = set(never_touch_segment_ids(ctx) or [])
    except Exception:
        banned = set()

    cleaned_layups: list[dict[str, Any]] = []
    for row in layups:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or row.get("target_segment_id") or "")
        if sid and sid in banned:
            actions.append({"action": "drop_never_touch_cta_layup", "segment_id": sid})
            continue
        text = str(row.get("text") or row.get("script") or "").strip()
        is_skip = bool(row.get("skip") or row.get("skipped") or row.get("omit"))
        if not text and not is_skip:
            actions.append({"action": "drop_blank_layup_row", "segment_id": sid})
            continue
        if sid and order_set and sid not in order_set:
            actions.append({"action": "drop_off_air_layup_row", "segment_id": sid})
            continue
        cleaned_layups.append(row)
    if len(cleaned_layups) != len(layups):
        out["layups"] = cleaned_layups
        layups = cleaned_layups

    # Freshness
    try:
        from interview_mux.nugget_layup import layup_freshness_errors

        fresh = layup_freshness_errors(ctx)
        if fresh:
            # If we already flagged recompose, keep; else refuse
            for e in list(fresh)[:4]:
                if "stale" in str(e).lower() or "fresh" in str(e).lower():
                    errors.append(str(e))
    except Exception:
        pass

    # QC / coverage — refuse hollow
    try:
        from interview_mux.nugget_layup import evaluate_layup_qc

        qc = evaluate_layup_qc(ctx, out)
        if isinstance(qc, dict):
            for e in (qc.get("errors") or [])[:6]:
                errors.append(f"layup_qc:{e}")
    except Exception:
        aired = [
            r
            for r in layups
            if isinstance(r, dict)
            and not (r.get("skip") or r.get("skipped") or r.get("omit"))
            and str(r.get("text") or r.get("script") or "").strip()
        ]
        meta_l = out.get("_meta") if isinstance(out.get("_meta"), dict) else {}
        if (
            order
            and len(aired) / max(1, len(order)) < 0.70
            and not meta_l.get("needs_recompose")
            and str(out.get("status") or "").lower() in {"", "ok", "complete", "done"}
        ):
            errors.append(
                f"layup_coverage_below_floor:{len(aired) / max(1, len(order)):.3f}"
            )

    # Adopt-only / skip-stuffed detection — only when skips lack justification.
    # Sparse justified plans (self-orient / spoken-copy / CTA) pass QC with high
    # skip ratios; treating them as stuffed forced endless recompose thrash.
    if layups and order:
        skips = [
            r
            for r in layups
            if isinstance(r, dict) and (r.get("skip") or r.get("skipped") or r.get("omit"))
        ]
        if len(skips) >= max(1, int(0.8 * len(layups))) and len(layups) >= 5:
            justified = 0
            try:
                from interview_mux.nugget_layup import is_justified_skip_row

                justified = sum(
                    1 for r in skips if is_justified_skip_row(r, soft_migrate=True)
                )
            except Exception:
                justified = 0
            if justified < int(0.8 * len(skips)):
                errors.append("layup_skip_stuffed_needs_recompose")
                meta = dict(out.get("_meta") or {}) if isinstance(out.get("_meta"), dict) else {}
                meta["needs_recompose"] = True
                out["_meta"] = meta
            else:
                meta = dict(out.get("_meta") or {}) if isinstance(out.get("_meta"), dict) else {}
                if meta.pop("needs_recompose", None) is not None:
                    out["_meta"] = meta
                    actions.append({"action": "clear_needs_recompose_justified_skips"})

    ok = not errors
    out = stamp_sanitize_meta(
        out,
        ok=ok,
        source="artifact_sanitize.nugget_layup_plan",
        actions_n=len(actions),
        content_keys=_CONTENT_KEYS,
    )
    return SanitizeResult(
        doc=out,
        actions=actions,
        ok=ok,
        errors=errors,
        artifact_rel=REL,
        metrics={"actions": len(actions), "layup_count": len(layups)},
    )


def layup_sanitary_errors(ctx: Any) -> list[str]:
    from interview_mux.artifact_sanitize.config import block_consumers_on_unsanitary

    if not block_consumers_on_unsanitary():
        return []
    if not ctx.artifact_exists(REL):
        return [f"{REL} missing"]
    try:
        doc = ctx.read_json(REL)
    except Exception as exc:
        return [f"{REL} unreadable: {exc}"]
    if not isinstance(doc, dict):
        return [f"{REL} invalid"]
    meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
    if meta.get("needs_recompose"):
        return ["layup_needs_recompose"]
    if stamp_matches(doc, content_keys=_CONTENT_KEYS):
        stamp = meta.get("sanitize") if isinstance(meta.get("sanitize"), dict) else {}
        if stamp.get("ok") is True:
            return []
    result = sanitize_nugget_layup_plan(ctx, doc)
    if result.ok and not result.actions:
        return []
    if not result.ok:
        return list(result.errors or ["layup sanitize refused"])
    return [
        "layup_needs_sanitize:"
        + ",".join(str(a.get("action") or "") for a in (result.actions or [])[:6])
    ]
