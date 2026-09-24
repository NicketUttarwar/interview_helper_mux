"""Keep episode orientation; suppress/retarget a duplicate opening layup on the first native."""

from __future__ import annotations

import re
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
    try:
        from interview_mux.seat_authority import gate_seat_mutation

        if not gate_seat_mutation(
            ctx,
            reason="opening_adjacency_suppress_duplicate",
            symptoms=["opening_adjacency"],
        ):
            return []
    except Exception:
        try:
            from interview_mux.seat_authority import soft_freeze_active, hard_freeze_active

            if soft_freeze_active(ctx) or hard_freeze_active(ctx):
                return []
        except Exception:
            return []
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
    from interview_mux.seat_authority import persist_frozen_seat_doc_verified

    result = persist_frozen_seat_doc_verified(
        ctx,
        "understanding/gap_report.json",
        gap,
        reason="opening_adjacency_suppress_duplicate",
        touched_line_ids=list(changed),
    )
    if not result.get("ok"):
        try:
            ctx.log(
                f"opening_adjacency: suppress persist not verified "
                f"({result.get('error') or result.get('skipped') or 'fail'})",
                level="warning",
                stage="opening_adjacency_repair",
            )
        except Exception:
            pass
        return []
    if ctx.artifact_exists("understanding/nugget_layup_plan.json"):
        try:
            from interview_mux.nugget_layup import PLAN_REL, stamp_typed_skip
            from interview_mux.artifact_sanitize.one_writer import (
                commit_nugget_layup_plan_doc,
            )

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
                    commit_nugget_layup_plan_doc(
                        ctx,
                        plan,
                        skip_handoff=True,
                        reason="opening_adjacency_suppress_duplicate",
                    )
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


_ORPHAN_OPENING_LINE_IDS = ("vo_preface_opening", "vo_preface_episode_orientation")


def drop_orphan_opening_vo_when_native_orients(ctx: RunContext) -> list[str]:
    """When native open already intros, drop leftover opening WAV/lines.

    Orientation omit leaves vo_preface_opening.wav on disk; EDL/G1 still see it
    as competing with the first native. Keep the omit; remove the duplicate.

    Cluster C: refuse delete under HEARD_KEEP / HOLLOW_MINT (disposition SSOT).
    """
    try:
        from interview_mux.hosted_vo_authority import drop_orphan_orientation_allowed

        gap_probe = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else {}
        )
        if isinstance(gap_probe, dict) and not drop_orphan_orientation_allowed(
            ctx, gap_probe
        ):
            return []
    except Exception:
        pass
    try:
        from interview_mux.seat_authority import gate_seat_mutation

        if not gate_seat_mutation(
            ctx,
            reason="opening_adjacency_drop_orphan",
            symptoms=["opening_adjacency", "wav_delete"],
        ):
            return []
    except Exception:
        try:
            from interview_mux.seat_authority import soft_freeze_active, hard_freeze_active

            if soft_freeze_active(ctx) or hard_freeze_active(ctx):
                return []
        except Exception:
            return []
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    gap = ctx.read_json("understanding/gap_report.json")
    if not isinstance(gap, dict):
        return []
    from interview_mux.opening_orientation import orientation_omitted

    if not orientation_omitted(gap):
        return []
    dropped: list[str] = []
    lines = gap.get("interviewer_lines")
    if isinstance(lines, list):
        kept: list[Any] = []
        for line in lines:
            if not isinstance(line, dict):
                kept.append(line)
                continue
            lid = str(line.get("line_id") or "").lower()
            if lid in _ORPHAN_OPENING_LINE_IDS and not line.get("skipped_optional"):
                line = dict(line)
                line["skipped_optional"] = True
                line["air_script_omit"] = True
                line["skip"] = True
                line["skip_reason_code"] = "native_open_self_orients"
                dropped.append(str(line.get("line_id") or lid))
            kept.append(line)
        if dropped:
            gap["interviewer_lines"] = kept
            from interview_mux.seat_authority import persist_frozen_seat_doc_verified

            result = persist_frozen_seat_doc_verified(
                ctx,
                "understanding/gap_report.json",
                gap,
                reason="opening_adjacency_drop_orphan",
                touched_line_ids=list(dropped),
            )
            if not result.get("ok"):
                try:
                    ctx.log(
                        f"opening_adjacency: drop_orphan persist not verified "
                        f"({result.get('error') or result.get('skipped') or 'fail'})",
                        level="warning",
                        stage="opening_adjacency_repair",
                    )
                except Exception:
                    pass
                return []
    pickup = ctx.final_path("vo_pickup")
    for lid in _ORPHAN_OPENING_LINE_IDS:
        for folder in (pickup, pickup / "synthesized"):
            wav = folder / f"{lid}.wav"
            if wav.is_file():
                wav.unlink()
                dropped.append(wav.name)
    if dropped:
        try:
            ctx.log(
                f"opening_adjacency: dropped orphan opening VO {dropped[:6]}",
                level="info",
                stage="sound_design_vo_finalize",
            )
        except Exception:
            pass
    return dropped


