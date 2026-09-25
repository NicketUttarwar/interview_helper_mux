"""Non-amplifying sanitizer for master/selection.json."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.artifact_sanitize.config import sanitize_selection_cfg
from interview_mux.artifact_sanitize.types import SanitizeResult

SELECTION_REL = "master/selection.json"
_BASE_ID_RE = re.compile(r"^(seg_\d+)")
# Lock hash refresh is not an air-order mutation (F1 2A restamp).
_COSMETIC_SANITIZE_ACTIONS = frozenset({"bump_order_lock"})
_EXCLUDE_REASON_BY_ACTION: dict[str, str] = {
    "dedupe_exact": "dedupe_exact",
    "drop_never_touch_cta": "drop_never_touch_cta",
    "collapse_fragment_depth": "collapse_fragment_depth",
    "sanitize_duplicate_source_span": "sanitize_duplicate_source_span",
    "cap_same_family_on_air": "cap_same_family_on_air",
}


def _base_family(sid: str) -> str:
    m = _BASE_ID_RE.match(str(sid or ""))
    return m.group(1) if m else str(sid or "")


def _fragment_depth(sid: str) -> int:
    """Depth of NLE-style suffix letters after the numeric base (seg_003aaaa → 4)."""
    s = str(sid or "")
    m = _BASE_ID_RE.match(s)
    if not m:
        return 0
    suffix = s[m.end() :]
    return len(suffix)


def _segment_starts(ctx: Any) -> dict[str, tuple[int, int]]:
    """Map segment_id → (start_ms, end_ms).

    Includes committed NLE/manifest/boundaries, then overlays pending
    ``.pending_writes/*/segments/nle_edits.json`` overrides so multi-letter
    family children (e.g. seg_062la) are not refused while NLE is staged.
    """
    out: dict[str, tuple[int, int]] = {}
    try:
        from interview_mux.nle_state import segments_by_id_with_nle

        by_id = segments_by_id_with_nle(ctx)
    except Exception:
        by_id = {}
    for sid, row in (by_id or {}).items():
        if not isinstance(row, dict):
            continue
        try:
            start = int(row.get("start_ms") or 0)
            end = int(row.get("end_ms") or start)
        except (TypeError, ValueError):
            continue
        out[str(sid)] = (start, end)
    # Always merge boundaries/manifest for parents missing from NLE map.
    for rel in ("segments/boundaries.json", "segments/segments.json", "segments/manifest.json"):
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        rows = []
        if isinstance(doc, dict):
            rows = list(
                doc.get("boundaries")
                or doc.get("segments")
                or doc.get("items")
                or []
            )
        for row in rows:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("segment_id") or row.get("id") or "")
            if not sid or sid in out:
                continue
            try:
                start = int(row.get("start_ms") or 0)
                end = int(row.get("end_ms") or start)
            except (TypeError, ValueError):
                continue
            out[sid] = (start, end)
    # Pending NLE overrides fill letter-split children not yet committed.
    try:
        pending_root = getattr(ctx, "run_dir", None)
        if pending_root is not None:
            root = pending_root / ".pending_writes"
            if root.is_dir():
                for stage_dir in root.iterdir():
                    if not stage_dir.is_dir():
                        continue
                    nle_path = stage_dir / "segments" / "nle_edits.json"
                    if not nle_path.is_file():
                        continue
                    try:
                        import json

                        data = json.loads(nle_path.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    overrides = (
                        data.get("segment_overrides")
                        if isinstance(data, dict)
                        else None
                    )
                    if not isinstance(overrides, dict):
                        continue
                    for sid, ov in overrides.items():
                        if not isinstance(ov, dict):
                            continue
                        if "start_ms" not in ov or "end_ms" not in ov:
                            continue
                        key = str(sid)
                        if key in out:
                            continue
                        try:
                            out[key] = (int(ov["start_ms"]), int(ov["end_ms"]))
                        except (TypeError, ValueError):
                            continue
    except Exception:
        pass
    # Persisted inherit hints from prior sanitize (letter kids without NLE spans).
    try:
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            meta = (sel or {}).get("_meta") if isinstance(sel, dict) else None
            hints = (meta or {}).get("inherited_segment_spans") if isinstance(meta, dict) else None
            if isinstance(hints, dict):
                for sid, span in hints.items():
                    key = str(sid)
                    if key in out or not isinstance(span, dict):
                        continue
                    try:
                        out[key] = (int(span["start_ms"]), int(span["end_ms"]))
                    except (KeyError, TypeError, ValueError):
                        continue
    except Exception:
        pass
    return out


def _inherit_letter_family_starts(
    starts: dict[str, tuple[int, int]],
    wanted: list[str],
) -> dict[str, tuple[int, int]]:
    """Fill missing letter-suffix ids from nearest shorter ancestor span."""
    out = dict(starts)
    for sid in wanted:
        key = str(sid or "").strip()
        if not key or key in out:
            continue
        cand = key
        while cand and cand[-1].isalpha() and not cand[-1].isdigit():
            cand = cand[:-1]
            if not cand:
                break
            if cand in out:
                out[key] = out[cand]
                break
    return out


def _spans_overlap_or_nested(a: tuple[int, int], b: tuple[int, int], *, tol_ms: int = 40) -> bool:
    a0, a1 = a
    b0, b1 = b
    if a1 < a0:
        a0, a1 = a1, a0
    if b1 < b0:
        b0, b1 = b1, b0
    # identical / near-identical
    if abs(a0 - b0) <= tol_ms and abs(a1 - b1) <= tol_ms:
        return True
    # nested
    if a0 <= b0 + tol_ms and a1 + tol_ms >= b1:
        return True
    if b0 <= a0 + tol_ms and b1 + tol_ms >= a1:
        return True
    # substantial overlap
    overlap = min(a1, b1) - max(a0, b0)
    if overlap <= 0:
        return False
    shorter = max(1, min(a1 - a0, b1 - b0))
    return overlap >= 0.85 * shorter


def _prefer_keep(a: str, b: str, hard_keeps: set[str]) -> str:
    if a in hard_keeps and b not in hard_keeps:
        return a
    if b in hard_keeps and a not in hard_keeps:
        return b
    da, db = _fragment_depth(a), _fragment_depth(b)
    if da != db:
        return a if da < db else b
    return a if len(a) <= len(b) else b


def _hard_keep_ids(ctx: Any) -> set[str]:
    try:
        from interview_mux.hard_keep import hard_keep_segment_ids

        return set(hard_keep_segment_ids(ctx) or [])
    except Exception:
        return set()


def _never_touch(ctx: Any) -> set[str]:
    try:
        from interview_mux.media_ip_cta import never_touch_segment_ids

        return set(never_touch_segment_ids(ctx) or [])
    except Exception:
        return set()


def _multi_member_family_ids(ordered: list[str]) -> set[str]:
    counts: dict[str, list[str]] = {}
    for s in ordered:
        counts.setdefault(_base_family(s), []).append(s)
    out: set[str] = set()
    for members in counts.values():
        if len(members) > 1:
            out.update(members)
    return out


def _remaining_same_family_overlaps(
    ordered: list[str], starts: dict[str, tuple[int, int]]
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(ordered):
        span_a = starts.get(a)
        if span_a is None:
            continue
        fam_a = _base_family(a)
        for b in ordered[i + 1 :]:
            if _base_family(b) != fam_a:
                continue
            span_b = starts.get(b)
            if span_b is None:
                continue
            if _spans_overlap_or_nested(span_a, span_b):
                pairs.append((a, b))
    return pairs


def _starts_unavailable_error(
    ordered: list[str], starts: dict[str, tuple[int, int]]
) -> str | None:
    need = _multi_member_family_ids(ordered)
    if not need:
        return None
    resolved = _inherit_letter_family_starts(starts, list(need))
    missing = [s for s in need if s not in resolved]
    if missing:
        return "segment_starts_unavailable"
    # Publish inherited spans into the live map for overlap collapse.
    for s in need:
        if s in resolved and s not in starts:
            starts[s] = resolved[s]
    return None


def sanitize_master_selection(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    """Conservative clean of locked air order — never unbounded readmit."""
    cfg = sanitize_selection_cfg()
    max_family = int(cfg.get("max_same_family_on_air") or 8)
    max_depth = int(cfg.get("max_fragment_depth") or 3)
    actions: list[dict[str, Any]] = []
    errors: list[str] = []
    out = dict(doc or {})
    ordered_raw = out.get("ordered_segment_ids")
    if not isinstance(ordered_raw, list):
        return SanitizeResult(
            doc=out,
            ok=False,
            errors=["ordered_segment_ids missing or not a list"],
            artifact_rel=SELECTION_REL,
        )
    before_n = len([s for s in ordered_raw if s])
    chapters_in = out.get("chapters")
    had_chapters = isinstance(chapters_in, list) and bool(chapters_in)
    hard_keeps = _hard_keep_ids(ctx)
    drop_reasons: dict[str, str] = {}

    # 1. shape / exact dedupe
    seen: set[str] = set()
    ordered: list[str] = []
    for sid in ordered_raw:
        s = str(sid or "").strip()
        if not s:
            actions.append({"action": "drop_blank_id"})
            continue
        if s in seen:
            actions.append({"action": "dedupe_exact", "segment_id": s})
            drop_reasons.setdefault(s, "dedupe_exact")
            continue
        seen.add(s)
        ordered.append(s)

    # 2. never-touch CTA drop (no readmit)
    banned = _never_touch(ctx)
    if banned:
        drop = [s for s in ordered if s in banned]
        if drop:
            ordered = [s for s in ordered if s not in banned]
            actions.append({"action": "drop_never_touch_cta", "ids": drop[:24]})
            for sid in drop:
                drop_reasons.setdefault(sid, "drop_never_touch_cta")

    # 3. fragment depth budget — never drop hard-keeps; refuse if they exceed
    depth_drop: list[str] = []
    kept_depth: list[str] = []
    deep_hard_keeps: list[str] = []
    for s in ordered:
        if _fragment_depth(s) > max_depth:
            if s in hard_keeps:
                deep_hard_keeps.append(s)
                kept_depth.append(s)
            else:
                depth_drop.append(s)
        else:
            kept_depth.append(s)
    if depth_drop:
        ordered = kept_depth
        actions.append(
            {
                "action": "collapse_fragment_depth",
                "max_depth": max_depth,
                "ids": depth_drop[:40],
            }
        )
        for sid in depth_drop:
            drop_reasons.setdefault(sid, "collapse_fragment_depth")
    else:
        ordered = kept_depth
    if deep_hard_keeps:
        errors.append(
            "hard_keep_exceeds_fragment_depth:" + ",".join(deep_hard_keeps[:8])
        )

    # 4. overlapping / identical source-span collapse within family
    starts = _segment_starts(ctx)
    starts_err = _starts_unavailable_error(ordered, starts)
    if starts_err:
        errors.append(starts_err)
    else:
        # Persist inherited letter-family spans so the next commit/sanitize does
        # not re-refuse segment_starts_unavailable (exec_13183 repair-once).
        try:
            need = _multi_member_family_ids(ordered)
            hints: dict[str, dict[str, int]] = {}
            meta_in = out.get("_meta") if isinstance(out.get("_meta"), dict) else {}
            prev_hints = meta_in.get("inherited_segment_spans")
            if isinstance(prev_hints, dict):
                for sid, span in prev_hints.items():
                    if isinstance(span, dict) and "start_ms" in span and "end_ms" in span:
                        hints[str(sid)] = {
                            "start_ms": int(span["start_ms"]),
                            "end_ms": int(span["end_ms"]),
                        }
            for sid in need:
                span = starts.get(sid)
                if span is None:
                    continue
                hints[str(sid)] = {"start_ms": int(span[0]), "end_ms": int(span[1])}
            if hints:
                meta = dict(meta_in)
                meta["inherited_segment_spans"] = hints
                out["_meta"] = meta
                actions.append(
                    {
                        "action": "persist_inherited_segment_spans",
                        "count": len(hints),
                    }
                )
        except Exception:
            pass
    if starts and not starts_err:
        survivors: list[str] = []
        dropped_span: list[str] = []
        for sid in ordered:
            span = starts.get(sid)
            if span is None:
                survivors.append(sid)
                continue
            family = _base_family(sid)
            collide_idx = None
            for i, other in enumerate(survivors):
                if _base_family(other) != family:
                    continue
                other_span = starts.get(other)
                if other_span is None:
                    continue
                if _spans_overlap_or_nested(span, other_span):
                    collide_idx = i
                    break
            if collide_idx is None:
                survivors.append(sid)
                continue
            other = survivors[collide_idx]
            if other in hard_keeps and sid in hard_keeps:
                # Leave both; refuse rather than drop a hard-keep.
                errors.append(f"hard_keep_span_collision:{other},{sid}")
                survivors.append(sid)
                continue
            keep = _prefer_keep(other, sid, hard_keeps)
            if keep == other:
                dropped_span.append(sid)
            else:
                dropped_span.append(other)
                survivors[collide_idx] = sid
        if dropped_span:
            ordered = survivors
            actions.append(
                {
                    "action": "sanitize_duplicate_source_span",
                    "ids": dropped_span[:40],
                }
            )
            for sid in dropped_span:
                drop_reasons.setdefault(sid, "sanitize_duplicate_source_span")
        else:
            ordered = survivors
        leftover = _remaining_same_family_overlaps(ordered, starts)
        if leftover and not any(
            e.startswith("hard_keep_span_collision:") for e in errors
        ):
            errors.append("overlap_collapse_incomplete")

    # 5. same-family on-air budget — prefer hard-keeps; refuse if still over
    family_counts: dict[str, list[str]] = {}
    for s in ordered:
        family_counts.setdefault(_base_family(s), []).append(s)
    family_drop: list[str] = []
    for fam, members in family_counts.items():
        if len(members) <= max_family:
            continue
        ranked = sorted(
            members,
            key=lambda x: (
                0 if x in hard_keeps else 1,
                _fragment_depth(x),
                len(x),
                x,
            ),
        )
        keep_set = set(ranked[:max_family])
        # Never drop hard-keeps from keep_set
        for m in members:
            if m in hard_keeps:
                keep_set.add(m)
        for m in members:
            if m not in keep_set:
                family_drop.append(m)
        kept_hard = [m for m in members if m in hard_keeps]
        if len(kept_hard) > max_family:
            errors.append(
                f"hard_keep_same_family_over_budget:{fam}:{len(kept_hard)}"
            )
        elif len([m for m in members if m in keep_set]) > max_family:
            # keep_set grew via hard-keeps beyond budget
            errors.append(
                f"hard_keep_same_family_over_budget:{fam}:"
                f"{len([m for m in members if m in keep_set])}"
            )
    if family_drop:
        drop_set = set(family_drop)
        ordered = [s for s in ordered if s not in drop_set]
        actions.append(
            {
                "action": "cap_same_family_on_air",
                "max": max_family,
                "ids": family_drop[:40],
            }
        )
        for sid in family_drop:
            drop_reasons.setdefault(sid, "cap_same_family_on_air")

    # Move dropped ids into exclusions (honest per-action reasons)
    excl = list(out.get("excluded_segment_ids") or [])
    have_ex = {
        str(r.get("segment_id") if isinstance(r, dict) else r)
        for r in excl
        if r is not None
    }
    rationales = (
        dict(out.get("exclude_rationales"))
        if isinstance(out.get("exclude_rationales"), dict)
        else {}
    )
    for sid in sorted(drop_reasons):
        if not sid or sid in have_ex or sid in ordered:
            continue
        reason = drop_reasons[sid]
        excl.append({"segment_id": sid, "reason": reason})
        rationales[sid] = reason
        have_ex.add(sid)
    out["ordered_segment_ids"] = ordered
    out["excluded_segment_ids"] = excl
    if rationales:
        out["exclude_rationales"] = rationales

    # 6. chapter clamp
    chapters = out.get("chapters")
    if isinstance(chapters, list):
        order_set = set(ordered)
        new_chapters: list[Any] = []
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            ids = [str(s) for s in (ch.get("segment_ids") or []) if str(s) in order_set]
            row = dict(ch)
            row["segment_ids"] = ids
            if not ids:
                actions.append(
                    {
                        "action": "drop_empty_chapter",
                        "title": str(ch.get("title") or "")[:80],
                    }
                )
                continue
            new_chapters.append(row)
        out["chapters"] = new_chapters
        if had_chapters and not new_chapters and ordered:
            errors.append("chapters_emptied_by_sanitize")

    # 7. reconcile ordered vs excluded (ordered wins)
    order_set = set(ordered)
    if isinstance(out.get("excluded_segment_ids"), list):
        pruned = []
        for row in out["excluded_segment_ids"]:
            sid = str(row.get("segment_id") if isinstance(row, dict) else row)
            if sid in order_set:
                continue
            pruned.append(row if isinstance(row, dict) else {"segment_id": sid, "reason": "excluded"})
        if len(pruned) != len(out["excluded_segment_ids"]):
            actions.append({"action": "reconcile_ordered_vs_excluded"})
        out["excluded_segment_ids"] = pruned

    # 7b. exclude_rationales may only describe excluded ids — never air-order ids.
    try:
        from interview_mux.artifact_repairs import prune_stale_exclude_rationales

        before_rat = (
            dict(out.get("exclude_rationales"))
            if isinstance(out.get("exclude_rationales"), dict)
            else {}
        )
        out, prune_notes = prune_stale_exclude_rationales(out)
        if prune_notes or before_rat != (
            dict(out.get("exclude_rationales"))
            if isinstance(out.get("exclude_rationales"), dict)
            else {}
        ):
            actions.append({"action": "prune_stale_exclude_rationales"})
    except Exception:
        pass

    # 7c. Constraint lattice — restore never-exclude primary impact + hard-keeps.
    # Sanitize previously stamped ok=True while selection_sanitary_errors still
    # reported framing:primary impact… (exec_13198 sticky incomplete_after_conductor).
    try:
        from interview_mux.selection_constraints import apply_selection_constraints

        before_order = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
        out = apply_selection_constraints(ctx, out)
        ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
        restored = [s for s in ordered if s not in before_order]
        if restored or ordered != before_order:
            actions.append(
                {
                    "action": "apply_selection_constraints",
                    "restored": restored[:24],
                    "before_count": len(before_order),
                    "after_count": len(ordered),
                }
            )
    except Exception as exc:
        errors.append(f"selection_constraints_failed:{type(exc).__name__}")

    # Fail closed on framing/hard-keep lattice criticals after restore.
    # Air-order integrity criticals stay metrics-only (ranking repairs jumps).
    try:
        from interview_mux.selection_constraints import (
            critical_lattice_lint_codes,
            lattice_lint_codes,
        )

        for code in critical_lattice_lint_codes(lattice_lint_codes(ctx, out))[:6]:
            if code and code not in errors:
                errors.append(code)
    except Exception:
        pass

    # 8. stamp lock
    try:
        from interview_mux.order_hash import bump_order_lock

        out = bump_order_lock(out, source="artifact_sanitize.selection")
        actions.append({"action": "bump_order_lock", "source": "artifact_sanitize.selection"})
    except Exception:
        pass

    after_n = len(ordered)
    metrics = {
        "before_count": before_n,
        "after_count": after_n,
        "dropped": max(0, before_n - after_n),
        "max_same_family_on_air": max_family,
        "max_fragment_depth": max_depth,
    }

    # Refuse thresholds
    if after_n == 0:
        errors.append("ordered_segment_ids empty after sanitize")
    fam2: dict[str, int] = {}
    for s in ordered:
        fam2[_base_family(s)] = fam2.get(_base_family(s), 0) + 1
    over = {k: v for k, v in fam2.items() if v > max_family}
    if over and not any(e.startswith("hard_keep_same_family_over_budget:") for e in errors):
        errors.append(f"same_family_budget_exceeded:{sorted(over.items())[:4]}")

    # Integrity criticals: metrics only (repair/pin belongs to ranking)
    try:
        from interview_mux.air_order_integrity import collect_violations, critical_violations

        viol = collect_violations(ctx, out)
        crit = critical_violations(viol)
        if crit:
            codes = [str(v.get("code") or "") for v in crit[:6] if v.get("code")]
            if codes:
                metrics["integrity_critical_codes"] = codes
    except Exception:
        pass

    ok = not errors
    from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta

    out = stamp_sanitize_meta(
        out,
        ok=ok,
        source="artifact_sanitize.selection",
        actions_n=len(actions),
        extra={"after_count": after_n},
        content_keys=["ordered_segment_ids", "order_content_hash"],
    )

    return SanitizeResult(
        doc=out,
        actions=actions,
        ok=ok,
        errors=errors,
        metrics=metrics,
        artifact_rel=SELECTION_REL,
    )


def selection_sanitary_hash(doc: dict[str, Any] | None) -> str:
    if not isinstance(doc, dict):
        return "empty"
    lock = doc.get("order_lock") if isinstance(doc.get("order_lock"), dict) else {}
    hc = str(doc.get("order_content_hash") or lock.get("order_content_hash") or "")
    ids = doc.get("ordered_segment_ids") or []
    return f"{hc}:{len(ids) if isinstance(ids, list) else 0}"


def _restamp_selection_sanitize_meta(ctx: Any, doc: dict[str, Any]) -> None:
    """Off-bus stamp refresh — only when ordered ids are unchanged."""
    from interview_mux.write_staging import write_committed_json

    out = dict(doc)
    meta = dict(out.get("_meta") or {}) if isinstance(out.get("_meta"), dict) else {}
    meta["producer_stage"] = "selection_order_sanitize"
    out["_meta"] = meta
    write_committed_json(
        ctx,
        SELECTION_REL,
        out,
        stage_key="selection_order_sanitize",
    )


def _lattice_and_integrity_errs(ctx: Any, doc: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    try:
        from interview_mux.selection_constraints import (
            critical_lattice_lint_codes,
            lattice_lint_codes,
        )

        codes = lattice_lint_codes(ctx, doc)
        crit = critical_lattice_lint_codes(codes)
        if crit:
            errs.extend(crit[:4])
    except Exception:
        pass
    try:
        from interview_mux.air_order_integrity import collect_violations, critical_violations

        viol = collect_violations(ctx, doc)
        crit_v = critical_violations(viol)
        if crit_v:
            codes = [str(v.get("code") or "") for v in crit_v[:6] if v.get("code")]
            if codes:
                errs.append("air_order_integrity_critical:" + ",".join(codes))
    except Exception:
        pass
    return errs


def _shape_sanitary_errs(ctx: Any, ordered: list[str], doc: dict[str, Any]) -> list[str]:
    cfg = sanitize_selection_cfg()
    max_family = int(cfg.get("max_same_family_on_air") or 8)
    max_depth = int(cfg.get("max_fragment_depth") or 3)
    hard_keeps = _hard_keep_ids(ctx)
    errs: list[str] = []
    deep = [str(s) for s in ordered if _fragment_depth(str(s)) > max_depth]
    if deep:
        deep_hk = [s for s in deep if s in hard_keeps]
        deep_other = [s for s in deep if s not in hard_keeps]
        if deep_hk:
            errs.append("hard_keep_exceeds_fragment_depth:" + ",".join(deep_hk[:8]))
        if deep_other:
            errs.append(f"fragment_depth_exceeded:{len(deep_other)}")
    fam: dict[str, list[str]] = {}
    for s in ordered:
        fam.setdefault(_base_family(str(s)), []).append(str(s))
    over_n = 0
    for fam_id, members in fam.items():
        if len(members) <= max_family:
            continue
        over_n += 1
        hk_n = sum(1 for m in members if m in hard_keeps)
        if hk_n > max_family:
            errs.append(f"hard_keep_same_family_over_budget:{fam_id}:{hk_n}")
    if over_n and not any(e.startswith("hard_keep_same_family_over_budget:") for e in errs):
        errs.append(f"same_family_over_budget:{over_n}")
    starts = _segment_starts(ctx)
    starts_err = _starts_unavailable_error([str(s) for s in ordered], starts)
    if starts_err:
        errs.append(starts_err)
    elif starts:
        leftover = _remaining_same_family_overlaps([str(s) for s in ordered], starts)
        if leftover:
            both_hk = [
                (a, b)
                for a, b in leftover
                if a in hard_keeps and b in hard_keeps
            ]
            if both_hk:
                a, b = both_hk[0]
                errs.append(f"hard_keep_span_collision:{a},{b}")
            else:
                errs.append("overlap_collapse_incomplete")
    chapters = doc.get("chapters")
    if isinstance(chapters, list) and chapters == [] and ordered:
        # Only flag when meta says chapters were emptied, or chapters key present
        # with prior non-empty is not recoverable here — rely on dry sanitize.
        pass
    return errs


def selection_sanitary_errors(ctx: Any) -> list[str]:
    """Errors if current on-disk selection is unsafe for layup/SDP."""
    if not ctx.artifact_exists(SELECTION_REL):
        return ["master/selection.json missing"]
    try:
        doc = ctx.read_json(SELECTION_REL)
    except Exception as exc:
        return [f"master/selection.json unreadable: {exc}"]
    if not isinstance(doc, dict):
        return ["master/selection.json invalid"]
    from interview_mux.artifact_sanitize.reentry import stamp_matches

    meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
    stamp = meta.get("sanitize") if isinstance(meta.get("sanitize"), dict) else {}
    ordered = doc.get("ordered_segment_ids")
    if not isinstance(ordered, list) or not ordered:
        return ["ordered_segment_ids empty"]
    ordered_s = [str(s) for s in ordered]
    errs = _shape_sanitary_errs(ctx, ordered_s, doc)
    errs.extend(_lattice_and_integrity_errs(ctx, doc))
    stamp_keys = ["ordered_segment_ids", "order_content_hash"]
    stamp_fresh = stamp_matches(doc, content_keys=stamp_keys)
    # Stale stamp (ok with diverged order) must never short-circuit.
    if stamp.get("ok") is True and stamp_fresh and not errs:
        return []
    if errs:
        return errs
    if stamp.get("ok") is True and not stamp_fresh:
        # F1 2A: restamp when a fresh sanitize would pass; do not block on stale hash.
        disk_ids = list(ordered_s)
        result = sanitize_master_selection(ctx, doc)
        result_ids = [
            str(s) for s in (result.doc.get("ordered_segment_ids") or []) if s
        ]
        mutating = [
            a
            for a in (result.actions or [])
            if str((a or {}).get("action") or "") not in _COSMETIC_SANITIZE_ACTIONS
        ]
        if result.ok and not mutating and result_ids == disk_ids:
            try:
                _restamp_selection_sanitize_meta(ctx, result.doc)
            except Exception:
                pass
            return []
        if result.ok and mutating:
            return [
                "selection_needs_sanitize:"
                + ",".join(str(a.get("action") or "") for a in mutating[:6])
            ]
        if result.ok and result_ids != disk_ids:
            return [
                "selection_needs_sanitize:"
                + ",".join(str(a.get("action") or "") for a in (result.actions or [])[:6])
            ]
        return list(result.errors or ["selection_sanitize_stamp_stale"])
    # No fresh stamp — run dry sanitize and report
    result = sanitize_master_selection(ctx, doc)
    if result.ok and not result.actions:
        return list(_lattice_and_integrity_errs(ctx, result.doc or doc))
    if not result.ok:
        return list(result.errors or ["selection sanitize refused"])
    # Would change — treat as unsanitary until stage commits
    return ["selection_needs_sanitize:" + ",".join(
        str(a.get("action") or "") for a in (result.actions or [])[:6]
    )]


def run_selection_order_sanitize(ctx: Any) -> None:
    """Delivery stage: sanitize + commit selection; refuse mark when not ok."""
    if not ctx.artifact_exists(SELECTION_REL):
        raise RuntimeError("selection_order_sanitize: master/selection.json missing")
    doc = ctx.read_json(SELECTION_REL)
    if not isinstance(doc, dict):
        raise RuntimeError("selection_order_sanitize: selection invalid")
    result = sanitize_master_selection(ctx, doc)
    from interview_mux.artifact_sanitize.audit import write_sanitize_audit

    write_sanitize_audit(
        ctx, result, stage_key="selection_order_sanitize", mode="stage"
    )
    if not result.ok:
        raise RuntimeError(
            "sanitize_refused:selection: " + "; ".join((result.errors or ["unknown"])[:4])
        )
    from interview_mux.air_order_boundary import commit_selection_mutation

    # write_committed avoids write_validated → repair undoing sanitize.
    commit_selection_mutation(
        ctx,
        result.doc,
        producer="artifact_sanitize.selection",
        stage_key="selection_order_sanitize",
        checkpoint_mode="detect",
        skip_checkpoint=False,
        write_committed=True,
    )
    from interview_mux.stage_completion import heal_or_raise

    heal_or_raise(ctx, "selection_order_sanitize")
