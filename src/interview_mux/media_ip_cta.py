"""Host execution of 0.1.0 flagship media-IP CTA judgments.

Flagship ranking decides which natives are clear this-listener media pitches.
This module drops those ids, optionally recuts mixed story+pitch clips, and
exposes never-touch / coverage-exempt / clone-cover flags to layup. 0.0.0 is
a no-op. No keyword engine.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from interview_mux.run_context import RunContext

REASON = "media_ip_cta"
ARTIFACT_REL = "mastering/media_ip_cta.json"
SKIP_HOLE = "media_ip_cta_hole"
MIN_CHILD_MS = 1500
_LETS_HEAR_RE = (
    "let's hear",
    "lets hear",
    "let us hear",
)


def enabled(ctx: RunContext) -> bool:
    try:
        from interview_mux.homunculus.runtime import is_homunculus_run

        return bool(is_homunculus_run(ctx))
    except Exception:
        return False


def cta_cover_budget_exempt(ctx: RunContext) -> bool:
    return bool(getattr(ctx, "_cta_cover_regenerate_inner", False))


@contextmanager
def cta_cover_regenerate_scope(ctx: RunContext) -> Iterator[None]:
    """Mandatory cover text+voice rerun — does not burn the 3-invoke cap."""
    setattr(ctx, "_cta_cover_regenerate_inner", True)
    try:
        yield
    finally:
        if hasattr(ctx, "_cta_cover_regenerate_inner"):
            delattr(ctx, "_cta_cover_regenerate_inner")


def load_state(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(ARTIFACT_REL):
        return {}
    raw = ctx.read_json(ARTIFACT_REL)
    return raw if isinstance(raw, dict) else {}


def never_touch_segment_ids(ctx: RunContext) -> set[str]:
    state = load_state(ctx)
    ids = {str(x) for x in (state.get("dropped_segment_ids") or []) if x}
    ids |= {str(x) for x in (state.get("never_touch_segment_ids") or []) if x}
    return ids


def never_touch_texts(ctx: RunContext) -> list[str]:
    state = load_state(ctx)
    texts = [str(t).strip() for t in (state.get("never_touch_texts") or []) if str(t).strip()]
    if texts:
        return texts
    ids = never_touch_segment_ids(ctx)
    if not ids:
        return []
    by_id = _segments_by_id(ctx)
    out: list[str] = []
    for sid in ids:
        text = str((by_id.get(sid) or {}).get("text") or "").strip()
        if text:
            out.append(text)
    return out


def cover_target_ids(ctx: RunContext) -> set[str]:
    state = load_state(ctx)
    return {str(x) for x in (state.get("cover_target_ids") or []) if x}


def is_lets_hear_hinge(text: str) -> bool:
    key = " ".join(str(text or "").casefold().split())
    if not key:
        return False
    return any(p in key for p in _LETS_HEAR_RE)


def air_overlaps_never_touch(ctx: RunContext, text: str, *, min_overlap: float = 0.45) -> bool:
    """True when clone VO reuses dropped CTA wording (token overlap)."""
    air = _tokens(text)
    if len(air) < 4:
        return False
    for blob in never_touch_texts(ctx):
        other = _tokens(blob)
        if len(other) < 4:
            continue
        if _overlap(air, other) >= min_overlap:
            return True
    return False


def _reapply_locked(
    ctx: RunContext, artifacts: dict[str, Any], prev: dict[str, Any]
) -> dict[str, Any]:
    """Keep previously chosen CTA drops so --from-stage does not retarget."""
    dropped = [str(x) for x in (prev.get("dropped_segment_ids") or []) if x]
    drop_set = set(dropped)
    recuts = list(prev.get("recuts") or [])
    id_map = _id_map_from_recuts(recuts)
    story_ids = _story_ids_from_recuts(recuts)
    recut_parents = _recut_parent_ids(recuts)
    ordered = [str(s) for s in (artifacts.get("ordered_segment_ids") or []) if s]
    if id_map:
        ordered = _rewrite_order(ordered, id_map)
    ordered = [s for s in ordered if s not in drop_set]
    ordered = _admit_story_ids(ctx, ordered, story_ids, drop_set)
    story_first = _story_first_from_state(prev)
    if story_first and story_first in ordered:
        ordered = [story_first] + [s for s in ordered if s != story_first]
    elif story_first and story_first not in drop_set:
        ordered = [story_first] + ordered
    excl = _without_excluded_ids(list(artifacts.get("excluded_segment_ids") or []), set(story_ids))
    artifacts["ordered_segment_ids"] = ordered
    artifacts["excluded_segment_ids"] = _stamp_excludes(excl, dropped + recut_parents)
    artifacts["media_ip_cta"] = list(prev.get("judgments") or [])
    _rewrite_chapter_ids(artifacts, id_map, drop_set, story_ids)
    _sync_cold_open(artifacts, drop_set, id_map, ordered)
    return artifacts


def extract_judgments(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Keep only clearly flagged pitches. Unsure / missing → keep native."""
    if not isinstance(payload, dict):
        return []
    raw = payload.get("media_ip_cta")
    if isinstance(raw, dict):
        raw = raw.get("hits") or raw.get("judgments") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or "").strip()
        if not sid:
            continue
        if not _truthy(row.get("clearly_media_ip_pitch")):
            continue
        out.append(dict(row))
    return out


