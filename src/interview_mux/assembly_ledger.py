"""Air-atom assembly ledger: EDL/mix pieces labeled by chapter + talking point."""

from __future__ import annotations

from typing import Any

from interview_mux.order_hash import ordered_segment_ids_hash
from interview_mux.reorder_bridges import build_reorder_bridges
from interview_mux.run_context import RunContext
from interview_mux.seam_glue import CHAPTER_SCALE_GAP_MS, is_chapter_scale_pair


def _segments_by_id(ctx: RunContext) -> dict[str, dict[str, Any]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return {}
    man = ctx.read_json("segments/manifest.json")
    return {
        str(s["segment_id"]): s
        for s in ((man or {}).get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }


def _chapter_spans(
    ordered: list[str],
    chapters_raw: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project chapter membership onto contiguous air-order spans."""
    if not ordered:
        return []
    # Prefer first chapter that claims each segment (stable by chapter order).
    seg_to_ch: dict[str, dict[str, Any]] = {}
    for i, ch in enumerate(chapters_raw):
        if not isinstance(ch, dict):
            continue
        cid = str(ch.get("chapter_id") or f"ch_{i + 1:02d}")
        title = str(ch.get("title") or ch.get("chapter_title") or f"Part {i + 1}")
        for sid in ch.get("segment_ids") or []:
            sid_s = str(sid)
            if sid_s and sid_s not in seg_to_ch:
                seg_to_ch[sid_s] = {"chapter_id": cid, "title": title}

    spans: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for sid in ordered:
        meta = seg_to_ch.get(sid) or {
            "chapter_id": "ch_unassigned",
            "title": "Unassigned",
        }
        if current is None or current["chapter_id"] != meta["chapter_id"]:
            current = {
                "chapter_id": meta["chapter_id"],
                "title": meta["title"],
                "segment_ids": [sid],
            }
            spans.append(current)
        else:
            current["segment_ids"].append(sid)
    return spans


def _talking_point_spans(
    ordered: list[str],
    topics: list[dict[str, Any]],
    chapter_spans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map content_brief topics onto contiguous runs inside chapter spans."""
    seg_to_topic: dict[str, dict[str, Any]] = {}
    for i, topic in enumerate(topics):
        if not isinstance(topic, dict):
            continue
        tid = str(topic.get("topic_id") or topic.get("id") or f"tp_{i + 1:02d}")
        name = str(topic.get("name") or topic.get("title") or f"Talking point {i + 1}")
        for sid in topic.get("segment_ids") or []:
            sid_s = str(sid)
            if sid_s and sid_s not in seg_to_topic:
                seg_to_topic[sid_s] = {"talking_point_id": tid, "title": name}

    # Fallback: one talking point per chapter span when topics don't cover.
    ch_of: dict[str, str] = {}
    for ch in chapter_spans:
        for sid in ch.get("segment_ids") or []:
            ch_of[str(sid)] = str(ch.get("chapter_id") or "")

    points: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for sid in ordered:
        topic = seg_to_topic.get(sid)
        if topic is None:
            cid = ch_of.get(sid) or "ch_unassigned"
            topic = {
                "talking_point_id": f"tp_{cid}",
                "title": f"Beat ({cid})",
            }
        cid = ch_of.get(sid) or "ch_unassigned"
        key = (cid, topic["talking_point_id"])
        if current is None or (current["chapter_id"], current["talking_point_id"]) != key:
            current = {
                "talking_point_id": topic["talking_point_id"],
                "title": topic["title"],
                "chapter_id": cid,
                "segment_ids": [sid],
            }
            points.append(current)
        else:
            current["segment_ids"].append(sid)
    return points


def _parent_ids_for_segment(
    sid: str,
    chapter_spans: list[dict[str, Any]],
    talking_points: list[dict[str, Any]],
) -> tuple[str, str]:
    chapter_id = "ch_unassigned"
    for ch in chapter_spans:
        if sid in (ch.get("segment_ids") or []):
            chapter_id = str(ch.get("chapter_id") or chapter_id)
            break
    tp_id = f"tp_{chapter_id}"
    for tp in talking_points:
        if sid in (tp.get("segment_ids") or []) and tp.get("chapter_id") == chapter_id:
            tp_id = str(tp.get("talking_point_id") or tp_id)
            break
    return chapter_id, tp_id


def _seam_index(
    ordered: list[str],
    segments_by_id: dict[str, dict[str, Any]],
    clips: list[dict[str, Any]],
    bridges: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Index speech→speech joins and whether glue atoms sit between them."""
    pair_meta = {}
    if isinstance(bridges, dict):
        for p in bridges.get("pairs") or []:
            if not isinstance(p, dict):
                continue
            a = str(p.get("after_id") or p.get("after_segment_id") or "")
            b = str(p.get("before_id") or p.get("before_segment_id") or "")
            if a and b:
                pair_meta[(a, b)] = p

    # Timeline positions of speech clips
    speech_pos: list[tuple[int, str, int, int]] = []
    for i, clip in enumerate(clips):
        if not isinstance(clip, dict) or clip.get("type") != "speech":
            continue
        sid = str(clip.get("segment_id") or "")
        if not sid:
            continue
        start = int(clip.get("timeline_start_ms") or 0)
        end = start + int(clip.get("duration_ms") or 0)
        speech_pos.append((i, sid, start, end))

    seams: list[dict[str, Any]] = []
    for idx in range(len(speech_pos) - 1):
        i_a, a, _a0, a1 = speech_pos[idx]
        i_b, b, b0, _b1 = speech_pos[idx + 1]
        meta = pair_meta.get((a, b))
        rebuilt = None
        if meta is None:
            # Contiguous source join — not a required bridge
            doc = build_reorder_bridges([a, b], segments_by_id)
            pairs = doc.get("pairs") or []
            if pairs:
                meta = pairs[0]
                rebuilt = True
        between = clips[i_a + 1 : i_b]
        glue_ids = [
            str(c.get("piece_id") or f"clip_{j}")
            for j, c in enumerate(between, start=i_a + 1)
            if isinstance(c, dict)
            and c.get("type") in {"vo_pickup", "transition"}
            and int(c.get("duration_ms") or 0) > 0
        ]
        requires = meta is not None
        naked = bool(requires and not glue_ids)
        gap = None
        if meta is not None:
            gap = meta.get("source_gap_ms")
        elif a in segments_by_id and b in segments_by_id:
            try:
                gap = int(segments_by_id[b].get("start_ms") or 0) - int(
                    segments_by_id[a].get("end_ms") or 0
                )
            except (TypeError, ValueError):
                gap = None
        seams.append(
            {
                "after_segment_id": a,
                "before_segment_id": b,
                "timeline_join_ms": a1,
                "gap_to_next_ms": max(0, b0 - a1),
                "source_gap_ms": gap,
                "requires_glue": requires,
                "chapter_scale": bool(meta and is_chapter_scale_pair(meta)),
                "glue_piece_ids": glue_ids,
                "naked": naked,
                "kind": (meta or {}).get("kind") if meta else "contiguous",
                "rebuilt_pair": bool(rebuilt),
            }
        )
    return seams


def build_assembly_ledger(ctx: RunContext, *, edl: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build master/assembly_ledger.json from EDL (+ chapter/topic labels)."""
    if edl is None:
        if not ctx.artifact_exists("master/edl.json"):
            raise FileNotFoundError("master/edl.json required for assembly ledger")
        edl = ctx.read_json("master/edl.json")
    if not isinstance(edl, dict):
        raise ValueError("edl must be a dict")

    ordered = [str(s) for s in (edl.get("ordered_segment_ids") or []) if s]
    clips_in = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
    segments_by_id = _segments_by_id(ctx)

    chapters_raw: list[dict[str, Any]] = []
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            chapters_raw = [c for c in (sel.get("chapters") or []) if isinstance(c, dict)]
    if not chapters_raw and ctx.artifact_exists("master/narrative_plan.json"):
        plan = ctx.read_json("master/narrative_plan.json")
        if isinstance(plan, dict):
            chapters_raw = [c for c in (plan.get("chapters") or []) if isinstance(c, dict)]

    topics: list[dict[str, Any]] = []
    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        if isinstance(brief, dict):
            topics = [t for t in (brief.get("topics") or []) if isinstance(t, dict)]

    chapter_spans = _chapter_spans(ordered, chapters_raw)
    talking_points = _talking_point_spans(ordered, topics, chapter_spans)

    volley_of: dict[str, str] = {}
    if ctx.artifact_exists("understanding/episode_structure.json"):
        es = ctx.read_json("understanding/episode_structure.json")
        if isinstance(es, dict):
            for v in es.get("speaker_volleys") or []:
                if not isinstance(v, dict):
                    continue
                vid = str(v.get("speaker_volley_id") or "")
                for sid in v.get("segment_ids") or []:
                    if sid and vid and str(sid) not in volley_of:
                        volley_of[str(sid)] = vid

    atoms: list[dict[str, Any]] = []
    current_speech_sid = ""
    for i, clip in enumerate(clips_in):
        ctype = str(clip.get("type") or "")
        piece_id = f"atom_{i:04d}_{ctype}"
        sid = ""
        if ctype == "speech":
            sid = str(clip.get("segment_id") or "")
            current_speech_sid = sid
        elif ctype == "vo_pickup":
            sid = str(clip.get("targets_segment_id") or current_speech_sid)
        elif ctype == "transition":
            sid = str(clip.get("after_segment_id") or current_speech_sid)
        else:
            sid = current_speech_sid

        chapter_id, tp_id = _parent_ids_for_segment(sid, chapter_spans, talking_points)
        seam_role = "content"
        if ctype == "silence":
            seam_role = "air"
        elif ctype in {"vo_pickup", "transition"}:
            seam_role = "glue"

        atom: dict[str, Any] = {
            "piece_id": piece_id,
            "type": ctype,
            "timeline_start_ms": int(clip.get("timeline_start_ms") or 0),
            "duration_ms": int(clip.get("duration_ms") or 0),
            "chapter_id": chapter_id,
            "talking_point_id": tp_id,
            "seam_role": seam_role,
        }
        if ctype == "speech":
            atom["segment_id"] = sid
            atom["source_start_ms"] = clip.get("source_start_ms")
            atom["source_end_ms"] = clip.get("source_end_ms")
            if sid in volley_of:
                atom["speaker_volley_id"] = volley_of[sid]
        elif ctype == "vo_pickup":
            atom["line_id"] = clip.get("line_id")
            atom["targets_segment_id"] = clip.get("targets_segment_id")
            atom["source_path"] = clip.get("source_path")
        elif ctype == "transition":
            atom["after_segment_id"] = clip.get("after_segment_id")
            atom["before_segment_id"] = clip.get("before_segment_id")
            atom["source_path"] = clip.get("source_path")
            atom["text"] = (clip.get("text") or "")[:160]
        elif ctype == "silence":
            atom["air_kind"] = clip.get("air_kind")
        atoms.append(atom)

    bridges = None
    if ctx.artifact_exists("understanding/reorder_bridges.json"):
        bridges = ctx.read_json("understanding/reorder_bridges.json")

    seams = _seam_index(ordered, segments_by_id, clips_in, bridges if isinstance(bridges, dict) else None)
    for seam in seams:
        a = seam["after_segment_id"]
        b = seam["before_segment_id"]
        glue: list[str] = []
        after_end = None
        before_start = None
        for atom in atoms:
            if atom["type"] == "speech" and atom.get("segment_id") == a:
                after_end = atom["timeline_start_ms"] + atom["duration_ms"]
            if atom["type"] == "speech" and atom.get("segment_id") == b:
                before_start = atom["timeline_start_ms"]
        if after_end is not None and before_start is not None:
            for atom in atoms:
                if atom["seam_role"] != "glue":
                    continue
                t0 = atom["timeline_start_ms"]
                if after_end <= t0 < before_start and atom["duration_ms"] > 0:
                    glue.append(atom["piece_id"])
        seam["glue_piece_ids"] = glue
        seam["naked"] = bool(seam.get("requires_glue") and not glue)

    naked = [s for s in seams if s.get("naked")]
    from interview_mux.order_hash import copy_order_lock, get_order_lock

    ledger: dict[str, Any] = {
        "version": 1,
        "order_content_hash": str(edl.get("order_content_hash") or ordered_segment_ids_hash(ordered)),
        "ordered_segment_ids": ordered,
        "timeline_duration_ms": int(edl.get("timeline_duration_ms") or 0),
        "chapters": chapter_spans,
        "talking_points": talking_points,
        "atoms": atoms,
        "seams": seams,
        "naked_seam_count": len(naked),
        "complete": len(naked) == 0,
        "chapter_scale_gap_ms": CHAPTER_SCALE_GAP_MS,
    }
    if get_order_lock(edl):
        ledger = copy_order_lock(edl, ledger)
    elif ctx.artifact_exists("master/selection.json"):
        try:
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict) and get_order_lock(sel):
                ledger = copy_order_lock(sel, ledger)
        except Exception:
            pass
    return ledger


def write_assembly_ledger(ctx: RunContext, *, edl: dict[str, Any] | None = None) -> dict[str, Any]:
    ledger = build_assembly_ledger(ctx, edl=edl)
    ctx.write_json("master/assembly_ledger.json", ledger)
    return ledger


def assert_ledger_no_naked_seams(ledger: dict[str, Any]) -> None:
    if ledger.get("complete"):
        return
    naked = [s for s in (ledger.get("seams") or []) if isinstance(s, dict) and s.get("naked")]
    sample = ", ".join(
        f"{s.get('after_segment_id')}->{s.get('before_segment_id')}" for s in naked[:6]
    )
    raise SystemExit(
        f"assembly_ledger: {len(naked)} naked seam(s) — audible glue required ({sample})"
    )
