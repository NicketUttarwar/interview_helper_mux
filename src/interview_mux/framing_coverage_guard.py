"""Deterministic post-ranking guards for succinct-master framing exclusions."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.gap_framing import gap_framing_cfg, load_gap_framing_plan, ranking_exclude_segment_ids
from interview_mux.run_context import RunContext

def _excluded_blank_ids(selection: dict[str, Any]) -> set[str]:
    """Blank-exclude IDs from a selection doc — playability SSOT."""
    from interview_mux.playability import blank_excluded_ids

    return blank_excluded_ids(None, selection)


def _impact_source_is_unenforceable(
    ctx: RunContext,
    sid: str,
    *,
    blank_excl: set[str],
    selection: dict[str, Any],
    ignore_selection_editorial: bool = False,
) -> bool:
    """Blank/unusable / CTA tape cannot be forced on-air as primary impact.

    Playability SSOT: blank_or_unusable exclude only — live blank heuristics
    are too aggressive for short-but-valid fixture/content text.

    Media-IP / never-touch CTA scraps also cannot be forced back by framing
    restore (exec_13198 seg_070 garbled post-CTA thrash).

    When ``ignore_selection_editorial`` is True (CTA restore / inject), do not
    treat the current exclude-reason stamp as permanent — that stamp is what
    we may be healing (FMR S2).
    """
    key = str(sid or "").strip()
    if not key:
        return True
    # A fuse union folded this source into an on-air survivor: its tape airs,
    # so "excluded" is only the retired id (same rule as hard keeps, ISSUES 64).
    try:
        from interview_mux.edl_overlap_repair import consumed_segment_ids

        if key in consumed_segment_ids(ctx):
            return True
    except Exception:
        pass
    try:
        if ctx.artifact_exists("segments/manifest.json"):
            man = ctx.read_json("segments/manifest.json")
            live = {
                str(row.get("segment_id") or "")
                for row in (man.get("segments") or [])
                if isinstance(row, dict)
            }
            live.discard("")
            if live and key not in live:
                return True
    except Exception:
        pass
    try:
        from interview_mux.media_ip_cta import (
            is_editorial_exclude_reason,
            never_touch_segment_ids,
        )

        if key in never_touch_segment_ids(ctx):
            return True
        if not ignore_selection_editorial:
            rats = (
                selection.get("exclude_rationales")
                if isinstance(selection.get("exclude_rationales"), dict)
                else {}
            )
            if is_editorial_exclude_reason(str((rats or {}).get(key) or "")):
                return True
            for row in selection.get("excluded_segment_ids") or []:
                if isinstance(row, dict):
                    if str(row.get("segment_id") or "") != key:
                        continue
                    if is_editorial_exclude_reason(str(row.get("reason") or "")):
                        return True
                elif str(row or "") == key and is_editorial_exclude_reason(
                    str((rats or {}).get(key) or "")
                ):
                    return True
    except Exception:
        pass
    try:
        from interview_mux.homunculus.values import should_hard_omit_cta

        text = ""
        if ctx.artifact_exists("segments/manifest.json"):
            man = ctx.read_json("segments/manifest.json")
            for row in (man.get("segments") or []) if isinstance(man, dict) else []:
                if isinstance(row, dict) and str(row.get("segment_id") or "") == key:
                    text = str(row.get("text") or "")
                    break
        if text and should_hard_omit_cta(text):
            return True
    except Exception:
        pass
    try:
        from interview_mux.playability import is_unplayable_for_primary_impact

        return is_unplayable_for_primary_impact(ctx, sid, selection)
    except Exception:
        return key in blank_excl

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

    blank_excl = _excluded_blank_ids(selection)
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
                    if sid not in excluded_ids:
                        continue
                    if _impact_source_is_unenforceable(
                        ctx, sid, blank_excl=blank_excl, selection=selection
                    ):
                        continue
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


def _segment_start_ms(ctx: RunContext, sid: str) -> int:
    """Best-effort source start for chronological restore placement."""
    try:
        from interview_mux.playability import segment_span_ms

        span = segment_span_ms(ctx, sid)
        if span is not None:
            return int(span[0])
    except Exception:
        pass
    try:
        if ctx.artifact_exists("segments/boundaries.json"):
            doc = ctx.read_json("segments/boundaries.json")
            for row in doc.get("boundaries") or []:
                if isinstance(row, dict) and str(row.get("segment_id") or "") == sid:
                    return int(row.get("start_ms") or 0)
    except Exception:
        pass
    return 10**12


def _merge_restored_in_tape_order(
    ctx: RunContext, ordered: list[str], restored: list[str]
) -> list[str]:
    """Insert restored ids by source start_ms among existing order (no full resort).

    Appending at the end caused mid_arc_reverse_jump (exec_13198: …seg_070→seg_012).
    """
    need = [s for s in restored if s and s not in ordered]
    if not need:
        return list(ordered)
    result = list(ordered)
    for sid in sorted(need, key=lambda s: (_segment_start_ms(ctx, s), s)):
        start = _segment_start_ms(ctx, sid)
        insert_at = len(result)
        for i, other in enumerate(result):
            if _segment_start_ms(ctx, other) > start:
                insert_at = i
                break
        result.insert(insert_at, sid)
    return result


def primary_impact_segment_ids(ctx: RunContext) -> set[str]:
    """All source_segment_ids named on gap_framing_plan impact_blocks."""
    plan = load_gap_framing_plan(ctx)
    if not plan:
        return set()
    out: set[str] = set()
    for act in plan.get("acts") or []:
        if not isinstance(act, dict):
            continue
        for block in act.get("impact_blocks") or []:
            if not isinstance(block, dict):
                continue
            out.update(str(s) for s in (block.get("source_segment_ids") or []) if s)
    return out


def enforceable_primary_impact_ids(
    ctx: RunContext,
    selection: dict[str, Any] | None = None,
    *,
    for_restore: bool = False,
) -> set[str]:
    """Playable non-CTA primary-impact ids that must stay on-air (S2).

    ``for_restore=True`` ignores selection editorial exclude stamps so CTA/omit
    debt can be healed; never_touch / blank / hard-omit tape still skip.
    """
    cfg = gap_framing_cfg()
    if not cfg.get("never_exclude_primary_impact", True):
        return set()
    sel = selection if isinstance(selection, dict) else {}
    blank_excl = _excluded_blank_ids(sel)
    keep: set[str] = set()
    for sid in primary_impact_segment_ids(ctx):
        if _impact_source_is_unenforceable(
            ctx,
            sid,
            blank_excl=blank_excl,
            selection=sel,
            ignore_selection_editorial=for_restore,
        ):
            continue
        keep.add(sid)
    return keep


def inject_ranking_lattice_keeps(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    stage: str = "full_master_ranking",
) -> dict[str, Any]:
    """Put enforceable primary-impact + hard_keeps into ordered before CTA/finalize.

    FMR S2: membership floor before omit passes so lattice debt is not reintroduced.
    """
    out = dict(selection)
    need: list[str] = []
    need.extend(sorted(enforceable_primary_impact_ids(ctx, out, for_restore=True)))
    try:
        from interview_mux.hard_keep import hard_keep_segment_ids

        need.extend(sorted(str(s) for s in hard_keep_segment_ids(ctx) if s))
    except Exception:
        pass
    try:
        if ctx.artifact_exists("segments/manifest.json"):
            man = ctx.read_json("segments/manifest.json")
            live = {
                str(row.get("segment_id") or "")
                for row in (man.get("segments") or [])
                if isinstance(row, dict) and row.get("segment_id")
            }
            if live:
                need = [s for s in need if s in live]
    except Exception:
        pass
    # De-dupe preserving order.
    seen: set[str] = set()
    uniq: list[str] = []
    for sid in need:
        if sid and sid not in seen:
            seen.add(sid)
            uniq.append(sid)
    if not uniq:
        return out
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    missing = [s for s in uniq if s not in set(ordered)]
    if missing:
        out["ordered_segment_ids"] = _merge_restored_in_tape_order(ctx, ordered, missing)
        excl_raw = list(out.get("excluded_segment_ids") or [])
        kept_excl: list[Any] = []
        miss_set = set(missing)
        for row in excl_raw:
            sid = ""
            if isinstance(row, dict):
                sid = str(row.get("segment_id") or "")
            elif isinstance(row, str):
                sid = row
            if sid and sid in miss_set:
                continue
            kept_excl.append(row)
        out["excluded_segment_ids"] = kept_excl
        rats = out.get("exclude_rationales")
        if isinstance(rats, dict):
            for sid in missing:
                rats.pop(sid, None)
            out["exclude_rationales"] = rats
        try:
            ctx.log(
                "ranking_lattice_keeps: injected "
                f"{', '.join(missing[:8])}",
                level="info",
                stage=stage,
            )
        except Exception:
            pass
    try:
        from interview_mux.hard_keep import enforce_hard_keeps

        out = enforce_hard_keeps(ctx, out)
    except Exception:
        pass
    return out


def restore_enforceable_primary_impact_natives(
    ctx: RunContext,
    before_ordered: list[str],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Re-admit enforceable primary-impact ids CTA prune removed (S2)."""
    out = dict(after) if isinstance(after, dict) else {}
    keep = enforceable_primary_impact_ids(ctx, out, for_restore=True)
    before_set = {str(s) for s in before_ordered if s}
    keep &= before_set
    if not keep:
        return out
    after_ids = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    if keep <= set(after_ids):
        return out
    restored = [sid for sid in before_ordered if sid in keep or sid in set(after_ids)]
    have = set(restored)
    for sid in after_ids:
        if sid not in have:
            restored.append(sid)
            have.add(sid)
    out["ordered_segment_ids"] = restored
    keep_excl: list[Any] = []
    for row in out.get("excluded_segment_ids") or []:
        sid = str(row.get("segment_id") if isinstance(row, dict) else row or "").strip()
        if sid and sid in keep:
            continue
        keep_excl.append(row)
    out["excluded_segment_ids"] = keep_excl
    rationales = out.get("exclude_rationales")
    if isinstance(rationales, dict):
        for sid in keep:
            rationales.pop(sid, None)
        out["exclude_rationales"] = rationales
    try:
        ctx.log(
            "cta_omit_refused_primary_impact: kept "
            f"{sorted(keep)[:12]} (never_exclude_primary_impact)",
            level="warning",
            stage="full_master_ranking",
            detail={"kept": sorted(keep)[:24]},
        )
    except Exception:
        pass
    return out


def enforce_framing_ranking(ctx: RunContext, selection: dict[str, Any]) -> dict[str, Any]:
    """Apply deterministic guards; auto-heal primary-impact exclusions when possible."""
    out = dict(selection)
    cfg = gap_framing_cfg()
    if cfg.get("never_exclude_primary_impact", True):
        primary_ids = primary_impact_segment_ids(ctx)
        blank_excl = _excluded_blank_ids(out)
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
                if (
                    sid
                    and sid in primary_ids
                    and not _impact_source_is_unenforceable(
                        ctx,
                        sid,
                        blank_excl=blank_excl,
                        selection=out,
                        ignore_selection_editorial=True,
                    )
                ):
                    restored.append(sid)
                    continue
                kept_excl.append(row)
            if restored:
                out["excluded_segment_ids"] = kept_excl
                ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
                out["ordered_segment_ids"] = _merge_restored_in_tape_order(
                    ctx, ordered, restored
                )
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
