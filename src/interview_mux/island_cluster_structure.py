"""Economy LLM structure adjudicate for dense high-value island multi-clusters.

LLM chooses topic unity + per-L fuse_side / hinge_attach only.
Exact cut timestamps are resolved from high-confidence flanks in code.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.high_value_speech_islands import high_value_speech_cfg
from interview_mux.run_context import RunContext

STAGE_KEY = "island_cluster_structure_adjudicate"
PROMPT_REL = "segmentation/island-cluster-structure-adjudicate.system.txt"
PACKETS_PATH = "analysis/island_cluster_structure_packets.json"
VERDICTS_PATH = "analysis/island_cluster_structure_verdicts.json"
LOCKED_SEAMS_PATH = "analysis/connector_fuse_locked_seams.json"

_FALLBACK_SYSTEM = """You structure high-value low-confidence speech islands for a podcast editor.

You receive ONE local multi-cluster packet (alternating high-conf / low-conf blocks) with
full in-span transcript text and metrics. Decide structure only — never invent timestamps
or words.

Rules:
- Return JSON only inside the required envelope.
- Use only IDs supplied in the packet (cluster_id, island_id, block_id, segment_id).
- Every low island in the packet must appear exactly once in assignments[].
- fuse_side ∈ {left, right}; never bridge a whole run — one neighbor per low island.
- hinge_attach ∈ {left, right, null} for a separating high-conf hinge between lows.
- Prefer absorbing every low island into a neighbor; never leave a low island standalone.
- When uncertain on topic unity, prefer same_conversation + left/right assignment.
- Judge only tape text + metrics + deterministic_hints.