def apply_cta_judgments(ctx: RunContext, artifacts: dict[str, Any] | None) -> dict[str, Any]:
    """Execute flagship CTA calls on selection. Homunculus 0.1.0 only."""
    out = dict(artifacts) if isinstance(artifacts, dict) else {}
    if not enabled(ctx):
        return out
    prev = load_state(ctx)
    if prev.get("locked") and prev.get("dropped_segment_ids"):
        return _reapply_locked(ctx, out, prev)
    judgments = extract_judgments(out)
    ranking_cta_excludes = _cta_like_excluded_ids(out)
    if (
        not judgments
        and not ranking_cta_excludes
        and not (prev.get("locked") and prev.get("dropped_segment_ids"))
    ):
        _write_state(
            ctx,
            {
                "version": 1,
                "locked": False,
                "judgments": [],
                "dropped_segment_ids": [],
                "never_touch_segment_ids": [],
                "never_touch_texts": [],
                "cover_target_ids": [],
                "recuts": [],
                "notes": ["no_clear_media_ip_cta"],
            },
        )
        return out

    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    dropped: list[str] = []
    recuts: list[dict[str, Any]] = []
    notes: list[str] = []
    id_map: dict[str, list[str]] = {}
    cta_open_parent: str | None = None
    open_choice = ""
    recut_texts: list[str] = []

    for row in judgments:
        sid = str(row.get("segment_id") or "").strip()
        if not sid:
            continue
        mixed = _truthy(row.get("mixed_with_story")) or _truthy(row.get("must_keep_in_clip"))
        region = str(row.get("cta_region") or ("end" if mixed else "whole")).strip().lower()
        if _truthy(row.get("cta_open")) and cta_open_parent is None:
            cta_open_parent = sid
            open_choice = str(row.get("open_choice") or "").strip()
        if mixed and region != "whole":
            try:
                children, recut_note = _recut_parent(ctx, sid, row, region)
            except Exception as exc:
                notes.append(f"recut_failed:{sid}:{type(exc).__name__}")
                dropped.append(sid)
                recuts.append(
                    {
                        "parent_id": sid,
                        "ok": False,
                        "reason": "error",
                        "detail": str(exc)[:240],
                    }
                )
                continue
            if not children:
                notes.append(f"recut_unclean:{sid}")
                dropped.append(sid)
                recuts.append({"parent_id": sid, "ok": False, "reason": recut_note})
                continue
            cta_kids = _cta_children(children, region)
            story_kids = [c for c in children if c not in set(cta_kids)]
            if not cta_kids:
                dropped.append(sid)
                recuts.append({"parent_id": sid, "ok": False, "reason": "no_cta_child"})
                continue
            id_map[sid] = children
            dropped.extend(cta_kids)
            recut_texts.extend(_texts_for(ctx, cta_kids))
            _exclude_nle_ids(ctx, cta_kids)
            recuts.append(
                {
                    "parent_id": sid,
                    "ok": True,
                    "children": children,
                    "cta_children": cta_kids,
                    "story_children": story_kids,
                }
            )
        else:
            dropped.append(sid)

    dropped = list(dict.fromkeys(dropped))
    recut_parents = _recut_parent_ids(recuts)
    story_ids = _story_ids_from_recuts(recuts)
    if id_map:
        ordered = _rewrite_order(ordered, id_map)

    drop_set = set(dropped)
    story_first = ""
    if cta_open_parent:
        recut = next((r for r in recuts if r.get("parent_id") == cta_open_parent and r.get("ok")), None)
        story_kids = list((recut or {}).get("story_children") or [])
        if open_choice == "story_child_first" and story_kids:
            story_first = story_kids[0]
        elif not open_choice and story_kids:
            # Flagship omitted the pick — prefer leftover story when it exists.
            story_first = story_kids[0]
            open_choice = "story_child_first"
        elif not open_choice:
            open_choice = "third_person_opener"
        notes.append(f"cta_open:{cta_open_parent}:{open_choice or 'third_person_opener'}")

    cover_targets = _cover_targets(ordered, dropped, id_map)
    ordered = [s for s in ordered if s not in drop_set]
    # Sanitized remainder is back on the master — mine must not treat it as dropped tape.
    ordered = _admit_story_ids(ctx, ordered, story_ids, drop_set)
    if story_first and story_first in ordered:
        ordered = [story_first] + [s for s in ordered if s != story_first]
    elif story_first and story_first not in drop_set:
        ordered = [story_first] + ordered

    leftover_ranking_cta = [
        sid for sid in ranking_cta_excludes if sid not in drop_set and sid not in set(story_ids)
    ]
    dropped = list(dict.fromkeys([*dropped, *leftover_ranking_cta]))
    drop_set = set(dropped)
    never_touch = list(dict.fromkeys([*dropped, *recut_parents]))

    excl = _without_excluded_ids(list(out.get("excluded_segment_ids") or []), set(story_ids))
    excl = _stamp_excludes(excl, dropped + recut_parents)

    if not ordered:
        # Never leave selection empty — restore last non-CTA if we emptied the tape.
        notes.append("drop_emptied_selection")
        fallback = [str(s) for s in (out.get("ordered_segment_ids") or []) if s and s not in drop_set]
        ordered = fallback or [str(s) for s in (out.get("ordered_segment_ids") or []) if s][:1]
        ordered = _admit_story_ids(ctx, ordered, story_ids, drop_set)

    out["ordered_segment_ids"] = ordered
    out["excluded_segment_ids"] = excl
    out["media_ip_cta"] = judgments
    _rewrite_chapter_ids(out, id_map, drop_set, story_ids)
    _sync_cold_open(out, drop_set, id_map, ordered)

    texts = list(dict.fromkeys([*recut_texts, *_texts_for(ctx, never_touch)]))
    state = {
        "version": 1,
        "locked": True,
        "judgments": judgments,
        "dropped_segment_ids": dropped,
        "never_touch_segment_ids": never_touch,
        "never_touch_texts": texts,
        "cover_target_ids": cover_targets,
        "recuts": recuts,
        "cta_open_parent": cta_open_parent,
        "open_choice": open_choice or None,
        "notes": notes,
    }
    _write_state(ctx, state)
    ctx.log(
        "media_ip_cta: dropped "
        f"{len(dropped)} native(s); recuts={sum(1 for r in recuts if r.get('ok'))}",
        level="info",
        stage="full_master_ranking",
        detail={"dropped_segment_ids": dropped[:12], "cover_target_ids": cover_targets[:12]},
    )
    return out


