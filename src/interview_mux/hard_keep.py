"""Union of segment IDs that ranking/pack/junction/fuse must never drop."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def hard_keep_segment_ids(ctx: RunContext) -> set[str]:
    ids: set[str] = set()
    try:
        from interview_mux.gap_framing import load_gap_framing_plan

        plan = load_gap_framing_plan(ctx)
        if plan:
            for act in plan.get("acts") or []:
                if not isinstance(act, dict):
                    continue
                for block in act.get("impact_blocks") or []:
                    if not isinstance(block, dict):
                        continue
                    ids.update(str(s) for s in (block.get("source_segment_ids") or []) if s)
    except Exception:
        pass
    try:
        from interview_mux.stages.audio_probes import authoritative_must_keep_ids

        ids |= authoritative_must_keep_ids(ctx)
    except Exception:
        pass
    if ctx.artifact_exists("understanding/ideal_cuts.json"):
        try:
            cuts = ctx.read_json("understanding/ideal_cuts.json")
            if isinstance(cuts, dict):
                ids.update(str(s) for s in (cuts.get("must_keep_segment_ids") or []) if s)
                for row in cuts.get("cuts") or []:
                    if isinstance(row, dict) and row.get("must_keep"):
                        sid = str(row.get("segment_id") or row.get("cut_id") or "")
                        if sid:
                            ids.add(sid)
        except Exception:
            pass
    if ctx.artifact_exists("understanding/talking_points.json"):
        try:
            tps = ctx.read_json("understanding/talking_points.json")
            rows = tps.get("talking_points") if isinstance(tps, dict) else tps
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                if not row.get("must_keep"):
                    continue
                for key in ("segment_id", "cut_id", "source_segment_id"):
                    sid = str(row.get(key) or "")
                    if sid:
                        ids.add(sid)
                ids.update(str(s) for s in (row.get("segment_ids") or []) if s)
        except Exception:
            pass
    return {s for s in ids if s}


def enforce_hard_keeps(ctx: RunContext, selection: dict[str, Any]) -> dict[str, Any]:
    """Restore hard-keeps into ordered even if they vanished from excluded too."""
    out = dict(selection)
    keeps = hard_keep_segment_ids(ctx)
    if not keeps:
        return out
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    seen = set(ordered)
    restored: list[str] = []
    for sid in sorted(keeps):
        if sid not in seen:
            ordered.append(sid)
            seen.add(sid)
            restored.append(sid)
    excl_raw = list(out.get("excluded_segment_ids") or [])
    kept_excl: list[Any] = []
    for row in excl_raw:
        sid = ""
        if isinstance(row, dict):
            sid = str(row.get("segment_id") or "")
        elif isinstance(row, str):
            sid = row
        if sid and sid in keeps:
            continue
        kept_excl.append(row)
    out["ordered_segment_ids"] = ordered
    out["excluded_segment_ids"] = kept_excl
    if restored:
        ctx.log(
            "hard_keep: restored " + ", ".join(restored[:8]),
            level="info",
            stage="full_master_ranking",
        )
    return out
