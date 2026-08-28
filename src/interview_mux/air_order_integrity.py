"""Tape-time air-order integrity: detect reverse jumps and late opening clusters."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.air_order_policy import (
    DEFAULT_OPENING_AIR_SLOTS,
    DEFAULT_OPENING_BODY_START_INDEX,
    DEFAULT_OPENING_WINDOW_MS,
    DEFAULT_REVERSE_JUMP_MARGIN_MS,
    policy_value,
    resolve_air_order_policy,
)
from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.selection_order_repair import (
    _parent_seg_id,
    resolved_source_start_ms,
)

_RECUT_FRAG_RE = re.compile(r"^(seg_\d+)([a-z]+)$", re.IGNORECASE)

INTEGRITY_REL = "master/air_order_integrity.json"
OPERATOR_LOG_REL = "operator/air_order_integrity.log.jsonl"


def air_order_integrity_cfg() -> dict[str, Any]:
    mastering = merged_config().get("mastering") or {}
    cfg = mastering.get("air_order_integrity") if isinstance(mastering, dict) else None
    return dict(cfg) if isinstance(cfg, dict) else {}


def _cfg_int(key: str, default: int) -> int:
    try:
        return int(air_order_integrity_cfg().get(key, default))
    except (TypeError, ValueError):
        return default


def _cfg_bool(key: str, default: bool) -> bool:
    val = air_order_integrity_cfg().get(key, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _resolve_policy(
    ctx: RunContext | None,
    policy: dict[str, Any] | None,
    *,
    selection: dict[str, Any] | None = None,
    starts: dict[str, int] | None = None,
) -> dict[str, Any] | None:
    if policy is not None:
        return policy
    if ctx is not None:
        return resolve_air_order_policy(ctx, selection=selection, starts=starts)
    return None


def opening_window_ms(
    ctx: RunContext | None = None,
    policy: dict[str, Any] | None = None,
) -> int:
    pol = _resolve_policy(ctx, policy)
    if pol is not None:
        return policy_value(pol, "opening_window_ms", DEFAULT_OPENING_WINDOW_MS)
    return _cfg_int("opening_window_ms", DEFAULT_OPENING_WINDOW_MS)


def opening_air_slots(
    ctx: RunContext | None = None,
    policy: dict[str, Any] | None = None,
) -> int:
    pol = _resolve_policy(ctx, policy)
    if pol is not None:
        return policy_value(pol, "opening_air_slots", DEFAULT_OPENING_AIR_SLOTS)
    return _cfg_int("opening_air_slots", DEFAULT_OPENING_AIR_SLOTS)


def opening_body_start_index(
    ctx: RunContext | None = None,
    policy: dict[str, Any] | None = None,
) -> int:
    pol = _resolve_policy(ctx, policy)
    if pol is not None:
        return policy_value(pol, "opening_body_start_index", DEFAULT_OPENING_BODY_START_INDEX)
    return _cfg_int("opening_body_start_index", DEFAULT_OPENING_BODY_START_INDEX)


def reverse_jump_margin_ms(
    ctx: RunContext | None = None,
    policy: dict[str, Any] | None = None,
) -> int:
    pol = _resolve_policy(ctx, policy)
    if pol is not None:
        return policy_value(pol, "reverse_jump_margin_ms", DEFAULT_REVERSE_JUMP_MARGIN_MS)
    return _cfg_int("reverse_jump_margin_ms", DEFAULT_REVERSE_JUMP_MARGIN_MS)


def count_opening_by_family(policy: dict[str, Any] | None) -> bool:
    if policy is None:
        return _cfg_bool("count_opening_by_family", True)
    val = policy.get("count_opening_by_family")
    if isinstance(val, bool):
        return val
    return _cfg_bool("count_opening_by_family", True)


def block_ranking_on_critical() -> bool:
    return _cfg_bool("block_ranking_on_critical", False)


def invalidate_mix_on_order_change() -> bool:
    return _cfg_bool("invalidate_mix_on_order_change", False)


def block_publish_on_critical() -> bool:
    return _cfg_bool("block_publish_on_critical", True)


def invalidate_edl_on_order_change() -> bool:
    return _cfg_bool("invalidate_edl_on_order_change", True)


def invalidate_transitions_on_order_change() -> bool:
    return _cfg_bool("invalidate_transitions_on_order_change", True)


def resolved_segment_starts(ctx: RunContext) -> dict[str, int]:
    starts: dict[str, int] = {}
    for rel in ("segments/boundaries.json", "segments/segments.json", "segments/manifest.json"):
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        rows: list[Any] = []
        if isinstance(doc, dict):
            rows = list(doc.get("boundaries") or doc.get("segments") or [])
        for row in rows:
            if not isinstance(row, dict) or not row.get("segment_id"):
                continue
            try:
                starts[str(row["segment_id"])] = int(
                    row.get("start_ms") or row.get("source_start_ms") or 0
                )
            except (TypeError, ValueError):
                continue
    return starts


def letter_split_family(sid: str, ordered: list[str] | None = None) -> list[str]:
    """Parent + all letter-split siblings present in ordered (or just parent+sid)."""
    parent = _parent_seg_id(sid)
    key = str(sid or "").strip()
    if not key:
        return []
    if ordered:
        stem = parent
        out = [s for s in ordered if s == stem or (_RECUT_FRAG_RE.match(s or "") and s.startswith(stem))]
        if out:
            return out
    if key == parent:
        return [key]
    if _RECUT_FRAG_RE.match(key):
        return [parent, key]
    return [key]


def pair_source_gap_ms(
    after_id: str,
    before_id: str,
    starts: dict[str, int] | None,
) -> int | None:
    if not starts:
        return None
    a = resolved_source_start_ms(after_id, starts)
    b = resolved_source_start_ms(before_id, starts)
    if a is None or b is None:
        return None
    return int(b) - int(a)


def opening_tape_segment_ids(
    ordered: list[str],
    starts: dict[str, int] | None,
    *,
    window_ms: int | None = None,
    policy: dict[str, Any] | None = None,
    ctx: RunContext | None = None,
) -> set[str]:
    window = (
        window_ms
        if window_ms is not None
        else opening_window_ms(ctx=ctx, policy=policy)
    )
    out: set[str] = set()
    if not starts:
        return out
    for sid in ordered:
        start = resolved_source_start_ms(sid, starts)
        if start is not None and int(start) < window:
            out.add(str(sid))
    return out


def _guest_first_open_established(
    ordered: list[str],
    starts: dict[str, int],
    *,
    policy: dict[str, Any] | None = None,
    ctx: RunContext | None = None,
) -> bool:
    """True when the episode opens with non-host-intro material but host intro airs later."""
    if not ordered or not starts or len(ordered) < 2:
        return False
    window = opening_window_ms(ctx=ctx, policy=policy)
    opening_parents: dict[str, int] = {}
    for sid in ordered:
        start = resolved_source_start_ms(sid, starts)
        if start is None or int(start) >= window:
            continue
        parent = _parent_seg_id(sid)
        opening_parents[parent] = min(int(opening_parents.get(parent, start)), int(start))
    if not opening_parents:
        return False
    host_parent = min(opening_parents, key=lambda p: opening_parents[p])
    first_parent = _parent_seg_id(ordered[0])
    if first_parent == host_parent:
        return False
    return any(_parent_seg_id(s) == host_parent and idx > 0 for idx, s in enumerate(ordered))


def reverse_tape_jump_violations(
    ctx: RunContext | None,
    ordered: list[str],
    *,
    starts: dict[str, int] | None = None,
    reorder_pairs: set[tuple[str, str]] | None = None,
    policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if starts is None and ctx is not None:
        starts = resolved_segment_starts(ctx)
    if not starts:
        return []
    margin = reverse_jump_margin_ms(ctx=ctx, policy=policy)
    declared = reorder_pairs or set()
    violations: list[dict[str, Any]] = []
    for i in range(len(ordered) - 1):
        after_id = str(ordered[i])
        before_id = str(ordered[i + 1])
        if (after_id, before_id) in declared:
            continue
        gap = pair_source_gap_ms(after_id, before_id, starts)
        if gap is None or gap >= -margin:
            continue
        violations.append(
            {
                "code": "mid_arc_reverse_jump",
                "severity": "critical",
                "after_segment_id": after_id,
                "before_segment_id": before_id,
                "source_gap_ms": gap,
                "air_index": i + 1,
                "message": (
                    f"Reverse tape jump: {after_id} -> {before_id} "
                    f"(source_gap_ms={gap})"
                ),
            }
        )
    return violations


def _opening_family_first_indices(
    ordered: list[str],
    opening_ids: set[str],
) -> list[tuple[str, int, list[str]]]:
    """Return [(parent_id, first_air_index, fragment_ids)] sorted by first index."""
    by_parent: dict[str, list[tuple[int, str]]] = {}
    for idx, sid in enumerate(ordered):
        if sid not in opening_ids:
            continue
        parent = _parent_seg_id(sid)
        by_parent.setdefault(parent, []).append((idx, sid))
    out: list[tuple[str, int, list[str]]] = []
    for parent, rows in by_parent.items():
        rows.sort(key=lambda r: r[0])
        first_idx = rows[0][0]
        frags = [sid for _, sid in rows]
        out.append((parent, first_idx, frags))
    out.sort(key=lambda row: row[1])
    return out


def late_opening_cluster_violations(
    ctx: RunContext | None,
    ordered: list[str],
    *,
    starts: dict[str, int] | None = None,
    policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if starts is None and ctx is not None:
        starts = resolved_segment_starts(ctx)
    if not starts or not ordered:
        return []
    pol = _resolve_policy(ctx, policy, starts=starts)
    opening_ids = opening_tape_segment_ids(
        ordered, starts, policy=pol, ctx=ctx
    )
    if not opening_ids:
        return []
    early_slots = opening_air_slots(ctx=ctx, policy=pol)
    violations: list[dict[str, Any]] = []
    guest_first = _guest_first_open_established(
        ordered, starts, policy=pol, ctx=ctx
    )
    by_family = count_opening_by_family(pol)

    if by_family:
        families = _opening_family_first_indices(ordered, opening_ids)
        for ordinal, (parent, first_idx, frags) in enumerate(families, start=1):
            if guest_first and first_idx >= 1:
                violations.append(
                    {
                        "code": "late_opening_cluster",
                        "severity": "critical",
                        "parent_segment_id": parent,
                        "segment_ids": frags,
                        "family_first_index": first_idx,
                        "family_ordinal": ordinal,
                        "air_index": first_idx,
                        "message": (
                            f"Opening-tape cluster {frags[:4]} after guest-first open "
                            f"at index {first_idx}"
                        ),
                    }
                )
            elif not guest_first and ordinal > early_slots:
                violations.append(
                    {
                        "code": "late_opening_cluster",
                        "severity": "critical",
                        "parent_segment_id": parent,
                        "segment_ids": frags,
                        "family_first_index": first_idx,
                        "family_ordinal": ordinal,
                        "air_index": first_idx,
                        "message": (
                            f"Opening-tape cluster {frags[:4]} airs late at index {first_idx}"
                        ),
                    }
                )
        return violations

    for idx, sid in enumerate(ordered):
        if sid not in opening_ids:
            continue
        if guest_first and idx >= 1:
            family = letter_split_family(sid, ordered)
            violations.append(
                {
                    "code": "late_opening_cluster",
                    "severity": "critical",
                    "segment_ids": family,
                    "air_index": idx,
                    "message": (
                        f"Opening-tape cluster {family[:4]} after guest-first open at index {idx}"
                    ),
                }
            )
        elif not guest_first and idx >= early_slots:
            family = letter_split_family(sid, ordered)
            violations.append(
                {
                    "code": "late_opening_cluster",
                    "severity": "critical",
                    "segment_ids": family,
                    "air_index": idx,
                    "message": (
                        f"Opening-tape cluster {family[:4]} airs late at index {idx}"
                    ),
                }
            )
    # Dedupe by family stem
    seen_stems: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for v in violations:
        stem = _parent_seg_id(str((v.get("segment_ids") or [""])[0]))
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        deduped.append(v)
    return deduped


def chapter_opening_mask_violations(
    ctx: RunContext | None,
    selection: dict[str, Any],
    *,
    starts: dict[str, int] | None = None,
    policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Flag opening-tape segments assigned to late-body chapters."""
    if starts is None and ctx is not None:
        starts = resolved_segment_starts(ctx)
    if not starts:
        return []
    pol = _resolve_policy(ctx, policy, selection=selection, starts=starts)
    ordered = [str(s) for s in (selection.get("ordered_segment_ids") or []) if s]
    opening_ids = opening_tape_segment_ids(
        ordered, starts, policy=pol, ctx=ctx
    )
    if not opening_ids:
        return []
    chapters = selection.get("chapters") or []
    if not isinstance(chapters, list) or len(chapters) < 2:
        return []
    pos = {sid: idx for idx, sid in enumerate(ordered)}
    late_chapter_indices = set(range(max(0, len(chapters) // 2), len(chapters)))
    violations: list[dict[str, Any]] = []
    for ch_idx, ch in enumerate(chapters):
        if not isinstance(ch, dict) or ch_idx not in late_chapter_indices:
            continue
        members = [str(s) for s in (ch.get("segment_ids") or []) if str(s) in opening_ids]
        if not members:
            continue
        late_member = max(members, key=lambda s: pos.get(s, -1))
        if pos.get(late_member, 0) >= opening_body_start_index(ctx=ctx, policy=pol):
            violations.append(
                {
                    "code": "chapter_opening_mask",
                    "severity": "warn",
                    "chapter_id": ch.get("chapter_id"),
                    "segment_ids": members[:8],
                    "message": (
                        f"Opening-tape segments in late chapter "
                        f"{ch.get('chapter_id') or ch_idx}: {members[:4]}"
                    ),
                }
            )
    return violations


def collect_violations(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    starts: dict[str, int] | None = None,
    policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ordered = [str(s) for s in (selection.get("ordered_segment_ids") or []) if s]
    if starts is None:
        starts = resolved_segment_starts(ctx)
    pol = _resolve_policy(ctx, policy, selection=selection, starts=starts)
    reorder_pairs: set[tuple[str, str]] = set()
    if ctx.artifact_exists("understanding/reorder_bridges.json"):
        try:
            bridges = ctx.read_json("understanding/reorder_bridges.json")
            for row in (bridges.get("bridges") if isinstance(bridges, dict) else []) or []:
                if not isinstance(row, dict):
                    continue
                a = str(row.get("after_segment_id") or "")
                b = str(row.get("before_segment_id") or "")
                if a and b:
                    reorder_pairs.add((a, b))
        except Exception:
            pass
    out: list[dict[str, Any]] = []
    out.extend(
        reverse_tape_jump_violations(
            ctx, ordered, starts=starts, reorder_pairs=reorder_pairs, policy=pol
        )
    )
    out.extend(
        late_opening_cluster_violations(ctx, ordered, starts=starts, policy=pol)
    )
    out.extend(
        chapter_opening_mask_violations(
            ctx, selection, starts=starts, policy=pol
        )
    )
    return out


def _exclude_segments(
    selection: dict[str, Any],
    drop_ids: list[str],
    *,
    reason: str,
) -> dict[str, Any]:
    out = dict(selection)
    drop_set = {str(s) for s in drop_ids if s}
    if not drop_set:
        return out
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s and str(s) not in drop_set]
    out["ordered_segment_ids"] = ordered
    excl = list(out.get("excluded_segment_ids") or [])
    have = {
        str(r.get("segment_id") if isinstance(r, dict) else r)
        for r in excl
    }
    for sid in drop_ids:
        if sid in have:
            continue
        excl.append({"segment_id": sid, "reason": reason})
        have.add(sid)
    out["excluded_segment_ids"] = excl
    rationales = (
        dict(out.get("exclude_rationales") or {})
        if isinstance(out.get("exclude_rationales"), dict)
        else {}
    )
    for sid in drop_ids:
        rationales[sid] = reason
    out["exclude_rationales"] = rationales
    keep = set(ordered)
    for ch in out.get("chapters") or []:
        if isinstance(ch, dict):
            ch["segment_ids"] = [str(x) for x in (ch.get("segment_ids") or []) if str(x) in keep]
    return out


def repair_opening_tape_integrity(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    mode: str = "prepend",
    starts: dict[str, int] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply opening-tape sub-rule; return (selection, actions).

    Default ``prepend`` keeps a strong native host intro on air by moving the
    late opening-tape family to the front. ``drop_if_guest_first`` remains as an
    explicit override for callers that still want exclusion.
    """
    out = dict(selection)
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    if not ordered:
        return out, []
    if starts is None:
        starts = resolved_segment_starts(ctx)
    pol = _resolve_policy(ctx, None, selection=out, starts=starts)
    actions: list[dict[str, Any]] = []
    guest_first = _guest_first_open_established(
        ordered, starts, policy=pol, ctx=ctx
    )
    late = late_opening_cluster_violations(
        ctx, ordered, starts=starts, policy=pol
    )
    opening_ids = opening_tape_segment_ids(
        ordered, starts, policy=pol, ctx=ctx
    )
    if not late and guest_first:
        for idx, sid in enumerate(ordered):
            if sid in opening_ids and idx >= 1:
                late.append({"segment_ids": letter_split_family(sid, ordered)})
    if not late:
        return out, actions
    to_drop: list[str] = []
    for v in late:
        family = [str(s) for s in (v.get("segment_ids") or []) if s]
        if mode == "drop_if_guest_first" and guest_first:
            to_drop.extend(family)
        else:
            # Prefer native host intro at front (default); company-pitch tape may
            # follow even when topics overlap across speakers.
            rest = [s for s in ordered if s not in set(family)]
            family_sorted = sorted(
                family,
                key=lambda s: (
                    resolved_source_start_ms(s, starts) or 0,
                    ordered.index(s) if s in ordered else 0,
                ),
            )
            ordered = family_sorted + rest
            actions.append({"action": "prepend_opening_family", "ids": family_sorted[:12]})
    if to_drop:
        reason = "opening_skipped_duplicate" if guest_first else "late_intro_reset"
        out = _exclude_segments(out, to_drop, reason=reason)
        actions.append({"action": "exclude_opening_cluster", "reason": reason, "ids": to_drop[:12]})
    elif actions:
        out["ordered_segment_ids"] = ordered
        # Clear stale opening_skipped_duplicate excludes for ids we restored.
        restored = {
            sid
            for act in actions
            if act.get("action") == "prepend_opening_family"
            for sid in (act.get("ids") or [])
        }
        if restored:
            excl = []
            for row in out.get("excluded_segment_ids") or []:
                sid = str(row.get("segment_id") if isinstance(row, dict) else row)
                reason = (
                    str(row.get("reason") or "")
                    if isinstance(row, dict)
                    else str((out.get("exclude_rationales") or {}).get(sid) or "")
                )
                if sid in restored and reason == "opening_skipped_duplicate":
                    continue
                excl.append(row)
            out["excluded_segment_ids"] = excl
            rationales = (
                dict(out.get("exclude_rationales") or {})
                if isinstance(out.get("exclude_rationales"), dict)
                else {}
            )
            for sid in restored:
                if rationales.get(sid) == "opening_skipped_duplicate":
                    rationales.pop(sid, None)
            out["exclude_rationales"] = rationales
    return out, actions


def pull_mid_arc_reverse_jumps(
    ordered: list[str],
    source_start_ms: dict[str, int] | None,
    *,
    guest_first: bool | None = None,
    margin_ms: int | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Scan all adjacent pairs; prepend earlier-tape families on reverse jump.

    Opening-window host-intro families are prepended (not dropped) even when
    guest/company tape already opened — prefer the native host intro on air.
    """
    base = [str(s) for s in ordered if str(s).strip()]
    if len(base) < 2 or not source_start_ms:
        return base, [], []
    if guest_first is None:
        guest_first = _guest_first_open_established(base, source_start_ms)
    _ = guest_first  # retained for call-site compatibility; no longer drops
    margin = reverse_jump_margin_ms() if margin_ms is None else margin_ms
    to_drop: list[str] = []
    moved: list[str] = []
    new_order = list(base)
    changed = True
    while changed:
        changed = False
        for i in range(len(new_order) - 1):
            after_id = new_order[i]
            before_id = new_order[i + 1]
            gap = pair_source_gap_ms(after_id, before_id, source_start_ms)
            if gap is None or gap >= -margin:
                continue
            family = letter_split_family(before_id, new_order)
            # Always prepend earlier-tape family before the later clip.
            rest = [s for s in new_order if s not in set(family)]
            insert_at = rest.index(after_id) if after_id in rest else 0
            family_sorted = sorted(
                family,
                key=lambda s: (
                    resolved_source_start_ms(s, source_start_ms) or 0,
                    base.index(s) if s in base else 0,
                ),
            )
            new_order = rest[:insert_at] + family_sorted + rest[insert_at:]
            for sid in family_sorted:
                if sid not in moved:
                    moved.append(sid)
            changed = True
            break
    return new_order, moved, to_drop


def repair_air_order_integrity(
    ctx: RunContext,
    selection: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Full integrity repair pass."""
    out = dict(selection)
    actions: list[dict[str, Any]] = []
    starts = resolved_segment_starts(ctx)
    pol = _resolve_policy(ctx, None, selection=out, starts=starts)
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    margin = reverse_jump_margin_ms(ctx=ctx, policy=pol)
    pulled, moved, dropped = pull_mid_arc_reverse_jumps(
        ordered, starts or None, margin_ms=margin
    )
    if moved or dropped or pulled != ordered:
        if dropped:
            out = _exclude_segments(out, dropped, reason="opening_skipped_duplicate")
            actions.append({"action": "mid_arc_exclude", "ids": dropped[:12]})
        else:
            out["ordered_segment_ids"] = pulled
            actions.append({"action": "mid_arc_pull", "ids": moved[:12]})
            # Clear stale duplicate excludes for ids we prepended back on air.
            restored = set(moved)
            if restored:
                excl = []
                for row in out.get("excluded_segment_ids") or []:
                    sid = str(row.get("segment_id") if isinstance(row, dict) else row)
                    reason = (
                        str(row.get("reason") or "")
                        if isinstance(row, dict)
                        else str((out.get("exclude_rationales") or {}).get(sid) or "")
                    )
                    if sid in restored and reason == "opening_skipped_duplicate":
                        continue
                    excl.append(row)
                out["excluded_segment_ids"] = excl
                rationales = (
                    dict(out.get("exclude_rationales") or {})
                    if isinstance(out.get("exclude_rationales"), dict)
                    else {}
                )
                for sid in restored:
                    if rationales.get(sid) == "opening_skipped_duplicate":
                        rationales.pop(sid, None)
                out["exclude_rationales"] = rationales
    out, opening_actions = repair_opening_tape_integrity(ctx, out, starts=starts)
    actions.extend(opening_actions)
    return out, actions


def critical_violations(violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [v for v in violations if str(v.get("severity") or "").lower() == "critical"]


def write_air_order_integrity_report(
    ctx: RunContext,
    *,
    violations: list[dict[str, Any]],
    actions: list[dict[str, Any]] | None = None,
    stage: str = "full_master_ranking",
    repaired: bool = False,
    resolved_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    critical = critical_violations(violations)
    policy = resolved_policy
    if policy is None and ctx.artifact_exists("master/selection.json"):
        try:
            sel = ctx.read_json("master/selection.json")
            policy = resolve_air_order_policy(
                ctx, selection=sel if isinstance(sel, dict) else None
            )
        except Exception:
            policy = resolve_air_order_policy(ctx)
    doc: dict[str, Any] = {
        "version": 1,
        "stage": stage,
        "repaired": bool(repaired),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "violation_count": len(violations),
        "critical_count": len(critical),
        "violations": violations[:32],
        "actions": list(actions or [])[:32],
        "ok": len(critical) == 0,
    }
    if policy:
        doc["resolved_policy"] = policy
    ctx.write_json(INTEGRITY_REL, doc, stage_key=stage)
    for v in critical:
        ctx.log(
            v.get("message") or str(v.get("code") or "air_order_integrity_violation"),
            level="error",
            stage=stage,
            detail=v,
        )
        _append_operator_log(ctx, v, stage=stage)
        _emit_homunculus_issue(ctx, v, stage=stage)
    return doc


def _append_operator_log(ctx: RunContext, violation: dict[str, Any], *, stage: str) -> None:
    line = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "violation": violation,
    }
    path = ctx.path(*OPERATOR_LOG_REL.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def _emit_homunculus_issue(ctx: RunContext, violation: dict[str, Any], *, stage: str) -> None:
    try:
        from interview_mux.homunculus.issues import ingest_catch

        ingest_catch(
            ctx,
            kind="air_order_integrity_violation",
            source=stage,
            evidence=violation,
            stage_id=stage,
        )
    except Exception:
        pass


def audit_and_report(
    ctx: RunContext,
    *,
    stage: str = "full_master_ranking",
    repair: bool = True,
) -> dict[str, Any]:
    if not ctx.artifact_exists("master/selection.json"):
        return {"ok": True, "violation_count": 0, "critical_count": 0}
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return {"ok": False, "violation_count": 0, "critical_count": 0}
    actions: list[dict[str, Any]] = []
    previous = dict(sel)
    if repair:
        sel, actions = repair_air_order_integrity(ctx, sel)
        if actions:
            on_selection_order_changed(ctx, source=f"audit_and_report:{stage}", previous=previous, current=sel)
            ctx.write_json("master/selection.json", sel, stage_key=stage)
    policy = resolve_air_order_policy(ctx, selection=sel)
    violations = collect_violations(ctx, sel, policy=policy)
    return write_air_order_integrity_report(
        ctx,
        violations=violations,
        actions=actions,
        stage=stage,
        repaired=bool(actions),
        resolved_policy=policy,
    )


def on_selection_order_changed(
    ctx: RunContext,
    *,
    source: str,
    previous: dict[str, Any] | None = None,
    current: dict[str, Any] | None = None,
) -> list[str]:
    """Invalidate stale transitions/EDL when air order changes."""
    notes: list[str] = []
    if current is None and ctx.artifact_exists("master/selection.json"):
        current = ctx.read_json("master/selection.json")
    if not isinstance(current, dict):
        return notes
    prev_ids = [
        str(s) for s in ((previous or {}).get("ordered_segment_ids") or []) if s
    ]
    cur_ids = [str(s) for s in (current.get("ordered_segment_ids") or []) if s]
    if prev_ids == cur_ids:
        return notes
    if invalidate_transitions_on_order_change() and ctx.is_done("transitions"):
        marker = ctx.final_path(".stage_done", "transitions")
        if marker.is_file():
            marker.unlink()
            notes.append("cleared_stage_done:transitions")
        if ctx.artifact_exists("master/transitions.json"):
            try:
                from interview_mux.artifact_repairs import prune_reverse_jump_transitions
                from interview_mux.gap_framing import prune_transitions_outside_selection

                tr = ctx.read_json("master/transitions.json")
                if isinstance(tr, dict):
                    pruned = prune_transitions_outside_selection(tr, cur_ids)
                    pruned, rnotes = prune_reverse_jump_transitions(ctx, pruned, cur_ids)
                    if int(pruned.get("outside_selection_pruned_count") or 0) or rnotes:
                        ctx.write_json("master/transitions.json", pruned, stage_key="transitions")
                        notes.extend(rnotes or [])
                        notes.append("prune_reverse_jump_transitions")
            except Exception:
                pass
    if invalidate_edl_on_order_change() and ctx.is_done("edl"):
        marker = ctx.final_path(".stage_done", "edl")
        if marker.is_file():
            marker.unlink()
            notes.append("cleared_stage_done:edl")
    if invalidate_mix_on_order_change() and ctx.is_done("mix"):
        edl_path = ctx.final_path("master", "edl.json")
        asm_path = ctx.final_path("master", "assembly.wav")
        stale_mix = False
        if edl_path.is_file() and asm_path.is_file():
            try:
                stale_mix = asm_path.stat().st_mtime < edl_path.stat().st_mtime
            except OSError:
                stale_mix = True
        if stale_mix or "cleared_stage_done:edl" in notes:
            marker = ctx.final_path(".stage_done", "mix")
            if marker.is_file():
                marker.unlink()
                notes.append("cleared_stage_done:mix")
    if prev_ids != cur_ids:
        try:
            if ctx.is_done("nugget_layup_compose") or ctx.artifact_exists(
                "understanding/nugget_layup_plan.json"
            ):
                from interview_mux.homunculus.agenda import invalidate_downstream

                invalidate_downstream(ctx, "nugget_layup_compose")
                notes.append("invalidated_downstream:nugget_layup_compose")
        except Exception:
            pass
    if notes:
        ctx.log(
            f"selection order changed ({source}): " + ", ".join(notes[:6]),
            level="warning",
            stage=source.split(":")[0] if ":" in source else source,
        )
    return notes


def lint_hard_keep_family_errors(
    ctx: RunContext,
    selection: dict[str, Any],
) -> list[str]:
    """Parent hard-keep with partial letter-split family mid-arc."""
    from interview_mux.hard_keep import hard_keep_segment_ids

    keeps = hard_keep_segment_ids(ctx)
    if not keeps:
        return []
    ordered = [str(s) for s in (selection.get("ordered_segment_ids") or []) if s]
    excl = {
        str(r.get("segment_id") if isinstance(r, dict) else r)
        for r in (selection.get("excluded_segment_ids") or [])
    }
    starts = resolved_segment_starts(ctx)
    pol = _resolve_policy(ctx, None, selection=selection, starts=starts)
    errors: list[str] = []
    pos = {sid: idx for idx, sid in enumerate(ordered)}
    for sid in keeps:
        if sid in ordered or sid in excl:
            continue
        family = letter_split_family(sid, ordered)
        present = [m for m in family if m in ordered]
        if not present:
            errors.append(f"hard-keep segment {sid} must appear in ordered_segment_ids")
            continue
        if len(present) < len([m for m in family if m in set(ordered) | excl]):
            late = max(present, key=lambda s: pos.get(s, 0))
            if pos.get(late, 0) >= opening_body_start_index(ctx=ctx, policy=pol):
                start = resolved_source_start_ms(late, starts)
                if start is not None and start < opening_window_ms(ctx=ctx, policy=pol):
                    errors.append(
                        f"hard-keep family partial mid-arc: {sid} -> {present[:4]}"
                    )
    return errors
