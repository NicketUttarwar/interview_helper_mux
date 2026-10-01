"""Sanitize understanding/sound_design_plan.json — schema-correct (W7)."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta
from interview_mux.artifact_sanitize.types import SanitizeResult

REL = "understanding/sound_design_plan.json"


def _selection_order(ctx: Any) -> set[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return set()
    try:
        sel = ctx.read_json("master/selection.json")
    except Exception:
        return set()
    if not isinstance(sel, dict):
        return set()
    return {str(s) for s in (sel.get("ordered_segment_ids") or []) if s}


def _cue_anchors(row: dict[str, Any]) -> list[str]:
    out = []
    for k in (
        "segment_id",
        "after_segment_id",
        "before_segment_id",
        "under_segment_id",
        "after",
        "before",
    ):
        v = str(row.get(k) or "")
        if v:
            out.append(v)
    return out


def sanitize_sound_design_plan(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    actions: list[dict[str, Any]] = []
    errors: list[str] = []
    out = dict(doc or {})
    order = _selection_order(ctx)

    # Legacy top-level keys (thin / rarely used)
    for key in ("cues", "beds", "hits", "themes", "events"):
        rows = out.get(key)
        if not isinstance(rows, list) or not order:
            continue
        kept = []
        dropped = 0
        for row in rows:
            if not isinstance(row, dict):
                kept.append(row)
                continue
            anchors = _cue_anchors(row)
            if anchors and all(a not in order for a in anchors):
                dropped += 1
                continue
            kept.append(row)
        if dropped:
            out[key] = kept
            actions.append({"action": f"drop_{key}_off_air", "count": dropped})

    # Real schema: flow_plans.*.cues
    flow = out.get("flow_plans")
    if isinstance(flow, dict) and order:
        for fname, fdoc in list(flow.items()):
            if not isinstance(fdoc, dict):
                continue
            cues = fdoc.get("cues")
            if not isinstance(cues, list):
                continue
            kept = []
            dropped = 0
            for row in cues:
                if not isinstance(row, dict):
                    continue
                anchors = _cue_anchors(row)
                # Any off-air anchor drops the cue (parity with repair any-anchor rule).
                if anchors and any(a not in order for a in anchors):
                    dropped += 1
                    continue
                # drop blank prompts
                text = str(row.get("description") or row.get("prompt") or row.get("text") or "")
                role = str(row.get("role") or "")
                if not text.strip() and role in {"", "bed", "theme"}:
                    dropped += 1
                    actions.append({"action": "drop_blank_cue", "flow": fname})
                    continue
                kept.append(row)
            if dropped:
                fdoc = dict(fdoc)
                fdoc["cues"] = kept
                flow[fname] = fdoc
                actions.append(
                    {"action": "drop_flow_cues_off_air", "flow": fname, "count": dropped}
                )
        out["flow_plans"] = flow

    # Palettes segment_ids intersection
    palettes = out.get("palettes")
    if isinstance(palettes, list) and order:
        new_p = []
        for pal in palettes:
            if not isinstance(pal, dict):
                continue
            ids = pal.get("segment_ids")
            if isinstance(ids, list):
                filtered = [str(s) for s in ids if str(s) in order]
                if filtered != [str(s) for s in ids]:
                    pal = dict(pal)
                    pal["segment_ids"] = filtered
                    actions.append({"action": "prune_palette_segment_ids"})
                if not filtered:
                    actions.append({"action": "drop_empty_palette"})
                    continue
            new_p.append(pal)
        out["palettes"] = new_p

    # Duplicate asset ids (ISSUES 122): the model repeats an asset row often
    # enough that the prompt craft, which writes one prompt per id, can never
    # match the row count the pre-flush check compares against. First row wins.
    try:
        from interview_mux.sound_design_caps import dedupe_assets

        out, dedupe = dedupe_assets(out)
        if dedupe:
            actions.append(dedupe)
    except Exception:
        pass

    # Asset cap (ISSUES 114): the barrier refuses a plan over the cap, so the
    # plan on disk never exceeds it. Cue-referenced assets outrank the rest.
    try:
        from interview_mux.sound_design_caps import clamp_assets_to_cap, sound_design_asset_cap

        out, clamp = clamp_assets_to_cap(out, sound_design_asset_cap(ctx))
        if clamp:
            actions.append(clamp)
    except Exception:
        pass

    # Clear false stale only when we have a sanitize stamp and selection lock matches
    # (actual fingerprint clear is producer responsibility — we only note)
    meta = dict(out.get("_meta") or {}) if isinstance(out.get("_meta"), dict) else {}
    if meta.get("stale") and actions:
        actions.append({"action": "note_stale_meta_present"})

    ok = not errors
    out = stamp_sanitize_meta(
        out,
        ok=ok,
        source="artifact_sanitize.sound_design_plan",
        actions_n=len(actions),
    )
    return SanitizeResult(
        doc=out,
        actions=actions,
        ok=ok,
        errors=errors,
        artifact_rel=REL,
        metrics={"actions": len(actions)},
    )


def sdp_sanitary_errors(ctx: Any) -> list[str]:
    from interview_mux.artifact_sanitize.config import block_consumers_on_unsanitary
    from interview_mux.artifact_sanitize.reentry import stamp_matches

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
    if meta.get("stale"):
        return [f"stale_meta:{meta.get('stale_reason') or 'stale'}"]
    if stamp_matches(doc):
        return []
    result = sanitize_sound_design_plan(ctx, doc)
    if result.ok and not result.actions:
        return []
    if not result.ok:
        return list(result.errors or ["sdp sanitize refused"])
    return [
        "sdp_needs_sanitize:"
        + ",".join(str(a.get("action") or "") for a in (result.actions or [])[:6])
    ]
