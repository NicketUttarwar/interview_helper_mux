"""Keep episode orientation; suppress/retarget a duplicate opening layup on the first native."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _first_ordered_id(ctx: RunContext) -> str:
    for rel, key in (
        ("master/selection.json", "ordered_segment_ids"),
        ("mastering/mastering_plan.json", "ordered_segment_ids"),
    ):
        if not ctx.artifact_exists(rel):
            continue
        doc = ctx.read_json(rel)
        if not isinstance(doc, dict):
            continue
        ordered = doc.get(key) or doc.get("selection", {}).get("ordered_segment_ids")
        if isinstance(ordered, list) and ordered:
            return str(ordered[0])
    if ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
        segs = (man or {}).get("segments") if isinstance(man, dict) else None
        if isinstance(segs, list) and segs:
            first = segs[0]
            if isinstance(first, dict) and first.get("segment_id"):
                return str(first["segment_id"])
    return ""


def _line_target(line: dict[str, Any]) -> str:
    return str(
        line.get("targets_segment_id")
        or line.get("target_segment_id")
        or line.get("before_segment_id")
        or ""
    )


def _is_opening_layup(line: dict[str, Any], first_id: str) -> bool:
    if not isinstance(line, dict) or not first_id:
        return False
    from interview_mux.opening_orientation import is_episode_orientation

    if is_episode_orientation(line):
        return False
    if line.get("skipped_optional") or line.get("skip") or line.get("air_script_omit"):
        return False
    origin = str(line.get("origin") or line.get("owner_stage") or "").lower()
    line_id = str(line.get("line_id") or "").lower()
    placement = str(line.get("placement") or "before").lower()
    if placement not in {"", "before"}:
        return False
    if _line_target(line) != first_id:
        return False
    if "layup" in origin or "layup" in line_id or origin in {"nugget_layup", "nugget_layup_compose"}:
        return True
    # Prefaces that are not orientation still collide with the opening seat.
    category = str(line.get("line_category") or "").lower()
    return category in {"layup", "nugget_layup", "opening_layup"}


def suppress_opening_layup_when_orientation_owns_slot(ctx: RunContext) -> list[str]:
    """Keep orientation on the first native; skip duplicate opening layups.

    Returns line_ids that were suppressed. No-op when orientation is absent.
    """
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    gap = ctx.read_json("understanding/gap_report.json")
    if not isinstance(gap, dict):
        return []
    lines = gap.get("interviewer_lines")
    if not isinstance(lines, list):
        return []
    from interview_mux.opening_orientation import is_episode_orientation

    has_orientation = any(
        isinstance(ln, dict) and is_episode_orientation(ln) and not ln.get("skipped_optional")
        for ln in lines
    )
    if not has_orientation:
        return []
    first_id = _first_ordered_id(ctx)
    if not first_id:
        return []
    changed: list[str] = []
    for line in lines:
        if not _is_opening_layup(line, first_id):
            continue
        line_id = str(line.get("line_id") or "")
        line["skipped_optional"] = True
        line["air_script_omit"] = True
        line["skip"] = True
        line["skip_reason_code"] = "opening_orientation_owns_target"
        line["compensating_path"] = "opening_orientation"
        notes = list(line.get("omit_notes") or [])
        note = "opening_adjacency: keep orientation; suppress duplicate opening layup"
        if note not in notes:
            notes.append(note)
        line["omit_notes"] = notes
        changed.append(line_id or _line_target(line))
    if not changed:
        return []
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(ctx.path("understanding/gap_report.json"), gap)
    if ctx.artifact_exists("understanding/nugget_layup_plan.json"):
        try:
            from interview_mux.nugget_layup import PLAN_REL, stamp_typed_skip

            plan = ctx.read_json(PLAN_REL)
            if isinstance(plan, dict):
                plan_changed = False
                for row in plan.get("layups") or []:
                    if not isinstance(row, dict) or row.get("skip"):
                        continue
                    if str(row.get("target_segment_id") or "") != first_id:
                        continue
                    stamp_typed_skip(
                        row,
                        reason_code="opening_orientation_owns_target",
                        evidence_refs=[
                            f"target:{first_id}",
                            "opening_orientation:owns_before_slot",
                        ],
                        compensating_path="opening_orientation",
                        revisit_if=["orientation_disabled", "opening_slot_freed"],
                        decision_confidence=0.95,
                        owner_stage="opening_adjacency_repair",
                    )
                    plan_changed = True
                if plan_changed:
                    fs_write_json(ctx.path(PLAN_REL), plan)
        except Exception:
            pass
    try:
        ctx.log(
            f"opening_adjacency: suppressed {len(changed)} duplicate opening layup(s)",
            level="info",
            stage="sound_design_vo_finalize",
            detail={"line_ids": changed[:8], "keep": "episode_orientation"},
        )
    except Exception:
        pass
    return changed