Canonical artifacts shape:
{
  "cluster_id": "hvc_001",
  "topic_unity": "same_conversation|split_topics",
  "hinge_attach": "left|right|null",
  "cut_hinge_block_ids": [],
  "assignments": [
    {"island_id": "hvi_001", "fuse_side": "left", "rationale": "continues prior clause"}
  ],
  "rationale": "short cluster rationale"
}
"""


def structure_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    hv = high_value_speech_cfg(cfg)
    block = hv.get("island_cluster_structure")
    if not isinstance(block, dict):
        block = {}
    return {
        "llm_tier": "economy",
        "fail_open_deterministic": True,
        "lock_forced_seams": True,
        "max_block_chars": 48000,
        **block,
    }


def _ms(row: dict[str, Any], key: str) -> int:
    try:
        return int(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _word_text(w: dict[str, Any]) -> str:
    return str(w.get("text") or w.get("word") or "").strip()


def _load_words(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("transcript/full.json"):
        return []
    try:
        tr = ctx.read_json("transcript/full.json")
    except Exception:
        return []
    rows = (tr.get("words") or []) if isinstance(tr, dict) else []
    words = [w for w in rows if isinstance(w, dict) and _word_text(w)]
    words.sort(key=lambda w: (_ms(w, "start_ms"), _ms(w, "end_ms")))
    return words


def _load_segments(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return []
    try:
        man = ctx.read_json("segments/manifest.json")
    except Exception:
        return []
    segs = [
        s
        for s in ((man.get("segments") or []) if isinstance(man, dict) else [])
        if isinstance(s, dict) and s.get("segment_id")
    ]
    segs.sort(key=lambda s: (_ms(s, "start_ms"), str(s.get("segment_id"))))
    return segs


def _words_in_span(words: list[dict[str, Any]], start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    return [
        w
        for w in words
        if _ms(w, "start_ms") < int(end_ms) and _ms(w, "end_ms") > int(start_ms)
    ]


def _topic_overlap(a: dict[str, Any], b: dict[str, Any]) -> float:
    ta = {str(t).casefold() for t in (a.get("topic_tags") or []) if t}
    tb = {str(t).casefold() for t in (b.get("topic_tags") or []) if t}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


def _segment_richness(seg: dict[str, Any]) -> float:
    dur = max(0, _ms(seg, "end_ms") - _ms(seg, "start_ms"))
    topics = len(seg.get("topic_tags") or [])
    text_n = len(str(seg.get("text") or "").split())
    return float(dur) + 500.0 * topics + 50.0 * text_n


def _soft_json(ctx: RunContext, rel: str) -> dict[str, Any] | None:
    if not ctx.artifact_exists(rel):
        return None
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return None
    return doc if isinstance(doc, dict) else None


def _block_full_text(
    words: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    max_chars: int,
) -> tuple[str, list[dict[str, Any]]]:
    span_words = _words_in_span(words, start_ms, end_ms)
    rows = [
        {
            "text": _word_text(w),
            "start_ms": _ms(w, "start_ms"),
            "end_ms": _ms(w, "end_ms"),
            "confidence": w.get("confidence", w.get("conf")),
            "speaker_id": w.get("speaker_id") or w.get("speaker"),
        }
        for w in span_words
    ]
    text = " ".join(r["text"] for r in rows if r["text"])
    if not text:
        parts: list[str] = []
        for seg in segments:
            s0, s1 = _ms(seg, "start_ms"), _ms(seg, "end_ms")
            if s1 <= start_ms or s0 >= end_ms:
                continue
            t = str(seg.get("text") or "").strip()
            if t:
                parts.append(t)
        text = " ".join(parts)
    if max_chars > 0 and len(text) > max_chars:
        text = text[: max_chars - 20] + " …[truncated]"
        rows = rows[: max(1, len(rows) // 2)]
    return text, rows


def build_island_cluster_structure_packet(
    ctx: RunContext,
    cluster: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Richest available tape-local packet for one multi-cluster (scope A)."""
    s_cfg = structure_cfg(cfg)
    max_chars = int(s_cfg.get("max_block_chars") or 48000)
    words = _load_words(ctx)
    segments = _load_segments(ctx)
    by_id = {str(s["segment_id"]): s for s in segments}
    order = [str(s["segment_id"]) for s in segments]
    index_of = {sid: i for i, sid in enumerate(order)}

    c0, c1 = _ms(cluster, "start_ms"), _ms(cluster, "end_ms")
    touched = [str(s) for s in (cluster.get("segment_ids_touched") or []) if s in by_id]
    if not touched:
        touched = [
            sid
            for sid, seg in by_id.items()
            if not (_ms(seg, "end_ms") <= c0 or _ms(seg, "start_ms") >= c1)
        ]
        touched.sort(key=lambda sid: index_of.get(sid, 1 << 30))

    first_i = min((index_of[s] for s in touched if s in index_of), default=0)
    last_i = max((index_of[s] for s in touched if s in index_of), default=0)
    prev_id = order[first_i - 1] if first_i > 0 else None
    next_id = order[last_i + 1] if last_i + 1 < len(order) else None

    try:
        from interview_mux.segment_fuse import connector_fuse_cfg

        topic_floor = float(connector_fuse_cfg(cfg).get("same_topic_score_floor") or 0.15)
        max_gap = int(connector_fuse_cfg(cfg).get("max_seam_gap_ms") or 8000)
    except Exception:
        topic_floor = 0.15
        max_gap = 8000

    islands = [i for i in (cluster.get("islands") or []) if isinstance(i, dict)]
    low_doc = _soft_json(ctx, "analysis/low_conf_islands.json") or {}
    ranking = _soft_json(ctx, "analysis/low_conf_density_ranking.json") or {}
    must_keep = _soft_json(ctx, "analysis/low_conf_must_keep.json") or {}
    hv_boosts = _soft_json(ctx, "analysis/high_value_speech_boosts.json") or {}
    rank_by = {
        str(r.get("segment_id")): r
        for r in (ranking.get("ranking") or [])
        if isinstance(r, dict) and r.get("segment_id")
    }
    must_ids = {str(x) for x in (must_keep.get("must_keep_segment_ids") or [])}
    hv_must = {str(x) for x in (must_keep.get("high_value_segment_ids") or [])}
    boost_by = {
        str(r.get("segment_id")): r
        for r in (hv_boosts.get("priors") or [])
        if isinstance(r, dict) and r.get("segment_id")
    }

    # Build chronological low/high spans inside [prev.start or c0, next.end or c1].
    window_start = _ms(by_id[prev_id], "start_ms") if prev_id else c0
    window_end = _ms(by_id[next_id], "end_ms") if next_id else c1

    blocks: list[dict[str, Any]] = []
    cursor = window_start
    block_n = 0

    def _emit(role: str, start: int, end: int, *, island: dict[str, Any] | None = None) -> None:
        nonlocal block_n
        if end <= start:
            return
        block_n += 1
        full_text, word_rows = _block_full_text(
            words, segments, start_ms=start, end_ms=end, max_chars=max_chars
        )
        sids = [
            sid
            for sid, seg in by_id.items()
            if not (_ms(seg, "end_ms") <= start or _ms(seg, "start_ms") >= end)
        ]
        sids.sort(key=lambda sid: index_of.get(sid, 1 << 30))
        confs = [float(r["confidence"]) for r in word_rows if r.get("confidence") is not None]
        row: dict[str, Any] = {
            "block_id": f"blk_{block_n:03d}",
            "role": role,
            "start_ms": start,
            "end_ms": end,
            "duration_ms": max(0, end - start),
            "segment_ids": sids,
            "full_text": full_text,
            "words": word_rows,
            "word_count": len(word_rows),
            "mean_confidence": (sum(confs) / len(confs)) if confs else None,
        }
        if island is not None:
            row["island_id"] = island.get("island_id")
            for key in (
                "kind",
                "kinds",
                "cluster_kind",
                "tiers_fired",
                "failure_mode",
                "suspect_reason",
                "suspect_reasons",
                "mean_rms",
                "level_ratio",
                "source_island_id",
                "low_word_count",
                "low_ratio",
            ):
                if island.get(key) is not None:
                    row[key] = island.get(key)
        blocks.append(row)

    hinge_ids = set(str(x) for x in (cluster.get("hinge_segment_ids") or []) if x)
    if prev_id:
        _emit("outer_left_h", window_start, min(c0, _ms(by_id[prev_id], "end_ms")))

    for idx, island in enumerate(islands):
        i0, i1 = _ms(island, "start_ms"), _ms(island, "end_ms")
        if i0 > cursor:
            role = "hinge_h" if any(
                not (_ms(by_id[sid], "end_ms") <= cursor or _ms(by_id[sid], "start_ms") >= i0)
                for sid in hinge_ids
                if sid in by_id
            ) else "intervening_h"
            _emit(role, cursor, i0)
        _emit("low_island", i0, i1, island=island)
        cursor = max(cursor, i1)

    if next_id:
        _emit("outer_right_h", max(cursor, c1), window_end)
    elif c1 > cursor:
        _emit("intervening_h", cursor, c1)

    # Segment context
    seg_rows: list[dict[str, Any]] = []
    interest = list(
        dict.fromkeys(
            [
                *([prev_id] if prev_id else []),
                *touched,
                *([next_id] if next_id else []),
                *list(hinge_ids),
            ]
        )
    )
    for sid in interest:
        seg = by_id.get(sid)
        if not seg:
            continue
        rank = rank_by.get(sid) or {}
        boost = boost_by.get(sid) or {}
        seg_rows.append(
            {
                "segment_id": sid,
                "start_ms": _ms(seg, "start_ms"),
                "end_ms": _ms(seg, "end_ms"),
                "duration_ms": max(0, _ms(seg, "end_ms") - _ms(seg, "start_ms")),
                "text": str(seg.get("text") or ""),
                "speaker_id": seg.get("speaker_id") or seg.get("speaker"),
                "topic_tags": list(seg.get("topic_tags") or []),
                "retention": seg.get("retention"),
                "high_value_speech": bool(seg.get("high_value_speech")),
                "richness": _segment_richness(seg),
                "density_rank": rank.get("rank"),
                "density_percentile": rank.get("percentile"),
                "density": rank.get("density"),
                "must_keep": sid in must_ids,
                "high_value_must_keep": sid in hv_must,
                "ranking_boost": boost.get("soft_boost"),
                "importance_score": boost.get("importance_score"),
            }
        )

    pair_hints: list[dict[str, Any]] = []
    try:
        from interview_mux.gap_vo_prior_context import clause_continues_after, ends_hanging_setup
        from interview_mux.low_conf_islands import load_islands as _load_lci
        from interview_mux.segment_fuse import _island_hints, words_in_span
    except Exception:
        clause_continues_after = None  # type: ignore[assignment]
        ends_hanging_setup = None  # type: ignore[assignment]
        _load_lci = None  # type: ignore[assignment]
        _island_hints = None  # type: ignore[assignment]
        words_in_span = None  # type: ignore[assignment]

    low_islands: list[dict[str, Any]] = []
    if _load_lci is not None:
        try:
            low_islands = [
                i
                for i in (_load_lci(ctx).get("islands") or [])
                if isinstance(i, dict)
            ]
        except Exception:
            low_islands = []

    for a_sid, b_sid in zip(interest, interest[1:]):
        a, b = by_id.get(a_sid), by_id.get(b_sid)
        if not a or not b:
            continue
        gap = max(0, _ms(b, "start_ms") - _ms(a, "end_ms"))
        score = _topic_overlap(a, b)
        a_end, b_start = _ms(a, "end_ms"), _ms(b, "start_ms")
        hanging = False
        continues = False
        if ends_hanging_setup is not None and words_in_span is not None:
            a_words = words_in_span(words, _ms(a, "start_ms"), a_end)
            tail = " ".join(_word_text(w) for w in a_words[-16:]) if a_words else str(a.get("text") or "")
            hanging = bool(ends_hanging_setup(tail))
            if clause_continues_after is not None:
                continues = bool(words) and clause_continues_after(words, a_end)
        straddle = False
        loose = False
        if _island_hints is not None:
            straddle, loose = _island_hints(
                low_islands, earlier_end_ms=a_end, later_start_ms=b_start
            )
        pair_hints.append(
            {
                "earlier_segment_id": a_sid,
                "later_segment_id": b_sid,
                "topic_overlap_score": score,
                "source_gap_ms": gap,
                "gap_over_cap": gap > max_gap,
                "same_speaker": (a.get("speaker_id") or a.get("speaker"))
                == (b.get("speaker_id") or b.get("speaker")),
                "hanging_setup_end": hanging,
                "clause_continues_after": continues,
                "island_straddle": bool(straddle),
                "loose_cluster_on_seam": bool(loose),
            }
        )

    # Per-L deterministic defaults
    per_l: list[dict[str, Any]] = []
    for island in islands:
        i0, i1 = _ms(island, "start_ms"), _ms(island, "end_ms")
        core = [
            sid
            for sid in touched
            if sid in by_id
            and not (_ms(by_id[sid], "end_ms") <= i0 or _ms(by_id[sid], "start_ms") >= i1)
        ]
        core.sort(key=lambda sid: index_of.get(sid, 1 << 30))
        fi = min((index_of[s] for s in core if s in index_of), default=first_i)
        li = max((index_of[s] for s in core if s in index_of), default=last_i)
        left = order[fi - 1] if fi > 0 else prev_id
        right = order[li + 1] if li + 1 < len(order) else next_id
        neighbors = [n for n in (left, right) if n and n in by_id]
        richer = None
        if neighbors:
            richer = max(neighbors, key=lambda sid: _segment_richness(by_id[sid]))
            if (
                left
                and right
                and left in by_id
                and right in by_id
                and abs(_segment_richness(by_id[left]) - _segment_richness(by_id[right])) < 1e-6
            ):
                richer = left
        bridge_ok = False
        if left and right and left in by_id and right in by_id:
            bridge_ok = _topic_overlap(by_id[left], by_id[right]) >= topic_floor
        default_side = "left" if richer == left else ("right" if richer == right else "left")
        per_l.append(
            {
                "island_id": island.get("island_id"),
                "left_segment_id": left,
                "right_segment_id": right,
                "richer_neighbor_default": richer,
                "default_fuse_side": default_side,
                "bridge_eligible": bridge_ok,
            }
        )

    # Soft editorial context (window-filtered, best-effort) + shared attach helpers.
    soft: dict[str, Any] = {}
    speakers_in = {
        str(r.get("speaker_id") or "")
        for r in seg_rows
        if r.get("speaker_id")
    }
    roles = _soft_json(ctx, "understanding/speaker_roles.json") or _soft_json(
        ctx, "understanding/speakers.json"
    ) or _soft_json(ctx, "analysis/speaker_roles.json")
    if roles:
        soft["speaker_roles"] = roles
    brief = _soft_json(ctx, "understanding/content_context.json") or _soft_json(
        ctx, "understanding/content_brief.json"
    )
    if brief:
        soft["content_context_keys"] = sorted(str(k) for k in brief.keys())[:40]
        topics_in = {
            str(t).casefold()
            for r in seg_rows
            for t in (r.get("topic_tags") or [])
            if t
        }
        excerpt_fields = []
        for key in ("summary", "episode_thesis", "thesis", "themes", "topics"):
            if key in brief:
                excerpt_fields.append({key: brief.get(key)})
        if excerpt_fields:
            soft["content_context_excerpts"] = excerpt_fields
        soft["topics_in_window"] = sorted(topics_in)

    ideal = _soft_json(ctx, "understanding/ideal_cuts.json")
    if ideal:
        cuts = []
        for row in ideal.get("cuts") or ideal.get("ideal_cuts") or []:
            if not isinstance(row, dict):
                continue
            s0, s1 = _ms(row, "start_ms"), _ms(row, "end_ms")
            if s1 <= window_start or s0 >= window_end:
                continue
            cuts.append(
                {
                    "cut_id": row.get("cut_id") or row.get("id"),
                    "start_ms": s0,
                    "end_ms": s1,
                    "segment_id": row.get("segment_id"),
                    "label": row.get("label") or row.get("title"),
                }
            )
        if cuts:
            soft["ideal_cuts_in_window"] = cuts[:40]

    tps = _soft_json(ctx, "understanding/talking_points.json")
    if tps:
        tp_rows = []
        for row in tps.get("talking_points") or []:
            if not isinstance(row, dict):
                continue
            sids = [str(x) for x in (row.get("segment_ids") or [])]
            if not set(sids) & set(interest):
                continue
            tp_rows.append(
                {
                    "talking_point_id": row.get("talking_point_id") or row.get("id"),
                    "title": row.get("title") or row.get("label"),
                    "segment_ids": sids,
                }
            )
        if tp_rows:
            soft["talking_points_in_window"] = tp_rows[:40]

    # Window-filter spine / conversation / disfluency helpers when available.
    helper_payload: dict[str, Any] = {
        "cluster_id": cluster.get("cluster_id"),
        "window_start_ms": window_start,
        "window_end_ms": window_end,
        "segment_ids": interest,
    }
    try:
        from interview_mux.interview_spine.compact import compact_for_volley, load_spine

        spine_doc = load_spine(ctx)
        if spine_doc:
            compact = compact_for_volley(ctx, max_windows=4, max_chars=160)
            if isinstance(compact, dict):
                # Keep windows overlapping the cluster span when timestamps exist.
                windows = []
                for w in compact.get("windows") or []:
                    if not isinstance(w, dict):
                        continue
                    w0, w1 = _ms(w, "start_ms"), _ms(w, "end_ms")
                    if w1 and w0 and (w1 <= window_start or w0 >= window_end):
                        continue
                    windows.append(w)
                if windows:
                    compact = {**compact, "windows": windows[:4]}
                soft["interview_spine"] = compact
    except Exception:
        pass
    try:
        from interview_mux.conversation_context import attach_conversation_context

        helper_payload = attach_conversation_context(
            ctx, helper_payload, STAGE_KEY
        )
        for key in ("conversation_context", "speaker_context", "roles_brief"):
            if key in helper_payload:
                soft[key] = helper_payload[key]
    except Exception:
        pass
    try:
        from interview_mux.stage_input_helpers import attach_disfluency_context

        helper_payload = attach_disfluency_context(helper_payload, ctx)
        # Scope must-keep / island excerpts to in-window segment ids.
        mk = [
            sid
            for sid in (helper_payload.get("must_keep_segment_ids") or [])
            if str(sid) in set(interest)
        ]
        if mk:
            soft["must_keep_segment_ids_in_window"] = mk
        excerpts = []
        for row in helper_payload.get("stt_island_excerpts") or helper_payload.get(
            "disfluency_excerpts"
        ) or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("segment_id") or "") in set(interest) or not row.get("segment_id"):
                excerpts.append(row)
        if excerpts:
            soft["disfluency_excerpts_in_window"] = excerpts[:40]
        for key in ("vernacular_must_keep_ids", "stt_lexicon_island_ids"):
            if key in helper_payload:
                soft[key] = helper_payload[key]
    except Exception:
        pass
    _ = speakers_in  # available for future speaker-scoped role trim

    packet = {
        "task": (
            "Decide topic_unity and per-island fuse_side for this local multi-cluster. "
            "Do not invent timestamps; code will cut on high-confidence flanks."
        ),
        "cluster": {
            "cluster_id": cluster.get("cluster_id"),
            "density": cluster.get("density"),
            "member_island_ids": list(cluster.get("member_island_ids") or []),
            "start_ms": c0,
            "end_ms": c1,
            "segment_ids_touched": touched,
            "outer_left_segment_id": prev_id,
            "outer_right_segment_id": next_id,
            "separate_reason_before": cluster.get("separate_reason_before"),
            "separate_reason_after": cluster.get("separate_reason_after"),
            "hinge_segment_ids": list(cluster.get("hinge_segment_ids") or []),
            "hinge_attach_default": cluster.get("hinge_attach"),
        },
        "policy": {
            "same_topic_score_floor": topic_floor,
            "max_seam_gap_ms": max_gap,
            "never_invent_timestamps": True,
            "never_leave_low_island_standalone": True,
            "one_neighbor_only": True,
            "bridge_only_if_same_conversation": False,
        },
        "blocks": blocks,
        "segments": seg_rows,
        "pair_hints": pair_hints,
        "per_island_defaults": per_l,
        "low_conf_island_count": len(low_doc.get("islands") or []) if low_doc else 0,
        "soft_context": soft,
    }
    return packet


