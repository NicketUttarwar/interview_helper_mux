"""P2: coverage_audit / narrative_plan / sfx_prompts / mmaudio_qa sanitizers."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_sanitize.types import SanitizeResult


def sanitize_coverage_audit(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    actions: list[dict[str, Any]] = []
    out = dict(doc or {})
    order: set[str] = set()
    if ctx.artifact_exists("master/selection.json"):
        try:
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                order = {str(s) for s in (sel.get("ordered_segment_ids") or []) if s}
        except Exception:
            pass
    topics = out.get("topics") or out.get("items")
    if isinstance(topics, list) and order:
        for row in topics:
            if not isinstance(row, dict):
                continue
            ids = row.get("segment_ids")
            if isinstance(ids, list):
                filtered = [str(s) for s in ids if str(s) in order]
                if filtered != [str(s) for s in ids]:
                    row["segment_ids"] = filtered
                    actions.append({"action": "drop_orphan_topic_segment_ids"})
    return SanitizeResult(doc=out, actions=actions, ok=True, artifact_rel="master/coverage_audit.json")


def sanitize_narrative_plan(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    actions: list[dict[str, Any]] = []
    out = dict(doc or {})
    order: set[str] = set()
    if ctx.artifact_exists("master/selection.json"):
        try:
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                order = {str(s) for s in (sel.get("ordered_segment_ids") or []) if s}
        except Exception:
            pass
    chapters = out.get("chapters")
    if isinstance(chapters, list) and order:
        new_ch = []
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            ids = [str(s) for s in (ch.get("segment_ids") or []) if str(s) in order]
            row = dict(ch)
            row["segment_ids"] = ids
            if not ids:
                actions.append({"action": "drop_empty_narrative_chapter"})
                continue
            new_ch.append(row)
        out["chapters"] = new_ch
    return SanitizeResult(doc=out, actions=actions, ok=True, artifact_rel="master/narrative_plan.json")


def sanitize_sfx_prompts(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    actions: list[dict[str, Any]] = []
    out = dict(doc or {})
    prompts = out.get("prompts") or out.get("items")
    if isinstance(prompts, list):
        kept = [p for p in prompts if isinstance(p, dict) and str(p.get("text") or p.get("prompt") or "").strip()]
        if len(kept) != len(prompts):
            key = "prompts" if "prompts" in out else "items"
            out[key] = kept
            actions.append({"action": "drop_blank_sfx_prompts", "count": len(prompts) - len(kept)})
    return SanitizeResult(doc=out, actions=actions, ok=True, artifact_rel="sound_design/sfx_prompts.json")


def sanitize_mmaudio_qa(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    actions: list[dict[str, Any]] = []
    out = dict(doc or {})
    assets = out.get("assets")
    if assets is not None and not isinstance(assets, list):
        return SanitizeResult(
            doc=out,
            ok=False,
            errors=["mmaudio_qa assets invalid"],
            artifact_rel="sound_design/mmaudio_qa.json",
        )
    if isinstance(assets, list) and not assets:
        actions.append({"action": "note_empty_mmaudio_assets"})
    return SanitizeResult(doc=out, actions=actions, ok=True, artifact_rel="sound_design/mmaudio_qa.json")
