"""Non-amplifying sanitizer for master/selection.json."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.artifact_sanitize.config import sanitize_selection_cfg
from interview_mux.artifact_sanitize.types import SanitizeResult

SELECTION_REL = "master/selection.json"
_BASE_ID_RE = re.compile(r"^(seg_\d+)")


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
    """Map segment_id → (start_ms, end_ms)."""
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
    if out:
        return out
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
            if not sid:
                continue
            try:
                start = int(row.get("start_ms") or 0)
                end = int(row.get("end_ms") or start)
            except (TypeError, ValueError):
                continue
            out[sid] = (start, end)
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

    # 3. fragment depth budget
    depth_drop: list[str] = []
    kept_depth: list[str] = []
    for s in ordered:
        if _fragment_depth(s) > max_depth:
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

    # 4. overlapping / identical source-span collapse within family
    starts = _segment_starts(ctx)
    hard_keeps = _hard_keep_ids(ctx)
    if starts:
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

    # 5. same-family on-air budget
    family_counts: dict[str, list[str]] = {}
    for s in ordered:
        family_counts.setdefault(_base_family(s), []).append(s)
    family_drop: list[str] = []
    for fam, members in family_counts.items():
        if len(members) <= max_family:
            continue
        # keep shortest / shallowest first
        ranked = sorted(members, key=lambda x: (_fragment_depth(x), len(x), x))
        keep_set = set(ranked[:max_family])
        for m in members:
            if m not in keep_set:
                family_drop.append(m)
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

    # Move dropped ids into exclusions
    dropped_all = {
        str(a.get("segment_id") or "")
        for a in actions
        if a.get("action") == "dedupe_exact" and a.get("segment_id")
    }
    for a in actions:
        for key in ("ids",):
            for sid in a.get(key) or []:
                dropped_all.add(str(sid))
    if depth_drop:
        dropped_all.update(depth_drop)

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
    for sid in sorted(dropped_all):
        if not sid or sid in have_ex or sid in ordered:
            continue
        reason = "sanitize_duplicate_source_span"
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
    # still over family budget somehow
    fam2: dict[str, int] = {}
    for s in ordered:
        fam2[_base_family(s)] = fam2.get(_base_family(s), 0) + 1
    over = {k: v for k, v in fam2.items() if v > max_family}
    if over:
        errors.append(f"same_family_budget_exceeded:{sorted(over.items())[:4]}")

    # optional integrity criticals (detect only — do not amplify)
    try:
        from interview_mux.air_order_integrity import collect_violations, critical_violations

        viol = collect_violations(ctx, out)
        crit = critical_violations(viol)
        if crit:
            codes = [str(v.get("code") or "") for v in crit[:6]]
            # Soft: record but only refuse if opening/empty-class criticals
            hard_codes = {
                "empty_order",
                "missing_selection",
                "no_speech_segments",
            }
            if any(c in hard_codes for c in codes):
                errors.append("air_order_critical:" + ",".join(codes))
            else:
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
    cfg = sanitize_selection_cfg()
    max_family = int(cfg.get("max_same_family_on_air") or 8)
    max_depth = int(cfg.get("max_fragment_depth") or 3)
    errs: list[str] = []
    deep = [s for s in ordered if _fragment_depth(str(s)) > max_depth]
    if deep:
        errs.append(f"fragment_depth_exceeded:{len(deep)}")
    fam: dict[str, int] = {}
    for s in ordered:
        fam[_base_family(str(s))] = fam.get(_base_family(str(s)), 0) + 1
    over = sum(1 for v in fam.values() if v > max_family)
    if over:
        errs.append(f"same_family_over_budget:{over}")
    stamp_keys = ["ordered_segment_ids", "order_content_hash"]
    stamp_fresh = stamp_matches(doc, content_keys=stamp_keys)
    # Stale stamp (ok with diverged order) must never short-circuit.
    if stamp.get("ok") is True and stamp_fresh and not errs:
        return []
    if stamp.get("ok") is True and not stamp_fresh:
        errs.append("selection_sanitize_stamp_stale")
    if errs:
        return errs
    # No fresh stamp — run dry sanitize and report
    result = sanitize_master_selection(ctx, doc)
    if result.ok and not result.actions:
        return []
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
    try:
        from interview_mux.stage_completion import heal_or_refuse_mark

        heal_or_refuse_mark(ctx, "selection_order_sanitize")
    except Exception:
        if result.ok:
            try:
                ctx.mark_done("selection_order_sanitize")
            except Exception:
                pass
