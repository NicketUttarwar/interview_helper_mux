"""Deterministic post-ranking guards for succinct-master framing exclusions."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.gap_framing import gap_framing_cfg, load_gap_framing_plan, ranking_exclude_segment_ids
from interview_mux.run_context import RunContext


def validate_framing_ranking(ctx: RunContext, selection: dict[str, Any]) -> list[str]:
    """Return lint errors/warnings for framing-aware ranking decisions."""
    cfg = gap_framing_cfg()
    errors: list[str] = []
    if not cfg.get("allow_replace_source_segments", True):
        return errors

    excluded_raw = selection.get("excluded_segment_ids") or []
    excluded_ids: set[str] = set()
    for row in excluded_raw:
        if isinstance(row, dict):
            sid = str(row.get("segment_id") or "")
            reason = str(row.get("reason") or "")
            if sid:
                excluded_ids.add(sid)
            if sid and reason == "covered_by_framing_vo":
                continue
        elif isinstance(row, str) and row:
            excluded_ids.add(row)

    framing_excludes = ranking_exclude_segment_ids(ctx)
    manifest_count = 0
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        manifest_count = len(manifest.get("segments") or [])

    if manifest_count and cfg.get("max_exclusion_ratio") is not None:
        ratio = len(framing_excludes) / max(manifest_count, 1)
        cap = float(cfg.get("max_exclusion_ratio", 0.15))
        if ratio > cap:
            errors.append(
                f"framing exclusions {len(framing_excludes)}/{manifest_count} exceed max_exclusion_ratio {cap:.2f}"
            )

    plan = load_gap_framing_plan(ctx)
    if plan and cfg.get("never_exclude_primary_impact", True):
        for act in plan.get("acts") or []:
            if not isinstance(act, dict):
                continue
            for block in act.get("impact_blocks") or []:
                if not isinstance(block, dict):
                    continue
                primaries = [str(s) for s in (block.get("source_segment_ids") or []) if s]
                for sid in primaries:
                    if sid in excluded_ids:
                        errors.append(
                            f"primary impact segment {sid} excluded — never_exclude_primary_impact"
                        )

    if cfg.get("require_topic_survival", True) and ctx.artifact_exists("master/coverage_audit.json"):
        audit = ctx.read_json("master/coverage_audit.json")
        topic_maps = audit.get("topic_segment_map") or audit.get("topics") or []
        for row in topic_maps if isinstance(topic_maps, list) else []:
            if not isinstance(row, dict):
                continue
            segs = [str(s) for s in (row.get("segment_ids") or row.get("segments") or []) if s]
            if not segs:
                continue
            excluded_for_topic = [s for s in segs if s in framing_excludes or s in excluded_ids]
            if len(excluded_for_topic) == len(segs):
                topic = row.get("topic_id") or row.get("topic") or row.get("title") or "unknown"
                errors.append(f"topic {topic} would have no surviving segment after framing exclusions")

    return errors


def enforce_framing_ranking(ctx: RunContext, selection: dict[str, Any]) -> dict[str, Any]:
    """Apply deterministic guards; auto-heal primary-impact exclusions when possible."""
    out = dict(selection)
    cfg = gap_framing_cfg()
    if cfg.get("never_exclude_primary_impact", True):
        plan = load_gap_framing_plan(ctx)
        primary_ids: set[str] = set()
        if plan:
            for act in plan.get("acts") or []:
                if not isinstance(act, dict):
                    continue
                for block in act.get("impact_blocks") or []:
                    if not isinstance(block, dict):
                        continue
                    primary_ids.update(str(s) for s in (block.get("source_segment_ids") or []) if s)
        if primary_ids:
            excluded_raw = list(out.get("excluded_segment_ids") or [])
            kept_excl: list[Any] = []
            restored: list[str] = []
            for row in excluded_raw:
                sid = ""
                if isinstance(row, dict):
                    sid = str(row.get("segment_id") or "")
                elif isinstance(row, str):
                    sid = row
                if sid and sid in primary_ids:
                    restored.append(sid)
                    continue
                kept_excl.append(row)
            if restored:
                out["excluded_segment_ids"] = kept_excl
                ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
                for sid in restored:
                    if sid not in ordered:
                        ordered.append(sid)
                out["ordered_segment_ids"] = ordered
                ctx.log(
                    "framing_coverage_guard: restored primary impact segment(s) "
                    f"{', '.join(restored[:6])}",
                    level="info",
                    stage="full_master_ranking",
                )
    issues = validate_framing_ranking(ctx, out)
    if issues:
        hardening = (merged_config().get("analysis") or {}).get("flow_hardening") or {}
        strict = bool(hardening.get("strict_critical_stages", True))
        msg = "; ".join(issues[:6])
        ctx.log(f"framing_coverage_guard: {msg}", level="warning", stage="full_master_ranking")
        if strict and any("never_exclude_primary_impact" in i or "no surviving segment" in i for i in issues):
            raise ValueError(f"framing_coverage_guard: {msg}")
    return out