def strip_never_touch_nuggets(ctx: RunContext, corpus: dict[str, Any] | None) -> dict[str, Any]:
    """Remove any nuggets whose evidence sits on a dropped CTA clip."""
    out = dict(corpus) if isinstance(corpus, dict) else {"nuggets": []}
    banned = never_touch_segment_ids(ctx)
    if not banned:
        return out
    kept: list[dict[str, Any]] = []
    dropped_ids: list[str] = []
    for nug in out.get("nuggets") or []:
        if not isinstance(nug, dict):
            continue
        sources = {str(x) for x in (nug.get("source_segment_ids") or []) if x}
        if sources & banned:
            nid = str(nug.get("nugget_id") or "")
            if nid:
                dropped_ids.append(nid)
            continue
        kept.append(nug)
    out["nuggets"] = kept
    if dropped_ids:
        warnings = list(out.get("warnings") or [])
        warnings.append(f"never_touch_cta_nuggets:{','.join(dropped_ids[:12])}")
        out["warnings"] = warnings
    return out


def attach_to_mine_input(ctx: RunContext, payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    banned = sorted(never_touch_segment_ids(ctx))
    if banned:
        out["never_touch_cta_segment_ids"] = banned
    return out


def attach_to_compose_input(ctx: RunContext, payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    state = load_state(ctx)
    banned = sorted(never_touch_segment_ids(ctx))
    covers = sorted(cover_target_ids(ctx))
    if banned:
        out["never_touch_cta_segment_ids"] = banned
    if covers:
        out["cta_cover_target_ids"] = covers
    natives = []
    cover_set = set(covers)
    for row in out.get("natives") or []:
        if not isinstance(row, dict):
            natives.append(row)
            continue
        native = dict(row)
        sid = str(native.get("segment_id") or "")
        if sid in cover_set:
            native["cta_hole_before"] = True
            native["cta_cover_allowed"] = True
        natives.append(native)
    if natives:
        out["natives"] = natives
    if state.get("open_choice"):
        out["cta_open_choice"] = state.get("open_choice")
    return out


def apply_cover_policy(
    ctx: RunContext, plan: dict[str, Any] | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Mark optional CTA-hole covers; stamp coverage-exempt skips; allow clone-adjacent."""
    out = dict(plan) if isinstance(plan, dict) else {"layups": []}
    notes: list[dict[str, Any]] = []
    if not enabled(ctx):
        return out, notes
    covers = cover_target_ids(ctx)
    if not covers:
        return out, notes
    from interview_mux.nugget_layup import stamp_typed_skip

    for row in out.get("layups") or []:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("target_segment_id") or "").strip()
        if tid not in covers:
            continue
        text = str(row.get("text") or "").strip()
        if row.get("skip") or not text:
            stamp_typed_skip(
                row,
                reason_code=SKIP_HOLE,
                evidence_refs=[f"target:{tid}", f"skip_reason:{SKIP_HOLE}"],
                compensating_path="media_ip_cta_omit",
                revisit_if=["cta_cover_needed"],
                decision_confidence=0.9,
                owner_stage="nugget_layup_compose",
            )
            notes.append({"action": "cta_hole_skip", "target_segment_id": tid})
            continue
        row["cta_cover"] = True
        row["cta_cover_regenerate"] = True
        row["clone_adjacency_exempt"] = True
        row["vo_shape"] = str(row.get("vo_shape") or "third_person")
        notes.append(
            {
                "action": "cta_cover_allow",
                "target_segment_id": tid,
                "line_id": row.get("line_id"),
            }
        )
        ctx.log(
            f"media_ip_cta: clone-adjacent cover flagged for {tid}; "
            "third-person regenerate does not count toward invoke cap",
            level="info",
            stage="nugget_layup_compose",
        )
    return out, notes


def nugget_from_never_touch(ctx: RunContext, nugget: dict[str, Any] | None) -> bool:
    if not isinstance(nugget, dict):
        return False
    sources = {str(x) for x in (nugget.get("source_segment_ids") or []) if x}
    return bool(sources & never_touch_segment_ids(ctx))


def _write_state(ctx: RunContext, state: dict[str, Any]) -> None:
    from interview_mux.artifact_writes import write_validated_artifact

    try:
        write_validated_artifact(
            ctx,
            ARTIFACT_REL,
            state,
            merge_from_disk=False,
            stage_key="full_master_ranking",
        )
    except Exception:
        ctx.write_json(ARTIFACT_REL, state)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"true", "yes", "1"}


def _segments_by_id(ctx: RunContext) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    try:
        from interview_mux.nle_state import segments_by_id_with_nle

        by_id = segments_by_id_with_nle(ctx)
    except Exception:
        by_id = {}
    if by_id:
        return by_id
    if not ctx.artifact_exists("segments/manifest.json"):
        return {}
    man = ctx.read_json("segments/manifest.json")
    return {
        str(s.get("segment_id")): s
        for s in ((man or {}).get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }


def _exclude_nle_ids(ctx: RunContext, segment_ids: list[str]) -> None:
    if not segment_ids:
        return
    try:
        from interview_mux.nle_state import load_nle, save_nle

        nle = load_nle(ctx)
        overrides = nle.setdefault("segment_overrides", {})
        drop = {str(s) for s in segment_ids if s}
        for sid in drop:
            row = dict(overrides.get(sid) or {})
            row["excluded"] = True
            overrides[sid] = row
        order = [str(s) for s in (nle.get("sequence_order") or []) if s]
        nle["sequence_order"] = [s for s in order if s not in drop]
        save_nle(ctx, nle)
    except Exception:
        pass


def _parent_bounds(ctx: RunContext, segment_id: str) -> tuple[int, int] | None:
    row = _segments_by_id(ctx).get(segment_id)
    if not row:
        return None
    try:
        start = int(row.get("start_ms") or 0)
        end = int(row.get("end_ms") or start)
    except (TypeError, ValueError):
        return None
    return start, end


def _recut_parent(
    ctx: RunContext,
    segment_id: str,
    judgment: dict[str, Any],
    region: str,
) -> tuple[list[str], str]:
    bounds = _parent_bounds(ctx, segment_id)
    if not bounds:
        return [], "missing_parent"
    start, end = bounds
    span = end - start
    if span < MIN_CHILD_MS * 2:
        return [], "too_short"
    cuts = [int(c) for c in (judgment.get("cut_ms") or []) if str(c).strip() != ""]
    cuts = [c for c in cuts if start + MIN_CHILD_MS <= c <= end - MIN_CHILD_MS]
    if not cuts:
        if region == "start":
            cuts = [start + max(MIN_CHILD_MS, span // 3)]
        elif region == "middle":
            a = start + max(MIN_CHILD_MS, span // 3)
            b = end - max(MIN_CHILD_MS, span // 3)
            cuts = [a, b] if b > a else [start + span // 2]
        else:
            cuts = [end - max(MIN_CHILD_MS, span // 3)]
    cuts = sorted(set(cuts))
    points = [start, *cuts, end]
    for a, b in zip(points, points[1:]):
        if b - a < MIN_CHILD_MS:
            return [], "child_too_short"
    from interview_mux.nle_state import load_nle, split_segment_at_cuts

    split_segment_at_cuts(ctx, segment_id, cuts)
    nle = load_nle(ctx)
    children = [
        str(x)
        for x in ((nle.get("segment_overrides") or {}).get(segment_id) or {}).get("split_into") or []
        if x
    ]
    return children, "ok"


def _cta_children(children: list[str], region: str) -> list[str]:
    if not children:
        return []
    if region == "start":
        return children[:1]
    if region == "middle":
        return children[1:-1] or children[-1:]
    return children[-1:]


def _cta_like_reason(reason: str) -> bool:
    key = str(reason or "").casefold().replace("-", "_")
    return any(
        token in key
        for token in (
            "media_ip_cta",
            "direct_listener_monetization",
            "perspective_direct_monetization",
            "direct_monetization",
        )
    )


def _cta_like_excluded_ids(artifacts: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for row in artifacts.get("excluded_segment_ids") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or "").strip()
        if sid and _cta_like_reason(str(row.get("reason") or "")):
            out.append(sid)
    return list(dict.fromkeys(out))


def _story_ids_from_recuts(recuts: list[Any]) -> list[str]:
    out: list[str] = []
    for recut in recuts:
        if not isinstance(recut, dict) or not recut.get("ok"):
            continue
        out.extend(str(c) for c in (recut.get("story_children") or []) if c)
    return list(dict.fromkeys(out))


def _recut_parent_ids(recuts: list[Any]) -> list[str]:
    return list(
        dict.fromkeys(
            str(r.get("parent_id") or "")
            for r in recuts
            if isinstance(r, dict) and r.get("ok") and r.get("parent_id")
        )
    )


def _exclude_id(row: Any) -> str:
    if isinstance(row, str):
        return row
    if isinstance(row, dict):
        return str(row.get("segment_id") or "")
    return ""


def _without_excluded_ids(excl: list[Any], ids: set[str]) -> list[Any]:
    if not ids:
        return list(excl)
    return [row for row in excl if _exclude_id(row) not in ids]


def _stamp_excludes(excl: list[Any], ids: list[str]) -> list[Any]:
    out = list(excl)
    have = {_exclude_id(row) for row in out}
    for sid in ids:
        if not sid:
            continue
        if sid not in have:
            out.append({"segment_id": sid, "reason": REASON})
            have.add(sid)
            continue
        for i, row in enumerate(out):
            if isinstance(row, dict) and str(row.get("segment_id") or "") == sid:
                out[i] = {**row, "reason": REASON}
            elif row == sid:
                out[i] = {"segment_id": sid, "reason": REASON}
    return out


def _admit_story_ids(
    ctx: RunContext,
    ordered: list[str],
    story_ids: list[str],
    drop_set: set[str],
) -> list[str]:
    """Put CTA-sanitized story remainder back on the master allow-list."""
    out = list(ordered)
    have = set(out)
    by_id = _segments_by_id(ctx)
    for sid in story_ids:
        if not sid or sid in drop_set or sid in have:
            continue
        start = 0
        try:
            start = int((by_id.get(sid) or {}).get("start_ms") or 0)
        except (TypeError, ValueError):
            start = 0
        idx = len(out)
        for i, other in enumerate(out):
            try:
                other_start = int((by_id.get(other) or {}).get("start_ms") or 0)
            except (TypeError, ValueError):
                other_start = 0
            if start < other_start:
                idx = i
                break
        out.insert(idx, sid)
        have.add(sid)
    return out


def _rewrite_chapter_ids(
    artifacts: dict[str, Any],
    id_map: dict[str, list[str]],
    drop_set: set[str],
    story_ids: list[str],
) -> None:
    del story_ids
    chapters = artifacts.get("chapters")
    if not isinstance(chapters, list):
        return
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        segs = [str(s) for s in (ch.get("segment_ids") or []) if s]
        if id_map:
            segs = _rewrite_order(segs, id_map)
        ch["segment_ids"] = list(dict.fromkeys(s for s in segs if s not in drop_set))


def _id_map_from_recuts(recuts: list[Any]) -> dict[str, list[str]]:
    id_map: dict[str, list[str]] = {}
    for recut in recuts:
        if not isinstance(recut, dict) or not recut.get("ok"):
            continue
        parent = str(recut.get("parent_id") or "").strip()
        kids = [str(c) for c in (recut.get("children") or []) if c]
        if parent and kids:
            id_map[parent] = kids
    return id_map


def _story_first_from_state(state: dict[str, Any]) -> str:
    if str(state.get("open_choice") or "") != "story_child_first":
        return ""
    parent = str(state.get("cta_open_parent") or "")
    for recut in state.get("recuts") or []:
        if not isinstance(recut, dict) or str(recut.get("parent_id") or "") != parent:
            continue
        kids = [str(c) for c in (recut.get("story_children") or []) if c]
        return kids[0] if kids else ""
    return ""


def _sync_cold_open(
    artifacts: dict[str, Any],
    drop_set: set[str],
    id_map: dict[str, list[str]],
    ordered: list[str],
) -> None:
    hook = str(artifacts.get("native_cold_open_segment_id") or "").strip()
    if not hook:
        return
    if hook in drop_set or hook in id_map:
        replacement = next((s for s in ordered if s not in drop_set), "")
        if replacement:
            artifacts["native_cold_open_segment_id"] = replacement
        else:
            artifacts.pop("native_cold_open_segment_id", None)


def _rewrite_order(ordered: list[str], id_map: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for sid in ordered:
        kids = id_map.get(sid)
        repl = kids if kids else [sid]
        for item in repl:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
    return out


def _cover_targets(
    ordered: list[str],
    dropped: list[str],
    id_map: dict[str, list[str]],
) -> list[str]:
    """Kept natives that immediately follow a CTA drop in the pre-filter order."""
    del id_map
    if not ordered or not dropped:
        return []
    drop_set = set(dropped)
    targets: list[str] = []
    for i, sid in enumerate(ordered):
        if sid not in drop_set:
            continue
        for later in ordered[i + 1 :]:
            if later not in drop_set:
                targets.append(later)
                break
    return list(dict.fromkeys(targets))


def _texts_for(ctx: RunContext, ids: list[str]) -> list[str]:
    by_id = _segments_by_id(ctx)
    out: list[str] = []
    for sid in ids:
        text = str((by_id.get(sid) or {}).get("text") or "").strip()
        if text:
            out.append(text)
    return out


def _tokens(text: str) -> set[str]:
    return {t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in (text or "")).split() if len(t) > 2}


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / float(min(len(a), len(b)))