_LATE_INTRO_RE = re.compile(
    r"\b(?:"
    r"let['’]?s welcome|"
    r"welcome (?:to|back)(?:\s+the\s+show)?|"
    r"hoping to hear|"
    r"on the show today|"
    r"joining (?:us|me)|"
    r"what are you hoping to hear"
    r")\b",
    flags=re.IGNORECASE,
)
_RECUT_FRAG_RE = re.compile(r"^(seg_\d+)[a-z]+$")


def _segment_text(ctx: RunContext, sid: str) -> str:
    if not sid or not ctx.artifact_exists("segments/manifest.json"):
        return ""
    man = ctx.read_json("segments/manifest.json")
    for row in (man.get("segments") or []) if isinstance(man, dict) else []:
        if isinstance(row, dict) and str(row.get("segment_id") or "") == sid:
            return str(row.get("text") or row.get("text_excerpt") or "")
    return ""


def drop_late_intro_reset_from_selection(ctx: RunContext) -> list[str]:
    """Drop recut welcome/intro fragments that air after the body has started.

    A native cold-open already greets the guest. Replaying “what is X / let’s
    welcome” mid-arc is a late opening-style reset, not a new chapter.
    """
    if not ctx.artifact_exists("master/selection.json"):
        return []
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return []
    ordered = [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]
    if len(ordered) < 4:
        return []
    introish = {sid: bool(_LATE_INTRO_RE.search(_segment_text(ctx, sid))) for sid in ordered}
    drop: list[str] = []
    seen_body = False
    i = 0
    while i < len(ordered):
        sid = ordered[i]
        if not introish.get(sid):
            # Recut children of the cold-open parent are still the open, even
            # when a bio/definition slice does not match the welcome regex.
            # Otherwise "hoping to hear" on seg_001k after seg_001d looks like
            # a late reset and the whole opening recut is dropped.
            if not seen_body and _RECUT_FRAG_RE.match(sid):
                i += 1
                continue
            seen_body = True
            i += 1
            continue
        if seen_body:
            stem_m = _RECUT_FRAG_RE.match(sid)
            stem = stem_m.group(1) if stem_m else ""
            k = i
            while k > 0 and stem and _RECUT_FRAG_RE.match(ordered[k - 1] or "") and ordered[k - 1].startswith(stem):
                k -= 1
            j = i
            while j < len(ordered):
                cur = ordered[j]
                if introish.get(cur) or (stem and _RECUT_FRAG_RE.match(cur or "") and cur.startswith(stem)):
                    j += 1
                    continue
                break
            drop.extend(ordered[k:j])
            i = j
            continue
        i += 1
    if not drop:
        return []
    drop_set = set(drop)
    sel["ordered_segment_ids"] = [s for s in ordered if s not in drop_set]
    excl = list(sel.get("excluded_segment_ids") or [])
    have = {
        str(r.get("segment_id") if isinstance(r, dict) else r)
        for r in excl
    }
    for sid in drop:
        if sid not in have:
            excl.append({"segment_id": sid, "reason": "late_intro_reset"})
            have.add(sid)
    sel["excluded_segment_ids"] = excl
    keep = set(sel["ordered_segment_ids"])
    for ch in sel.get("chapters") or []:
        if isinstance(ch, dict):
            ch["segment_ids"] = [
                str(x) for x in (ch.get("segment_ids") or []) if str(x) in keep
            ]
    from interview_mux.artifact_repairs import reconcile_ordered_vs_excluded

    sel = reconcile_ordered_vs_excluded(sel)
    from interview_mux.air_order_boundary import commit_selection_mutation
    from interview_mux.order_hash import bump_order_lock

    sel = bump_order_lock(sel, source="opening_adjacency_repair:late_intro")
    commit_selection_mutation(
        ctx,
        sel,
        producer="opening_adjacency_repair",
        stage_key="opening_adjacency_repair",
        checkpoint_mode="repair",
        skip_handoff=True,
    )
    try:
        ctx.log(
            f"late_intro_reset: dropped {drop[:12]}",
            level="warning",
            stage="edl_narrative_audit",
        )
    except Exception:
        pass
    return drop