def deterministic_structure_for_cluster(
    cluster: dict[str, Any],
    packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail-open / simple-path structure: richer-neighbor per L."""
    defaults = {
        str(r.get("island_id")): r
        for r in ((packet or {}).get("per_island_defaults") or [])
        if isinstance(r, dict) and r.get("island_id")
    }
    assignments = []
    for iid in cluster.get("member_island_ids") or []:
        d = defaults.get(str(iid)) or {}
        side = str(d.get("default_fuse_side") or "left")
        if side not in {"left", "right"}:
            side = "left"
        assignments.append(
            {
                "island_id": str(iid),
                "fuse_side": side,
                "rationale": "deterministic richer-neighbor fallback",
            }
        )
    hinge = cluster.get("hinge_attach")
    if hinge not in {"left", "right"}:
        hinge = None
    return {
        "cluster_id": cluster.get("cluster_id"),
        "topic_unity": "same_conversation",
        "hinge_attach": hinge,
        "cut_hinge_block_ids": [],
        "assignments": assignments,
        "rationale": "deterministic_fallback",
        "adjudication_fallback": True,
    }


def parse_island_cluster_structure_envelope(
    envelope: dict[str, Any] | None,
    packet: dict[str, Any],
    cluster: dict[str, Any],
) -> dict[str, Any] | None:
    """Validate / coerce LLM artifacts into a usable structure verdict."""
    if not isinstance(envelope, dict):
        return None
    artifacts = envelope.get("artifacts")
    if not isinstance(artifacts, dict):
        # Accept flat artifact docs.
        artifacts = envelope if "assignments" in envelope or "topic_unity" in envelope else None
    if not isinstance(artifacts, dict):
        return None

    allowed_islands = {
        str(i)
        for i in (cluster.get("member_island_ids") or [])
        if i
    }
    allowed_blocks = {
        str(b.get("block_id"))
        for b in (packet.get("blocks") or [])
        if isinstance(b, dict) and b.get("block_id")
    }
    defaults = {
        str(r.get("island_id")): r
        for r in (packet.get("per_island_defaults") or [])
        if isinstance(r, dict) and r.get("island_id")
    }

    topic_unity = str(artifacts.get("topic_unity") or "").strip().casefold()
    if topic_unity in {"same", "same_topic", "same_flow"}:
        topic_unity = "same_conversation"
    if topic_unity in {"split", "different", "different_topics"}:
        topic_unity = "split_topics"
    if topic_unity not in {"same_conversation", "split_topics"}:
        topic_unity = "same_conversation"

    hinge = artifacts.get("hinge_attach")
    if hinge is not None:
        hinge = str(hinge).strip().casefold()
        if hinge in {"null", "none", ""}:
            hinge = None
        elif hinge not in {"left", "right"}:
            hinge = cluster.get("hinge_attach") if cluster.get("hinge_attach") in {
                "left",
                "right",
            } else None

    cut_hinges = []
    for bid in artifacts.get("cut_hinge_block_ids") or []:
        b = str(bid)
        if b in allowed_blocks:
            cut_hinges.append(b)

    raw_assign = artifacts.get("assignments") or []
    by_island: dict[str, dict[str, Any]] = {}
    if isinstance(raw_assign, list):
        for row in raw_assign:
            if not isinstance(row, dict):
                continue
            iid = str(row.get("island_id") or "")
            if iid not in allowed_islands:
                continue
            side = str(row.get("fuse_side") or "").strip().casefold()
            if side not in {"left", "right", "bridge"}:
                continue
            if side == "bridge":
                side = str((defaults.get(iid) or {}).get("default_fuse_side") or "left")
                if side not in {"left", "right"}:
                    side = "left"
            by_island[iid] = {
                "island_id": iid,
                "fuse_side": side,
                "rationale": str(row.get("rationale") or "")[:200],
            }

    assignments = []
    for iid in cluster.get("member_island_ids") or []:
        key = str(iid)
        if key in by_island:
            assignments.append(by_island[key])
            continue
        d = defaults.get(key) or {}
        side = str(d.get("default_fuse_side") or "left")
        if side not in {"left", "right"}:
            side = "left"
        assignments.append(
            {
                "island_id": key,
                "fuse_side": side,
                "rationale": "filled_missing_assignment",
            }
        )

    return {
        "cluster_id": str(artifacts.get("cluster_id") or cluster.get("cluster_id") or ""),
        "topic_unity": topic_unity,
        "hinge_attach": hinge,
        "cut_hinge_block_ids": cut_hinges,
        "assignments": assignments,
        "rationale": str(artifacts.get("rationale") or "")[:300],
        "adjudication_fallback": False,
    }


def adjudicate_island_cluster_structure(
    ctx: RunContext,
    cluster: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One economy LLM call per multi-cluster; simple clusters skip LLM + full packet."""
    s_cfg = structure_cfg(cfg)

    if str(cluster.get("density") or "") != "multi":
        # Lightweight deterministic path — no rich packet build / no LLM.
        verdict = deterministic_structure_for_cluster(cluster, packet=None)
        verdict["adjudication_fallback"] = True
        verdict["skip_reason"] = "simple_cluster"
        _append_verdict(ctx, verdict)
        return verdict

    packet = build_island_cluster_structure_packet(ctx, cluster, cfg=cfg)
    _append_packet(ctx, packet)

    fail_open = bool(s_cfg.get("fail_open_deterministic", True))
    envelope = _llm_structure_call(ctx, packet, cfg=s_cfg)
    parsed = parse_island_cluster_structure_envelope(envelope, packet, cluster)
    if parsed is None and fail_open:
        parsed = deterministic_structure_for_cluster(cluster, packet)
    if parsed is None:
        parsed = deterministic_structure_for_cluster(cluster, packet)
    _append_verdict(ctx, parsed)
    return parsed


def _llm_structure_call(
    ctx: RunContext,
    packet: dict[str, Any],
    *,
    cfg: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        from interview_mux.stages.llm_runner import load_system_prompt, run_prompt_envelope
    except Exception:
        return None
    try:
        from interview_mux.required_response_format import build_required_response_block

        format_block = build_required_response_block(
            STAGE_KEY, variant="full", task_kind="primary"
        )
    except Exception:
        format_block = ""

    try:
        base = load_system_prompt(PROMPT_REL, include_preamble=False)
    except Exception:
        base = _FALLBACK_SYSTEM
    system = f"{base.rstrip()}\n\n{format_block}".strip() if format_block else base
    user = json.dumps(packet, indent=2, ensure_ascii=False)
    tier = str(cfg.get("llm_tier") or "economy")

    response_format: dict[str, Any] | None
    try:
        from interview_mux.openai_structured_output import resolve_response_format

        # Use primary so composed json_schema resolves; fall back to json_object.
        response_format = resolve_response_format(STAGE_KEY, "primary")
    except Exception:
        response_format = None
    if not response_format:
        response_format = {"type": "json_object"}

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            envelope = run_prompt_envelope(
                STAGE_KEY,
                PROMPT_REL,
                user,
                ctx=ctx,
                include_preamble=False,
                task_kind="primary",
                explicit_tier=tier,
                bump_tier=False,
                response_format=response_format,
                system_override=system,
            )
            if isinstance(envelope, dict):
                return envelope
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            # Retry once with loose json_object if strict schema rejected.
            if attempt == 0 and response_format.get("type") == "json_schema":
                response_format = {"type": "json_object"}
                continue
            continue
    ctx.log(
        f"island_cluster_structure LLM unavailable: {last_exc}",
        level="warning",
        stage=STAGE_KEY,
        action_id="island_cluster.llm.fallback",
        detail={"error": str(last_exc)[:300] if last_exc else ""},
    )
    return None


def _append_packet(ctx: RunContext, packet: dict[str, Any]) -> None:
    doc = _soft_json(ctx, PACKETS_PATH) or {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "packets": [],
    }
    packets = [p for p in (doc.get("packets") or []) if isinstance(p, dict)]
    cid = str((packet.get("cluster") or {}).get("cluster_id") or "")
    packets = [p for p in packets if str((p.get("cluster") or {}).get("cluster_id")) != cid]
    packets.append(packet)
    doc["packets"] = packets
    doc["generated_at"] = datetime.now(timezone.utc).isoformat()
    ctx.write_json(PACKETS_PATH, doc)


def _append_verdict(ctx: RunContext, verdict: dict[str, Any]) -> None:
    doc = _soft_json(ctx, VERDICTS_PATH) or {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdicts": [],
    }
    rows = [v for v in (doc.get("verdicts") or []) if isinstance(v, dict)]
    cid = str(verdict.get("cluster_id") or "")
    rows = [v for v in rows if str(v.get("cluster_id")) != cid]
    rows.append(verdict)
    doc["verdicts"] = rows
    doc["generated_at"] = datetime.now(timezone.utc).isoformat()
    ctx.write_json(VERDICTS_PATH, doc)


def load_locked_seams(ctx: RunContext) -> set[str]:
    doc = _soft_json(ctx, LOCKED_SEAMS_PATH) or {}
    pairs = doc.get("pair_ids") or []
    return {str(p) for p in pairs if p}


def lock_seams(ctx: RunContext, pair_ids: list[str], *, pass_id: str = "") -> None:
    doc = _soft_json(ctx, LOCKED_SEAMS_PATH) or {
        "version": 1,
        "pair_ids": [],
        "entries": [],
    }
    existing = {str(p) for p in (doc.get("pair_ids") or []) if p}
    entries = [e for e in (doc.get("entries") or []) if isinstance(e, dict)]
    for pid in pair_ids:
        p = str(pid)
        if not p or p in existing:
            continue
        existing.add(p)
        entries.append(
            {
                "pair_id": p,
                "pass_id": pass_id or None,
                "locked_at": datetime.now(timezone.utc).isoformat(),
                "cut_source": "high_conf_flank",
            }
        )
    doc["pair_ids"] = sorted(existing)
    doc["entries"] = entries
    ctx.write_json(LOCKED_SEAMS_PATH, doc)


def high_conf_flank_cuts(
    ctx: RunContext,
    *,
    island_start_ms: int,
    island_end_ms: int,
    fuse_side: str,
    low_conf_threshold: float = 0.85,
) -> dict[str, int]:
    """Resolve exact cut timestamps from high-confidence word flanks."""
    words = _load_words(ctx)
    before = [
        w
        for w in words
        if _ms(w, "end_ms") <= island_start_ms
    ]
    after = [
        w
        for w in words
        if _ms(w, "start_ms") >= island_end_ms
    ]

    def _is_high(w: dict[str, Any]) -> bool:
        c = w.get("confidence", w.get("conf"))
        if c is None:
            return True  # missing conf treated as usable flank text
        try:
            return float(c) >= low_conf_threshold
        except (TypeError, ValueError):
            return True

    left_cut = island_start_ms
    for w in reversed(before):
        if _is_high(w):
            left_cut = _ms(w, "end_ms")
            break
    right_cut = island_end_ms
    for w in after:
        if _is_high(w):
            right_cut = _ms(w, "start_ms")
            break

    side = str(fuse_side or "left")
    if side == "left":
        return {"absorb_start_ms": left_cut, "absorb_end_ms": island_end_ms, "cut_ms": left_cut}
    if side == "right":
        return {"absorb_start_ms": island_start_ms, "absorb_end_ms": right_cut, "cut_ms": right_cut}
    # bridge: span from left H flank through right H flank
    return {"absorb_start_ms": left_cut, "absorb_end_ms": right_cut, "cut_ms": left_cut}


__all__ = [
    "LOCKED_SEAMS_PATH",
    "PACKETS_PATH",
    "PROMPT_REL",
    "STAGE_KEY",
    "VERDICTS_PATH",
    "adjudicate_island_cluster_structure",
    "build_island_cluster_structure_packet",
    "deterministic_structure_for_cluster",
    "high_conf_flank_cuts",
    "load_locked_seams",
    "lock_seams",
    "parse_island_cluster_structure_envelope",
    "structure_cfg",
]