def _segment_start_ms(ctx: RunContext, sid: str) -> int | None:
    if not sid or not ctx.artifact_exists("segments/manifest.json"):
        return None
    man = ctx.read_json("segments/manifest.json")
    for row in (man.get("segments") or []) if isinstance(man, dict) else []:
        if isinstance(row, dict) and str(row.get("segment_id") or "") == sid:
            try:
                return int(row.get("start_ms") or 0)
            except (TypeError, ValueError):
                return None
    return None


def drop_post_coda_reverse_jump_from_selection(ctx: RunContext) -> list[str]:
    """Drop early-tape leftovers parked after a late-tape coda.

    CTA omit / order reconcile can leave early sampling clips (low ``start_ms``)
    after the episode has already reached its closing minutes. That reverse
    jump fails narrative audit and cannot be healed by recomposing VO.
    Hard-keeps stay on air.
    """
    if not ctx.artifact_exists("master/selection.json"):
        return []
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return []
    ordered = [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]
    if len(ordered) < 6:
        return []
    starts = {sid: _segment_start_ms(ctx, sid) for sid in ordered}
    if any(v is None for v in starts.values()):
        return []
    peak_ms = max(int(v or 0) for v in starts.values())
    if peak_ms < 60_000:
        return []
    coda_end = 0
    for i, sid in enumerate(ordered):
        if int(starts.get(sid) or 0) >= int(peak_ms * 0.80):
            coda_end = i
    if coda_end <= 0 or coda_end >= len(ordered) - 1:
        return []
    keeps: set[str] = set()
    try:
        from interview_mux.hard_keep import hard_keep_segment_ids

        keeps = hard_keep_segment_ids(ctx)
    except Exception:
        keeps = set()
    drop: list[str] = []
    early_cut = int(peak_ms * 0.35)
    for sid in ordered[coda_end + 1 :]:
        if sid in keeps:
            break
        if int(starts.get(sid) or 0) >= early_cut:
            break
        drop.append(sid)
    if not drop:
        return []
    drop_set = set(drop)
    sel["ordered_segment_ids"] = [s for s in ordered if s not in drop_set]
    excl = list(sel.get("excluded_segment_ids") or [])
    have = {
        str(r.get("segment_id") if isinstance(r, dict) else r)
        for r in excl
    }
    for sid in drop:
        if sid not in have:
            excl.append({"segment_id": sid, "reason": "post_coda_reverse_jump"})
            have.add(sid)
    sel["excluded_segment_ids"] = excl
    keep = set(sel["ordered_segment_ids"])
    for ch in sel.get("chapters") or []:
        if isinstance(ch, dict):
            ch["segment_ids"] = [
                str(x) for x in (ch.get("segment_ids") or []) if str(x) in keep
            ]
    from interview_mux.artifact_repairs import reconcile_ordered_vs_excluded
    from interview_mux.order_hash import bump_order_lock

    sel = reconcile_ordered_vs_excluded(sel)
    sel = bump_order_lock(sel, source="post_coda_reverse_jump")
    from interview_mux.air_order_boundary import commit_selection_mutation

    commit_selection_mutation(
        ctx,
        sel,
        producer="opening_adjacency_repair",
        stage_key="opening_adjacency_repair",
        checkpoint_mode="repair",
        skip_handoff=True,
    )
    try:
        ctx.log(
            f"post_coda_reverse_jump: dropped {drop[:12]}",
            level="warning",
            stage="edl_narrative_audit",
        )
    except Exception:
        pass
    return drop
