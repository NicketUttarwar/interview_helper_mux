"""One-shot chapter-close hitch: recut toward chapter/TP closes, remap ids, restage.

After the first ``narrative_arc_plan``, this host stage freezes that chapter map,
walks each keeper from its legal open to the last listen-complete hinge inside a
chapter/talking-point bound, republishes boundaries, rewires every ``seg_*``
consumer, invalidates stale delivery, restages through a second chapter plan
(QC only), and ships the **remapped original chapters**. Latched: never twice.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.segment_id_remap import (
    apply_segment_id_map,
    compose_segment_maps,
    rewrite_artifact_segment_refs,
    rewrite_embedded_segment_ids,
)
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

STAGE_ID = "chapter_close_hitch"
LATCH_REL = "mastering/chapter_close_hitch.json"
INTENT_REL = "mastering/chapter_close_hitch/intent_plan.json"
REMAP_REL = "mastering/chapter_close_hitch/remap.json"
PRE_KEEPERS_REL = "mastering/chapter_close_hitch/pre_keepers.json"
HITCH_KEEPERS_REL = "mastering/chapter_close_hitch/hitch_keepers.json"
VO_SNAPSHOT_REL = "mastering/chapter_close_hitch/vo_snapshot.json"
OMIT_SNAPSHOT_REL = "mastering/chapter_close_hitch/omit_ledger.json"
QC_PLAN_REL = "master/narrative_plan.qc.json"
NARRATIVE_REL = "master/narrative_plan.json"
BOUNDARIES_REL = "segments/boundaries.json"
MATERIALIZED_REL = "understanding/ideal_cuts_materialized.json"
MANIFEST_REL = "segments/manifest.json"

HITCH_PRESERVE_PREFIXES = (
    "mastering/chapter_close_hitch.json",
    "mastering/chapter_close_hitch/",
)



def hitch_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = ((cfg or merged_config()).get("mastering") or {}).get("chapter_close_hitch") or {}
    defaults: dict[str, Any] = {
        "enabled": True,
        "max_cut_ms": 180_000,
        "next_keeper_eps_ms": 80,
        "extend_hanging_horizon_ms": 8_000,
    }
    return {**defaults, **(raw if isinstance(raw, dict) else {})}


def hitch_listen_restage_count(ctx: RunContext) -> int:
    doc = _latch_doc(ctx)
    try:
        return int(doc.get("listen_restage_count") or 0)
    except (TypeError, ValueError):
        return 0


def arm_hitch_listen_restage(ctx: RunContext) -> bool:
    """Latch one hitch recut/merge restage. Returns False if already used."""
    prior = _latch_doc(ctx)
    try:
        count = int(prior.get("listen_restage_count") or 0)
    except (TypeError, ValueError):
        count = 0
    if count >= 1:
        return False
    payload = dict(prior) if prior else {"version": 1}
    payload["version"] = 1
    payload["status"] = "running"
    payload["listen_restage_count"] = 1
    payload["listen_restage"] = True
    payload["generated_at"] = payload.get("generated_at") or _now()
    _write_latch(ctx, payload)
    marker = ctx.final_path(".stage_done", STAGE_ID)
    if marker.is_file():
        marker.unlink(missing_ok=True)
    return True


def hitch_latch_committed(ctx: RunContext) -> bool:
    if not ctx.artifact_exists(LATCH_REL):
        return False
    doc = ctx.read_json(LATCH_REL)
    return isinstance(doc, dict) and str(doc.get("status") or "") == "committed"


def hitch_budget_identity(ctx: RunContext, identity: str) -> str:
    """Inner restage work bills the hitch, not nested stage identities."""
    if getattr(ctx, "_chapter_close_hitch_inner", False):
        return STAGE_ID
    return identity


def junction_snip_budget_identity(ctx: RunContext, identity: str) -> str:
    """Feel-audit LLM invokes nest under junction_snip_qa budget identity."""
    if identity == "junction_feel_audit" and getattr(ctx, "_junction_snip_qa_inner", False):
        return "junction_snip_qa"
    return identity


def hitch_restage_order() -> list[str]:
    """Stages restaged inside the hitch (boundary_detection → narrative_arc_plan)."""
    analysis = list(ANALYSIS_ORDER)
    delivery = list(DELIVERY_ORDER)
    start = analysis.index("boundary_detection")
    end_del = delivery.index("narrative_arc_plan")
    return analysis[start:] + delivery[: end_del + 1]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _word_list(transcript: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(transcript, dict):
        return []
    words = transcript.get("words") or []
    return [w for w in words if isinstance(w, dict)] if isinstance(words, list) else []


def last_listen_complete_end_ms(
    words: list[dict[str, Any]],
    *,
    start_ms: int,
    bound_end_ms: int,
    min_keep_ms: int = 2500,
) -> int | None:
    """Last listen-complete hinge in ``(start_ms, bound_end_ms]``, not the first pause.

    Hanging / same-clause continues are skipped. A later payoff in the bound
    wins over an earlier 1s breath. Returns None when no legal hinge fits.
    """
    from interview_mux.gap_vo_prior_context import (
        clause_continues_after,
        is_legal_conceptual_hinge,
        same_answer_continues,
    )

    cap = int(bound_end_ms)
    floor = int(start_ms)
    if cap <= floor + 300:
        return None
    window = [
        w
        for w in words
        if isinstance(w, dict)
        and floor < int(float(w.get("end_ms") or 0)) <= cap
        and str(w.get("text") or w.get("word") or "").strip()
    ]
    if not window:
        return None
    window.sort(key=lambda w: int(float(w.get("end_ms") or 0)))
    best: int | None = None
    accumulated: list[str] = []
    for i, w in enumerate(window):
        tok = str(w.get("text") or w.get("word") or "").strip()
        if tok:
            accumulated.append(tok)
        if not accumulated:
            continue
        cand_end = int(float(w.get("end_ms") or 0))
        if cand_end - floor < min_keep_ms:
            continue
        text = " ".join(accumulated)
        pause: int | None = None
        if i + 1 < len(window):
            pause = max(
                0,
                int(float(window[i + 1].get("start_ms") or 0)) - cand_end,
            )
        else:
            nxt = next(
                (
                    x
                    for x in words
                    if isinstance(x, dict) and int(float(x.get("start_ms") or 0)) > cand_end
                ),
                None,
            )
            if nxt is not None:
                pause = max(0, int(float(nxt.get("start_ms") or 0)) - cand_end)
        if not is_legal_conceptual_hinge(
            text, words=words, end_ms=cand_end, next_pause_ms=pause
        ):
            continue
        if clause_continues_after(words, cand_end):
            continue
        # Soft hang: period on a setup whose payoff is the next speech.
        if same_answer_continues(words, cand_end):
            continue
        best = cand_end
    return best


def _parse_topic_range_ms(text: str) -> tuple[int, int] | None:
    from interview_mux.topic_tag_bootstrap import _parse_approx_time_range_ms

    return _parse_approx_time_range_ms(text)


def _topic_end_ms_for_talking_point(
    brief: dict[str, Any] | None,
    talking_point_id: str,
    title: str,
) -> int | None:
    if not isinstance(brief, dict):
        return None
    needle = (talking_point_id or "").strip().lower()
    title_l = (title or "").strip().lower()
    for topic in brief.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        tid = str(topic.get("topic_id") or topic.get("id") or "").strip().lower()
        name = str(topic.get("name") or topic.get("title") or "").strip().lower()
        if needle and (tid == needle or needle in tid or tid in needle):
            parsed = _parse_topic_range_ms(str(topic.get("approx_time_range") or ""))
            if parsed:
                return parsed[1]
        if title_l and name and (title_l == name or title_l in name or name in title_l):
            parsed = _parse_topic_range_ms(str(topic.get("approx_time_range") or ""))
            if parsed:
                return parsed[1]
    return None


def _keepers_from_ctx(ctx: RunContext) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if ctx.artifact_exists(MANIFEST_REL):
        man = ctx.read_json(MANIFEST_REL)
        segs = (man or {}).get("segments") if isinstance(man, dict) else None
        if isinstance(segs, list):
            for s in segs:
                if not isinstance(s, dict) or not s.get("segment_id"):
                    continue
                rows.append(
                    {
                        "segment_id": str(s["segment_id"]),
                        "start_ms": int(s.get("start_ms") or 0),
                        "end_ms": int(s.get("end_ms") or 0),
                        "talking_point_id": str(s.get("talking_point_id") or ""),
                        "text": str(s.get("text") or ""),
                        "speaker_id": str(s.get("speaker_id") or s.get("speaker") or ""),
                    }
                )
    if not rows and ctx.artifact_exists(BOUNDARIES_REL):
        doc = ctx.read_json(BOUNDARIES_REL)
        for b in (doc or {}).get("boundaries") or []:
            if not isinstance(b, dict) or not b.get("segment_id"):
                continue
            rows.append(
                {
                    "segment_id": str(b["segment_id"]),
                    "start_ms": int(b.get("start_ms") or 0),
                    "end_ms": int(b.get("end_ms") or 0),
                    "talking_point_id": str(b.get("talking_point_id") or ""),
                    "text": "",
                    "speaker_id": str(b.get("speaker_id") or b.get("speaker") or ""),
                }
            )
    if ctx.artifact_exists(MATERIALIZED_REL):
        mat = ctx.read_json(MATERIALIZED_REL)
        by_sid: dict[str, dict[str, Any]] = {}
        for cut in (mat or {}).get("cuts") or []:
            if not isinstance(cut, dict):
                continue
            sid = str(cut.get("segment_id") or "").strip()
            if sid:
                by_sid[sid] = cut
        for row in rows:
            cut = by_sid.get(row["segment_id"])
            if cut:
                tp = str(cut.get("talking_point_id") or "").strip()
                if tp:
                    row["talking_point_id"] = tp
                row["cut_id"] = cut.get("cut_id")
                row["priority"] = cut.get("priority")
    rows.sort(key=lambda r: int(r.get("start_ms") or 0))
    return rows


def _chapter_membership(
    plan: dict[str, Any],
    keepers: list[dict[str, Any]],
) -> dict[str, str]:
    """segment_id → chapter_id (first claiming chapter)."""
    out: dict[str, str] = {}
    for ch in plan.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        cid = str(ch.get("chapter_id") or ch.get("id") or "").strip()
        if not cid:
            continue
        for sid in ch.get("segment_ids") or []:
            s = str(sid).strip()
            if s and s not in out:
                out[s] = cid
    return out


def _chapter_last_ids(plan: dict[str, Any], keepers: list[dict[str, Any]]) -> set[str]:
    by_id = {str(k.get("segment_id") or ""): k for k in keepers}
    last: set[str] = set()
    for ch in plan.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        ids = [str(s).strip() for s in (ch.get("segment_ids") or []) if str(s).strip()]
        timed = [s for s in ids if s in by_id]
        if timed:
            last.add(max(timed, key=lambda s: int(by_id[s].get("start_ms") or 0)))
        elif ids:
            last.add(ids[-1])
    return last


def _next_chapter_start_ms(
    plan: dict[str, Any],
    keepers: list[dict[str, Any]],
    chapter_id: str,
) -> int | None:
    chapters = [c for c in (plan.get("chapters") or []) if isinstance(c, dict)]
    idx = next(
        (
            i
            for i, ch in enumerate(chapters)
            if str(ch.get("chapter_id") or ch.get("id") or "") == chapter_id
        ),
        None,
    )
    if idx is None or idx + 1 >= len(chapters):
        return None
    nxt = chapters[idx + 1]
    ids = [str(s).strip() for s in (nxt.get("segment_ids") or []) if str(s).strip()]
    by_id = {str(k.get("segment_id")): k for k in keepers}
    starts = [int(by_id[s]["start_ms"]) for s in ids if s in by_id]
    return min(starts) if starts else None


def _extend_hanging_end_ms(
    words: list[dict[str, Any]],
    *,
    from_ms: int,
    horizon_ms: int,
) -> int | None:
    """First listen-complete close after a hanging keeper end, cross-speaker OK."""
    from interview_mux.thought_complete_recut import complete_thought_candidates

    if horizon_ms <= from_ms:
        return None
    cands = complete_thought_candidates(
        words, from_ms, horizon_ms=horizon_ms, speaker=""
    )
    if not cands:
        return None
    cut = int(cands[0])
    return cut if cut > from_ms else None


def _shrink_next_keeper_start(
    words: list[dict[str, Any]],
    *,
    keep_end_ms: int,
    next_row: dict[str, Any],
) -> None:
    """Push the next keeper open to leftover speech after an extended close."""
    from interview_mux.thought_complete_recut import remainder_open_ms

    next_end = int(next_row.get("end_ms") or 0)
    horizon = max(next_end, keep_end_ms + 1)
    rem = remainder_open_ms(
        words, keep_end_ms, horizon_ms=horizon, speaker=""
    )
    new_start = int(rem) if rem is not None else keep_end_ms
    new_start = max(new_start, keep_end_ms)
    if next_end and new_start >= next_end:
        next_row["start_ms"] = next_end
        return
    next_row["start_ms"] = new_start


def compute_recut_windows(
    *,
    keepers: list[dict[str, Any]],
    plan: dict[str, Any],
    words: list[dict[str, Any]],
    brief: dict[str, Any] | None = None,
    talking_points: dict[str, Any] | None = None,
    max_cut_ms: int = 180_000,
    min_keep_ms: int = 2500,
    next_keeper_eps_ms: int = 80,
    extend_hanging_horizon_ms: int | None = None,
) -> list[dict[str, Any]]:
    """Return keeper rows with updated ``end_ms`` aimed at chapter/TP close."""
    from interview_mux.gap_vo_prior_context import (
        end_is_hanging_clause,
        same_speaker_continuous_keep,
    )

    membership = _chapter_membership(plan, keepers)
    last_ids = _chapter_last_ids(plan, keepers)
    tp_titles: dict[str, str] = {}
    for tp in (talking_points or {}).get("talking_points") or []:
        if isinstance(tp, dict) and tp.get("talking_point_id"):
            tp_titles[str(tp["talking_point_id"])] = str(tp.get("title") or "")

    horizon = (
        int(extend_hanging_horizon_ms)
        if extend_hanging_horizon_ms is not None
        else int(hitch_cfg().get("extend_hanging_horizon_ms") or 8_000)
    )
    rows = [dict(r) for r in keepers if isinstance(r, dict)]
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        start = int(row.get("start_ms") or 0)
        end = int(row.get("end_ms") or start)
        orig_start = int(keepers[i].get("start_ms") or start)
        sid = str(row.get("segment_id") or "")
        next_start: int | None = None
        next_row: dict[str, Any] | None = None
        if i + 1 < len(rows):
            next_row = rows[i + 1]
            next_start = int(next_row.get("start_ms") or 0)
        cid = membership.get(sid, "")
        is_last = sid in last_ids
        tp_id = str(row.get("talking_point_id") or "")
        topic_end = _topic_end_ms_for_talking_point(
            brief, tp_id, tp_titles.get(tp_id, "")
        )
        hanging = bool(words) and end_is_hanging_clause(words, end)
        continuous_keep = bool(
            next_row is not None
            and words
            and same_speaker_continuous_keep(row, next_row, words)
        )
        leftover_after_extend = start > orig_start
        extended = False
        keep_merge = False
        bound = start + int(max_cut_ms)
        if leftover_after_extend:
            # Prior keeper already claimed the hanging close; leave the CTA/leftover slab.
            new_end = end
            bound = end
        elif hanging or continuous_keep:
            ext_horizon = min(end + horizon, start + int(max_cut_ms))
            if i + 1 < len(rows):
                ext_horizon = min(
                    ext_horizon, int(rows[i + 1].get("end_ms") or ext_horizon)
                )
            if continuous_keep and next_row is not None:
                payoff = int(next_row.get("end_ms") or next_start or end)
                ext_horizon = max(ext_horizon, payoff)
                ext_horizon = min(ext_horizon, start + int(max_cut_ms))
                keep_merge = True
            if topic_end is not None and topic_end > start and not continuous_keep:
                ext_horizon = min(ext_horizon, topic_end)
            ext_horizon = max(ext_horizon, end)
            bound = ext_horizon
            snapped = _extend_hanging_end_ms(
                words, from_ms=end, horizon_ms=ext_horizon
            )
            new_end = int(snapped) if snapped is not None else end
            if keep_merge:
                listen = last_listen_complete_end_ms(
                    words,
                    start_ms=start,
                    bound_end_ms=bound,
                    min_keep_ms=min_keep_ms,
                )
                if listen is not None and int(listen) > new_end:
                    new_end = int(listen)
                if next_row is not None and new_end < int(next_row.get("start_ms") or 0):
                    new_end = min(int(next_row.get("end_ms") or new_end), bound)
            extended = new_end > end
        else:
            if is_last and cid:
                nxt_ch = _next_chapter_start_ms(plan, rows, cid)
                if nxt_ch is not None:
                    bound = min(bound, nxt_ch - int(next_keeper_eps_ms))
                elif next_start is not None:
                    bound = min(bound, next_start - int(next_keeper_eps_ms))
            elif next_start is not None:
                bound = min(bound, next_start - int(next_keeper_eps_ms))
            if topic_end is not None and topic_end > start:
                bound = min(bound, topic_end)
            bound = max(bound, start + min_keep_ms)
            snapped = last_listen_complete_end_ms(
                words, start_ms=start, bound_end_ms=bound, min_keep_ms=min_keep_ms
            )
            new_end = int(snapped) if snapped is not None else end
            if next_start is not None:
                new_end = min(new_end, next_start - int(next_keeper_eps_ms))
        if new_end < start + min_keep_ms:
            new_end = end
            extended = False
        if next_start is not None and words:
            from interview_mux.cut_edge_refine import lift_end_for_outgoing_last_word
            from interview_mux.gap_vo_prior_context import (
                end_is_hard_hang,
                same_answer_continues,
            )

            soft = next_start - int(next_keeper_eps_ms)
            lifted, used = lift_end_for_outgoing_last_word(
                new_end,
                words,
                clip_start_ms=start,
                next_keeper_start_ms=next_start,
                proposed_end_ms=soft,
            )
            if used and lifted > new_end:
                new_end = lifted
                if new_end > next_start and i + 1 < len(rows):
                    _shrink_next_keeper_start(
                        words, keep_end_ms=new_end, next_row=rows[i + 1]
                    )
            # Phase 2: same-answer continuity — prefer one keeper through payoff.
            if same_answer_continues(words, new_end, next_start) and i + 1 < len(rows):
                next_end = int(rows[i + 1].get("end_ms") or next_start)
                ext_bound = min(int(bound), next_end, start + int(max_cut_ms))
                snapped = last_listen_complete_end_ms(
                    words,
                    start_ms=start,
                    bound_end_ms=ext_bound,
                    min_keep_ms=min_keep_ms,
                )
                if snapped is not None and snapped > new_end:
                    new_end = int(snapped)
                    extended = True
                    if new_end > next_start:
                        _shrink_next_keeper_start(
                            words, keep_end_ms=new_end, next_row=rows[i + 1]
                        )
            # Phase 1: never ship a hard hang after lift / extend.
            if end_is_hard_hang(words, new_end):
                snapped = last_listen_complete_end_ms(
                    words,
                    start_ms=start,
                    bound_end_ms=min(int(bound), start + int(max_cut_ms)),
                    min_keep_ms=min_keep_ms,
                )
                if snapped is not None and not end_is_hard_hang(words, int(snapped)):
                    new_end = int(snapped)
                else:
                    from interview_mux.thought_complete_recut import (
                        complete_thought_candidates,
                    )

                    cands = complete_thought_candidates(
                        words,
                        max(start, new_end - 500),
                        horizon_ms=min(
                            int(bound),
                            (next_start or new_end) + horizon,
                            start + int(max_cut_ms),
                        ),
                        speaker="",
                    )
                    for cut in cands:
                        if int(cut) > start + min_keep_ms and not end_is_hard_hang(
                            words, int(cut)
                        ):
                            new_end = int(cut)
                            break
        if (
            extended
            and next_start is not None
            and new_end > next_start - int(next_keeper_eps_ms)
            and i + 1 < len(rows)
        ):
            _shrink_next_keeper_start(
                words, keep_end_ms=new_end, next_row=rows[i + 1]
            )
        updated = dict(row)
        updated["end_ms"] = new_end
        updated["end_changed"] = new_end != int(keepers[i].get("end_ms") or end)
        updated["bound_end_ms"] = bound
        updated["last_in_chapter"] = is_last
        updated["chapter_id"] = cid
        updated["hanging_extended"] = extended
        updated["keep_merge"] = keep_merge
        out.append(updated)
    return out


def apply_acoustic_refine(
    windows: list[dict[str, Any]],
    words: list[dict[str, Any]],
    wav_path: Any | None,
) -> list[dict[str, Any]]:
    from pathlib import Path

    from interview_mux.cut_edge_refine import refine_cut_edges
    from interview_mux.ideal_cuts import ideal_cuts_cfg

    conf = ideal_cuts_cfg()
    acoustic_on = bool(conf.get("acoustic_edge_refine", True))
    search = int(conf.get("acoustic_search_ms") or 120)
    path = Path(wav_path) if wav_path else None
    out: list[dict[str, Any]] = []
    for i, row in enumerate(windows):
        start = int(row.get("start_ms") or 0)
        end = int(row.get("end_ms") or start)
        s2, e2, meta = refine_cut_edges(
            start_ms=start,
            end_ms=end,
            words=words,
            wav_path=path if path and path.is_file() else None,
            search_ms=search,
            apply_exact_words=bool(words),
            apply_acoustic=acoustic_on,
        )
        next_start = None
        if i + 1 < len(windows):
            try:
                next_start = int(windows[i + 1].get("start_ms") or 0)
            except (TypeError, ValueError):
                next_start = None
        if words:
            from interview_mux.cut_edge_refine import lift_end_for_outgoing_last_word

            lifted, used = lift_end_for_outgoing_last_word(
                e2,
                words,
                clip_start_ms=s2,
                next_keeper_start_ms=next_start,
                proposed_end_ms=e2,
            )
        if used:
            e2 = lifted
        if row.get("keep_merge") or row.get("hanging_extended"):
            prior_end = int(row.get("end_ms") or e2)
            if prior_end > e2:
                e2 = prior_end
        elif words and i + 1 < len(windows):
            from interview_mux.gap_vo_prior_context import (
                same_answer_continues,
                same_speaker_continuous_keep,
            )

            nxt = windows[i + 1]
            probe = dict(row)
            probe["end_ms"] = e2
            if same_speaker_continuous_keep(probe, nxt, words) or same_answer_continues(
                words, e2, next_start
            ):
                prior_end = int(row.get("end_ms") or e2)
                if prior_end > e2:
                    e2 = prior_end
        updated = dict(row)
        updated["start_ms"] = int(s2)
        updated["end_ms"] = int(e2)
        updated["edge_refine"] = meta
        out.append(updated)
    return out


def reapply_same_speaker_keep_merge(
    windows: list[dict[str, Any]],
    words: list[dict[str, Any]],
    *,
    max_cut_ms: int = 180_000,
) -> list[dict[str, Any]]:
    """Restore keep-merge after acoustic refine snaps an end back to a period."""
    from interview_mux.gap_vo_prior_context import same_speaker_continuous_keep

    out = [dict(r) for r in windows if isinstance(r, dict)]
    for i in range(len(out) - 1):
        left = out[i]
        right = out[i + 1]
        if not same_speaker_continuous_keep(left, right, words):
            continue
        start = int(left.get("start_ms") or 0)
        payoff = int(right.get("end_ms") or left.get("end_ms") or 0)
        desired = min(payoff, start + int(max_cut_ms))
        if desired <= int(left.get("end_ms") or 0):
            continue
        left["end_ms"] = desired
        left["keep_merge"] = True
        _shrink_next_keeper_start(words, keep_end_ms=desired, next_row=right)
    return out


def overlap_ms(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def build_segment_remap(
    old_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    *,
    must_keep_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Map old_id → new_id via talking_point_id + max overlap."""
    mapping: dict[str, str] = {}
    used_new: set[str] = set()
    unmatched_must: list[str] = []

    def _score(old: dict[str, Any], new: dict[str, Any]) -> int:
        ov = overlap_ms(
            int(old.get("start_ms") or 0),
            int(old.get("end_ms") or 0),
            int(new.get("start_ms") or 0),
            int(new.get("end_ms") or 0),
        )
        otp = str(old.get("talking_point_id") or "").strip()
        ntp = str(new.get("talking_point_id") or "").strip()
        if otp and ntp and otp == ntp:
            ov += 1_000_000
        return ov

    for old in old_rows:
        oid = str(old.get("segment_id") or "").strip()
        if not oid:
            continue
        best: tuple[int, str] | None = None
        for new in new_rows:
            nid = str(new.get("segment_id") or "").strip()
            if not nid or nid in used_new:
                continue
            sc = _score(old, new)
            if sc <= 0:
                continue
            if best is None or sc > best[0]:
                best = (sc, nid)
        if best is not None:
            mapping[oid] = best[1]
            used_new.add(best[1])
        elif oid in (must_keep_ids or set()):
            unmatched_must.append(oid)

    return {
        "old_to_new": mapping,
        "unmatched_must_keep_ids": unmatched_must,
        "new_ids": [str(r.get("segment_id") or "") for r in new_rows if r.get("segment_id")],
        "old_ids": [str(r.get("segment_id") or "") for r in old_rows if r.get("segment_id")],
    }


def rewrite_upstream_segment_refs(ctx: RunContext, mapping: dict[str, str]) -> list[str]:
    """Rewrite hitch-class artifacts plus shared consumers onto surviving ids."""
    return rewrite_artifact_segment_refs(
        ctx, mapping, extra_rels=(INTENT_REL,), skip_handoff=True
    )


def _mapping_from_remap_doc(remap_doc: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(remap_doc, dict):
        return {}
    return {
        str(k): str(v)
        for k, v in (remap_doc.get("old_to_new") or {}).items()
        if k and v
    }


def snapshot_pre_hitch_state(ctx: RunContext, keepers: list[dict[str, Any]]) -> None:
    """Freeze keepers, G1 VO lines, and omit ledger under the hitch prefix (survives wipe)."""
    ctx.write_json(PRE_KEEPERS_REL, {"keepers": keepers}, skip_handoff=True, stage_key=STAGE_ID)
    lines: list[dict[str, Any]] = []
    if ctx.artifact_exists("understanding/gap_report.json"):
        report = ctx.read_json("understanding/gap_report.json")
        if isinstance(report, dict):
            for row in report.get("interviewer_lines") or []:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    {
                        "line_id": str(row.get("line_id") or ""),
                        "targets_segment_id": str(row.get("targets_segment_id") or ""),
                        "skipped_optional": bool(row.get("skipped_optional")),
                        "skip_reason_code": str(row.get("skip_reason_code") or ""),
                        "delivery": str(row.get("delivery") or ""),
                        "text": str(row.get("text") or ""),
                    }
                )
    files: list[str] = []
    pickup = ctx.final_path("vo_pickup")
    if pickup.is_dir():
        for wav in sorted(pickup.rglob("*.wav")):
            try:
                files.append(wav.relative_to(ctx.run_dir).as_posix())
            except ValueError:
                files.append(str(wav))
    ctx.write_json(
        VO_SNAPSHOT_REL,
        {"interviewer_lines": lines, "vo_files": files},
        skip_handoff=True,
        stage_key=STAGE_ID,
    )
    if ctx.artifact_exists("understanding/omit_ledger.json"):
        ledger = ctx.read_json("understanding/omit_ledger.json")
        ctx.write_json(OMIT_SNAPSHOT_REL, ledger, skip_handoff=True, stage_key=STAGE_ID)


def load_pre_keepers(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists(PRE_KEEPERS_REL):
        return []
    doc = ctx.read_json(PRE_KEEPERS_REL)
    rows = (doc or {}).get("keepers") if isinstance(doc, dict) else None
    return [r for r in (rows or []) if isinstance(r, dict) and r.get("segment_id")]


def rebind_vo_pickup_files(ctx: RunContext, mapping: dict[str, str]) -> list[str]:
    """Copy G1 WAVs whose stems embed old ids onto the remapped names."""
    copied: list[str] = []
    if not mapping:
        return copied
    pickup = ctx.final_path("vo_pickup")
    if not pickup.is_dir():
        return copied
    wavs = [p for p in pickup.rglob("*.wav") if p.is_file()]
    for wav in wavs:
        new_stem = rewrite_embedded_segment_ids(wav.stem, mapping)
        if new_stem == wav.stem:
            continue
        dest = wav.with_name(new_stem + wav.suffix)
        if dest.resolve() == wav.resolve():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file():
            shutil.copy2(wav, dest)
            copied.append(dest.relative_to(ctx.run_dir).as_posix())
    return copied


def _resolve_snapshot_wav(ctx: RunContext, line: dict[str, Any], mapping: dict[str, str]) -> Path | None:
    from interview_mux.stages.assembly import resolve_vo_pickup_path

    candidates = [
        dict(line),
        {
            **line,
            "line_id": rewrite_embedded_segment_ids(str(line.get("line_id") or ""), mapping),
            "targets_segment_id": rewrite_embedded_segment_ids(
                str(line.get("targets_segment_id") or ""), mapping
            ),
        },
    ]
    for cand in candidates:
        found = resolve_vo_pickup_path(ctx, cand)
        if found is not None and found.is_file():
            return found
    pickup = ctx.final_path("vo_pickup")
    stems = [
        str(line.get("line_id") or ""),
        str(line.get("targets_segment_id") or ""),
        rewrite_embedded_segment_ids(str(line.get("line_id") or ""), mapping),
        rewrite_embedded_segment_ids(str(line.get("targets_segment_id") or ""), mapping),
    ]
    for stem in stems:
        if not stem:
            continue
        for base in (pickup / "matched", pickup / "synthesized", pickup / "clean", pickup / "normalized", pickup):
            cand = base / f"{stem}.wav"
            if cand.is_file():
                return cand
    return None


def reattach_vo_to_gap_report(ctx: RunContext, mapping: dict[str, str]) -> dict[str, Any]:
    """Keep recorded/synthesized G1 lines attached after gap_report is rebuilt."""
    snapshot: dict[str, Any] = {}
    if ctx.artifact_exists(VO_SNAPSHOT_REL):
        loaded = ctx.read_json(VO_SNAPSHOT_REL)
        if isinstance(loaded, dict):
            snapshot = loaded
    old_lines = [
        row
        for row in (snapshot.get("interviewer_lines") or [])
        if isinstance(row, dict) and (row.get("line_id") or row.get("targets_segment_id"))
    ]
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return {"copied": 0, "injected": 0, "stamped_skips": 0}
    report = ctx.read_json("understanding/gap_report.json")
    if not isinstance(report, dict):
        return {"copied": 0, "injected": 0, "stamped_skips": 0}
    lines = [row for row in (report.get("interviewer_lines") or []) if isinstance(row, dict)]
    by_target: dict[str, list[dict[str, Any]]] = {}
    by_line: dict[str, dict[str, Any]] = {}
    for row in lines:
        tid = str(row.get("targets_segment_id") or "")
        lid = str(row.get("line_id") or "")
        if tid:
            by_target.setdefault(tid, []).append(row)
        if lid:
            by_line[lid] = row
    copied = 0
    injected = 0
    stamped = 0
    pickup = ctx.final_path("vo_pickup")
    pickup.mkdir(parents=True, exist_ok=True)

    def _copy_to_line(src: Path, line: dict[str, Any]) -> None:
        nonlocal copied
        lid = str(line.get("line_id") or "")
        tid = str(line.get("targets_segment_id") or "")
        dest_stems = [s for s in (lid, tid) if s]
        for stem in dest_stems:
            dest = src.parent / f"{stem}{src.suffix}"
            if dest.resolve() == src.resolve():
                continue
            if not dest.is_file():
                shutil.copy2(src, dest)
                copied += 1
        if lid and not (pickup / f"{lid}.wav").is_file() and src.parent != pickup:
            raw_dest = pickup / f"{lid}.wav"
            if not raw_dest.is_file():
                shutil.copy2(src, raw_dest)
                copied += 1

    for old in old_lines:
        new_tid = rewrite_embedded_segment_ids(str(old.get("targets_segment_id") or ""), mapping)
        new_lid = rewrite_embedded_segment_ids(str(old.get("line_id") or ""), mapping)
        wav = _resolve_snapshot_wav(ctx, old, mapping)
        targets = list(by_target.get(new_tid) or [])
        if new_lid and new_lid in by_line and by_line[new_lid] not in targets:
            targets.append(by_line[new_lid])
        if targets:
            for row in targets:
                if wav is not None:
                    _copy_to_line(wav, row)
                if old.get("skipped_optional") and not row.get("skipped_optional"):
                    row["skipped_optional"] = True
                    if not row.get("skip_reason_code"):
                        row["skip_reason_code"] = str(old.get("skip_reason_code") or "hitch_remap")
                    stamped += 1
            continue
        if wav is None and not old.get("skipped_optional"):
            continue
        injected_line = dict(old)
        injected_line["line_id"] = new_lid or str(old.get("line_id") or "")
        injected_line["targets_segment_id"] = new_tid
        lines.append(injected_line)
        if new_tid:
            by_target.setdefault(new_tid, []).append(injected_line)
        if injected_line.get("line_id"):
            by_line[str(injected_line["line_id"])] = injected_line
        if wav is not None:
            _copy_to_line(wav, injected_line)
        injected += 1

    report["interviewer_lines"] = lines
    ctx.write_json("understanding/gap_report.json", report, skip_handoff=True)
    return {"copied": copied, "injected": injected, "stamped_skips": stamped}


def remap_omit_ledger(ctx: RunContext, mapping: dict[str, str]) -> bool:
    """Rewrite omit/skip subjects onto live segment and line ids."""
    rel = "understanding/omit_ledger.json"
    src = None
    if ctx.artifact_exists(rel):
        src = ctx.read_json(rel)
    elif ctx.artifact_exists(OMIT_SNAPSHOT_REL):
        src = ctx.read_json(OMIT_SNAPSHOT_REL)
    if not isinstance(src, dict):
        return False
    rewritten = apply_segment_id_map(src, mapping)
    if rewritten == src and ctx.artifact_exists(rel):
        return False
    try:
        from interview_mux.omit_ledger import write_omit_ledger

        write_omit_ledger(ctx, rewritten if isinstance(rewritten, dict) else src)
    except Exception:
        ctx.write_json(rel, rewritten, skip_handoff=True)
    ctx.write_json(OMIT_SNAPSHOT_REL, rewritten, skip_handoff=True, stage_key=STAGE_ID)
    return True


def align_episode_structure_to_narrative(
    ctx: RunContext,
    mapping: dict[str, str],
    new_ids: set[str],
) -> dict[str, Any]:
    """Keep slot bindings and segment_order on the remapped chapter map."""
    from interview_mux.episode_structure import (
        STRUCTURE_PATH,
        _segments,
        build_compact_digest,
        build_episode_structure,
        check_integrity,
        load_episode_structure,
        persist_structure,
        structure_enabled,
    )

    if not structure_enabled():
        return {"ok": True, "adopted": "disabled"}
    live_ids = set(new_ids)
    segs = _segments(ctx)
    if segs:
        live_ids = {str(s.get("segment_id") or "") for s in segs if s.get("segment_id")}
    plan = ctx.read_json(NARRATIVE_REL) if ctx.artifact_exists(NARRATIVE_REL) else {}
    chapters = [
        ch for ch in ((plan or {}).get("chapters") or []) if isinstance(ch, dict)
    ]
    chapter_order: list[str] = []
    seen: set[str] = set()
    for ch in chapters:
        for sid in ch.get("segment_ids") or []:
            s = str(sid).strip()
            if s in live_ids and s not in seen:
                chapter_order.append(s)
                seen.add(s)
    for sid in live_ids:
        if sid not in seen:
            chapter_order.append(sid)
            seen.add(sid)

    doc = load_episode_structure(ctx)
    if not isinstance(doc, dict):
        try:
            doc = build_episode_structure(ctx, refresh=False)
        except Exception as exc:
            return {"ok": False, "adopted": "missing", "error": str(exc)[:240]}

    doc = apply_segment_id_map(doc, mapping)
    if not isinstance(doc, dict):
        return {"ok": False, "adopted": "invalid"}

    def _filt(ids: list[Any]) -> list[str]:
        out: list[str] = []
        for item in ids:
            s = str(item).strip()
            if s in live_ids and s not in out:
                out.append(s)
        return out

    if chapter_order:
        doc["segment_order"] = chapter_order
    else:
        doc["segment_order"] = _filt(list(doc.get("segment_order") or []))

    first_open = ""
    if chapters:
        first_open = str(chapters[0].get("suggested_open_segment_id") or "")
        if first_open not in live_ids:
            ids0 = _filt(list(chapters[0].get("segment_ids") or []))
            first_open = ids0[0] if ids0 else ""
    hook = dict(doc.get("hook_reel") or {}) if isinstance(doc.get("hook_reel"), dict) else {}
    if first_open:
        hook["segment_id"] = first_open
        hook["repeat_allowed"] = bool(hook.get("repeat_allowed", True))
        doc["hook_reel"] = hook

    lasts: list[str] = []
    for ch in chapters:
        ids = _filt(list(ch.get("segment_ids") or []))
        if ids:
            lasts.append(ids[-1])
    for slot in doc.get("slot_plan") or []:
        if not isinstance(slot, dict):
            continue
        cid = str(slot.get("component_id") or "")
        bound = _filt(list(slot.get("bound_segment_ids") or []))
        if cid == "STD_act_body":
            bound = list(chapter_order)
        elif cid == "STD_chapter_hinge":
            bound = list(lasts)
        elif cid == "STD_cold_open_slot" and first_open:
            bound = [first_open]
            slot["repeat_allowed"] = True
        slot["bound_segment_ids"] = bound

    ok, flags = check_integrity(segs, list(doc.get("segment_order") or []))
    doc["integrity"] = {"ok": ok, "flags": flags}
    counts: dict[str, int] = {}
    for sid in doc.get("segment_order") or []:
        s = str(sid)
        counts[s] = counts.get(s, 0) + 1
    doc["occupancy"] = {
        "violations": [f"segment_id:{sid}:count={n}" for sid, n in counts.items() if n > 1]
    }
    doc["compact_digest"] = build_compact_digest(doc)
    try:
        persist_structure(ctx, doc, stage=STAGE_ID)
        return {"ok": True, "adopted": "aligned", "segment_count": len(doc.get("segment_order") or [])}
    except Exception as exc:
        try:
            rebuilt = build_episode_structure(ctx, refresh=False)
            persist_structure(ctx, rebuilt, stage=STAGE_ID)
            return {
                "ok": True,
                "adopted": "rebuilt",
                "error": str(exc)[:240],
                "segment_count": len((rebuilt or {}).get("segment_order") or []),
            }
        except Exception as exc2:
            ctx.write_json(STRUCTURE_PATH, doc, skip_handoff=True, stage_key=STAGE_ID)
            return {"ok": False, "adopted": "write_unvalidated", "error": str(exc2)[:240]}


def remap_homunculus_memory(ctx: RunContext, mapping: dict[str, str]) -> list[str]:
    """Rewrite leftover analysis memory so inner/later stages do not see ghost ids."""
    return rewrite_upstream_segment_refs(ctx, mapping)


def _ensure_inner_walk_gates(ctx: RunContext) -> None:
    """Inner restage must not re-block on G-Framing after the operator already passed G1."""
    try:
        from interview_mux.gap_vo_gates import (
            check_gap_framing_decision_pending,
            set_gap_framing_enabled,
        )
        from interview_mux.source_topology import (
            pickup_eligible_speaker_id,
            pickup_speaker_confirmed,
        )

        if check_gap_framing_decision_pending(ctx):
            enabled = True
            if ctx.artifact_exists("run_meta.json"):
                meta = ctx.read_json("run_meta.json")
                if isinstance(meta, dict) and "gap_framing_enabled" in meta:
                    enabled = bool(meta.get("gap_framing_enabled"))
            set_gap_framing_enabled(ctx, enabled)
        if not pickup_speaker_confirmed(ctx):
            sid = pickup_eligible_speaker_id(ctx)
            if sid:
                adapt = (
                    ctx.read_json("understanding/flow_adaptation.json")
                    if ctx.artifact_exists("understanding/flow_adaptation.json")
                    else {}
                )
                if isinstance(adapt, dict):
                    overrides = dict(adapt.get("operator_overrides") or {})
                    overrides["pickup_speaker_confirmed"] = True
                    adapt["operator_overrides"] = overrides
                    if not adapt.get("pickup_eligible_speaker_id"):
                        adapt["pickup_eligible_speaker_id"] = sid
                    ctx.write_json(
                        "understanding/flow_adaptation.json", adapt, skip_handoff=True
                    )
    except Exception:
        return


def refresh_live_remap(
    ctx: RunContext,
    old_keepers: list[dict[str, Any]],
    *,
    must_keep_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Re-match original keepers onto the post-walk manifest (fuse/resplit may churn ids)."""
    live = _keepers_from_ctx(ctx)
    hitch_rows: list[dict[str, Any]] = []
    if ctx.artifact_exists(HITCH_KEEPERS_REL):
        doc = ctx.read_json(HITCH_KEEPERS_REL)
        raw = (doc or {}).get("keepers") if isinstance(doc, dict) else None
        hitch_rows = [r for r in (raw or []) if isinstance(r, dict)]
    old_to_hitch: dict[str, str] = {}
    if ctx.artifact_exists(REMAP_REL):
        old_to_hitch = _mapping_from_remap_doc(ctx.read_json(REMAP_REL))
    hitch_to_live = _mapping_from_remap_doc(
        build_segment_remap(hitch_rows, live) if hitch_rows else {"old_to_new": {}}
    )
    old_to_live = _mapping_from_remap_doc(
        build_segment_remap(old_keepers, live, must_keep_ids=must_keep_ids)
    )
    combined = compose_segment_maps(old_to_hitch, hitch_to_live, old_to_live)
    unmatched = [
        str(k.get("segment_id") or "")
        for k in old_keepers
        if str(k.get("segment_id") or "") in (must_keep_ids or set())
        and str(k.get("segment_id") or "") not in combined
    ]
    remap_doc = {
        "old_to_new": combined,
        "unmatched_must_keep_ids": unmatched,
        "new_ids": [str(r.get("segment_id") or "") for r in live if r.get("segment_id")],
        "old_ids": [str(r.get("segment_id") or "") for r in old_keepers if r.get("segment_id")],
        "hitch_to_live": hitch_to_live,
    }
    ctx.write_json(REMAP_REL, remap_doc, skip_handoff=True, stage_key=STAGE_ID)
    return remap_doc


def remap_intent_plan(
    intent: dict[str, Any],
    mapping: dict[str, str],
    new_ids: set[str],
) -> tuple[dict[str, Any], list[str]]:
    """Rewrite intent chapter membership. Returns (plan, infeasible_reasons)."""
    remapped = apply_segment_id_map(intent, mapping)
    reasons: list[str] = []
    chapters = remapped.get("chapters") if isinstance(remapped, dict) else None
    if not isinstance(chapters, list) or not chapters:
        return remapped if isinstance(remapped, dict) else {"chapters": []}, ["no_chapters"]
    kept: list[dict[str, Any]] = []
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        ids = [str(s) for s in (ch.get("segment_ids") or []) if str(s) in new_ids]
        if not ids:
            reasons.append(f"empty_chapter:{ch.get('chapter_id')}")
            continue
        row = dict(ch)
        row["segment_ids"] = ids
        open_id = str(row.get("suggested_open_segment_id") or "")
        if open_id not in new_ids:
            row["suggested_open_segment_id"] = ids[0]
        kept.append(row)
    remapped = dict(remapped)
    remapped["chapters"] = kept
    if not kept:
        reasons.append("all_chapters_empty")
    cons = remapped.get("ordering_constraints")
    if isinstance(cons, list):
        cleaned = []
        for c in cons:
            if not isinstance(c, dict):
                continue
            a = str(c.get("before_segment_id") or "")
            b = str(c.get("after_segment_id") or "")
            if a in new_ids and b in new_ids:
                cleaned.append(c)
        remapped["ordering_constraints"] = cleaned
    return remapped, reasons


def _write_latch(ctx: RunContext, payload: dict[str, Any]) -> None:
    ctx.write_json(LATCH_REL, payload, skip_handoff=True, stage_key=STAGE_ID)


def _must_keep_ids(ctx: RunContext) -> set[str]:
    ids: set[str] = set()
    for rel, key in (
        ("understanding/ideal_cuts_selection_seed.json", "must_keep_segment_ids"),
        ("analysis/low_conf_must_keep.json", "must_keep_segment_ids"),
        ("analysis/low_conf_must_keep.json", "high_value_segment_ids"),
    ):
        if not ctx.artifact_exists(rel):
            continue
        doc = ctx.read_json(rel)
        if isinstance(doc, dict):
            ids.update(str(x) for x in (doc.get(key) or []) if x)
    return ids


def _publish_boundaries_from_windows(
    ctx: RunContext, windows: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    from interview_mux.ideal_cuts import boundaries_from_snapped_cuts

    cuts = []
    dropped_zero = 0
    for i, row in enumerate(windows):
        start = int(row.get("start_ms") or 0)
        end = int(row.get("end_ms") or start)
        if end <= start:
            dropped_zero += 1
            continue
        cuts.append(
            {
                "cut_id": row.get("cut_id") or f"hitch_cut_{i + 1:03d}",
                "talking_point_id": row.get("talking_point_id") or "",
                "start_ms": start,
                "end_ms": end,
                "priority": row.get("priority") or "should_keep",
                "rationale": "chapter_close_hitch",
                "split_reason": "chapter_close_hitch",
                "speaker_id": row.get("speaker_id") or "spk_0",
            }
        )
    cuts.sort(key=lambda c: (int(c["start_ms"]), int(c["end_ms"])))
    clamped: list[dict[str, Any]] = []
    prev_end: int | None = None
    overlap_clamped = 0
    for cut in cuts:
        start = int(cut["start_ms"])
        end = int(cut["end_ms"])
        if prev_end is not None and start < prev_end:
            start = prev_end
            overlap_clamped += 1
        if end <= start:
            dropped_zero += 1
            continue
        cut = {**cut, "start_ms": start, "end_ms": end}
        clamped.append(cut)
        prev_end = end
    cuts = clamped
    snapped = {"version": 1, "cuts": cuts, "snap_warnings": []}
    warnings: list[str] = []
    if dropped_zero:
        warnings.append(f"dropped {dropped_zero} zero-duration hitch window(s)")
    if overlap_clamped:
        warnings.append(f"clamped {overlap_clamped} overlapping hitch window(s)")
    snapped["snap_warnings"] = warnings
    boundaries = boundaries_from_snapped_cuts(snapped, publisher_stage=STAGE_ID)
    return boundaries, snapped


def _windows_from_boundaries(doc: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for b in (doc or {}).get("boundaries") or []:
        if not isinstance(b, dict) or not b.get("segment_id"):
            continue
        out.append(
            {
                "segment_id": str(b["segment_id"]),
                "start_ms": int(b.get("start_ms") or 0),
                "end_ms": int(b.get("end_ms") or 0),
                "talking_point_id": str(b.get("talking_point_id") or ""),
                "cut_id": b.get("cut_id"),
                "priority": b.get("priority"),
            }
        )
    return out


def _hitch_published_boundaries(ctx: RunContext) -> bool:
    if not ctx.artifact_exists(BOUNDARIES_REL):
        return False
    try:
        doc = ctx.read_json(BOUNDARIES_REL)
    except Exception:
        return False
    if not isinstance(doc, dict) or not (doc.get("boundaries") or []):
        return False
    meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
    contract = meta.get("segment_contract") if isinstance(meta.get("segment_contract"), dict) else {}
    return str(contract.get("publisher_stage") or "") == STAGE_ID


def run_inner_walk(ctx: RunContext, stages: list[str] | None = None) -> list[str]:
    """Restage host stages with the inner-stage flag so 0.1.0 budget is not burned."""
    from interview_mux.pipeline import run_single_stage

    order = list(stages or hitch_restage_order())
    ran: list[str] = []
    setattr(ctx, "_homunculus_inner_stage", True)
    setattr(ctx, "_chapter_close_hitch_inner", True)
    try:
        _ensure_inner_walk_gates(ctx)
        for stage in order:
            if stage == STAGE_ID:
                continue
            # Hitch already republished the timeline. Re-collating here undoes the
            # recut and can reintroduce zero-length windows from the LLM collate.
            if stage == "boundary_detection" and _hitch_published_boundaries(ctx):
                if not ctx.is_done(stage):
                    ctx.mark_done(stage, force=True)
                ctx.log(
                    "chapter_close_hitch: keeping hitch-published boundaries — skip recollate",
                    stage=STAGE_ID,
                )
                ran.append(stage)
                continue
            run_single_stage(ctx, stage)
            ran.append(stage)
    finally:
        if hasattr(ctx, "_homunculus_inner_stage"):
            delattr(ctx, "_homunculus_inner_stage")
        if hasattr(ctx, "_chapter_close_hitch_inner"):
            delattr(ctx, "_chapter_close_hitch_inner")
    return ran


def apply_post_walk_patches(
    ctx: RunContext,
    *,
    intent: dict[str, Any],
    mapping: dict[str, str],
    new_ids: set[str],
) -> dict[str, Any]:
    """VO, omit, chapters, episode structure, and leftover memory after restage."""
    vo_files: list[str] = []
    vo_gap: dict[str, Any] = {"copied": 0, "injected": 0, "stamped_skips": 0}
    omit_updated = False
    stamped = 0
    rewritten: list[str] = []
    try:
        vo_files = rebind_vo_pickup_files(ctx, mapping)
        vo_gap = reattach_vo_to_gap_report(ctx, mapping)
    except Exception as exc:
        vo_gap = {**vo_gap, "error": str(exc)[:240]}
    try:
        omit_updated = remap_omit_ledger(ctx, mapping)
    except Exception:
        omit_updated = False
    try:
        from interview_mux.omit_ledger import stamp_gap_report_omit_skips

        stamped = stamp_gap_report_omit_skips(ctx)
    except Exception:
        stamped = 0
    try:
        from interview_mux.vo_contract import clamp_hosted_seats_to_rendered_wavs

        clamp_hosted_seats_to_rendered_wavs(ctx)
    except Exception:
        pass
    try:
        rewritten = remap_homunculus_memory(ctx, mapping)
    except Exception:
        rewritten = []
    authority = apply_chapter_authority(
        ctx, intent=intent, mapping=mapping, new_ids=new_ids
    )
    try:
        structure = align_episode_structure_to_narrative(ctx, mapping, new_ids)
    except Exception as exc:
        structure = {"ok": False, "adopted": "error", "error": str(exc)[:240]}
    layup_adopt: dict[str, Any] = {}
    try:
        from interview_mux.nugget_layup import adopt_layup_plan_to_selection

        layup_adopt = adopt_layup_plan_to_selection(
            ctx, mapping=mapping, persist=True, stage="chapter_close_hitch"
        )
    except Exception as exc:
        layup_adopt = {"ok": False, "error": str(exc)[:240]}
    return {
        "vo_files": vo_files,
        "vo_gap": vo_gap,
        "omit_updated": omit_updated,
        "omit_stamped": stamped,
        "rewritten": rewritten,
        "chapter_authority": authority,
        "episode_structure": structure,
        "layup_adopt": layup_adopt,
    }


def apply_chapter_authority(
    ctx: RunContext,
    *,
    intent: dict[str, Any],
    mapping: dict[str, str],
    new_ids: set[str],
) -> dict[str, Any]:
    """Keep remapped intent; adopt QC plan only when intent is infeasible."""
    remapped, reasons = remap_intent_plan(intent, mapping, new_ids)
    qc: dict[str, Any] | None = None
    if ctx.artifact_exists(NARRATIVE_REL):
        live = ctx.read_json(NARRATIVE_REL)
        if isinstance(live, dict):
            qc = live
            ctx.write_json(QC_PLAN_REL, live, skip_handoff=True, stage_key=STAGE_ID)

    adopted = "remapped_intent"
    plan = remapped
    if reasons and qc and isinstance(qc.get("chapters"), list) and qc.get("chapters"):
        qc_ids: set[str] = set()
        for ch in qc.get("chapters") or []:
            if isinstance(ch, dict):
                qc_ids.update(str(s) for s in (ch.get("segment_ids") or []) if s)
        if qc_ids & new_ids:
            plan = qc
            adopted = "qc_plan"
        else:
            adopted = "remapped_intent_infeasible_qc_unusable"
    ctx.write_json(NARRATIVE_REL, plan, skip_handoff=True, stage_key="narrative_arc_plan")
    return {
        "adopted": adopted,
        "infeasible_reasons": reasons,
        "chapter_count": len(plan.get("chapters") or []) if isinstance(plan, dict) else 0,
    }


def _latch_doc(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(LATCH_REL):
        return {}
    doc = ctx.read_json(LATCH_REL)
    return doc if isinstance(doc, dict) else {}


def run_chapter_close_hitch(ctx: RunContext) -> None:
    conf = hitch_cfg()
    if hitch_latch_committed(ctx):
        ctx.log("chapter_close_hitch: latch committed — no-op", stage=STAGE_ID)
        if not ctx.is_done(STAGE_ID):
            ctx.mark_done(STAGE_ID, force=True)
        return
    if not bool(conf.get("enabled", True)):
        _write_latch(
            ctx,
            {
                "version": 1,
                "status": "committed",
                "seq": 1,
                "skipped": True,
                "reason": "disabled",
                "generated_at": _now(),
            },
        )
        ctx.mark_done(STAGE_ID, force=True)
        return
    if not ctx.artifact_exists(NARRATIVE_REL) and not ctx.artifact_exists(INTENT_REL):
        _write_latch(
            ctx,
            {
                "version": 1,
                "status": "committed",
                "seq": 1,
                "skipped": True,
                "reason": "no_narrative_plan",
                "generated_at": _now(),
            },
        )
        ctx.mark_done(STAGE_ID, force=True)
        return

    if ctx.artifact_exists(INTENT_REL):
        intent = ctx.read_json(INTENT_REL)
    else:
        intent = ctx.read_json(NARRATIVE_REL)
        ctx.write_json(INTENT_REL, intent, skip_handoff=True, stage_key=STAGE_ID)
    if not isinstance(intent, dict):
        intent = {"chapters": []}

    prior = _latch_doc(ctx)
    resume = str(prior.get("status") or "") == "running" and bool(prior.get("wiped"))
    resume_count = int(prior.get("resume_count") or 0)
    try:
        listen_restage_n = int(prior.get("listen_restage_count") or 0)
    except (TypeError, ValueError):
        listen_restage_n = 0
    listen_restage = bool(prior.get("listen_restage")) or (
        listen_restage_n >= 1 and str(prior.get("status") or "") == "running"
    )
    if resume:
        resume_count += 1

    if listen_restage:
        old_keepers = _keepers_from_ctx(ctx)
        if not ctx.artifact_exists(VO_SNAPSHOT_REL):
            snapshot_pre_hitch_state(ctx, old_keepers)
    else:
        old_keepers = load_pre_keepers(ctx)
        if not old_keepers:
            old_keepers = _keepers_from_ctx(ctx)
            snapshot_pre_hitch_state(ctx, old_keepers)
        elif not ctx.artifact_exists(VO_SNAPSHOT_REL):
            snapshot_pre_hitch_state(ctx, old_keepers)

    _write_latch(
        ctx,
        {
            "version": 1,
            "status": "running",
            "seq": 1,
            "generated_at": str(prior.get("generated_at") or _now()),
            "wiped": bool(prior.get("wiped")) if resume else False,
            "resume_count": resume_count,
        },
    )

    must_keep = _must_keep_ids(ctx)
    any_change = bool(prior.get("any_end_changed"))
    mapping: dict[str, str] = {}
    remap_doc: dict[str, Any]
    restaged: list[str] = []
    rewritten: list[str] = []

    can_resume = (
        resume
        and ctx.artifact_exists(REMAP_REL)
        and ctx.artifact_exists(BOUNDARIES_REL)
    )
    if can_resume:
        ctx.log("chapter_close_hitch: resume running latch — skip recut", stage=STAGE_ID)
        remap_doc = ctx.read_json(REMAP_REL)
        mapping = _mapping_from_remap_doc(remap_doc)
        rewritten = rewrite_upstream_segment_refs(ctx, mapping)
        rebind_vo_pickup_files(ctx, mapping)
        remap_omit_ledger(ctx, mapping)
    else:
        words: list[dict[str, Any]] = []
        if ctx.artifact_exists("transcript/full.json"):
            words = _word_list(ctx.read_json("transcript/full.json"))
        brief = (
            ctx.read_json("understanding/content_brief.json")
            if ctx.artifact_exists("understanding/content_brief.json")
            else None
        )
        tps = (
            ctx.read_json("understanding/talking_points.json")
            if ctx.artifact_exists("understanding/talking_points.json")
            else None
        )
        windows = compute_recut_windows(
            keepers=old_keepers,
            plan=intent,
            words=words,
            brief=brief if isinstance(brief, dict) else None,
            talking_points=tps if isinstance(tps, dict) else None,
            max_cut_ms=int(conf.get("max_cut_ms") or 180_000),
            next_keeper_eps_ms=int(conf.get("next_keeper_eps_ms") or 80),
            extend_hanging_horizon_ms=int(
                conf.get("extend_hanging_horizon_ms") or 8_000
            ),
        )
        wav = None
        try:
            wav = ctx.read_path("ingest", "normalized.wav")
        except Exception:
            wav = None
        windows = apply_acoustic_refine(windows, words, wav)
        windows = reapply_same_speaker_keep_merge(
            windows,
            words,
            max_cut_ms=int(conf.get("max_cut_ms") or 180_000),
        )

        any_change = any(bool(w.get("end_changed")) for w in windows)
        boundaries, snapped = _publish_boundaries_from_windows(ctx, windows)
        new_rows = _windows_from_boundaries(boundaries)
        remap_doc = build_segment_remap(
            old_keepers, new_rows, must_keep_ids=must_keep
        )
        ctx.write_json(REMAP_REL, remap_doc, skip_handoff=True, stage_key=STAGE_ID)
        ctx.write_json(
            HITCH_KEEPERS_REL,
            {"keepers": new_rows},
            skip_handoff=True,
            stage_key=STAGE_ID,
        )
        mapping = _mapping_from_remap_doc(remap_doc)

        combined = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
        ctx.clear_from("boundary_detection", combined)
        ctx.write_json(INTENT_REL, intent, skip_handoff=True, stage_key=STAGE_ID)
        ctx.write_json(REMAP_REL, remap_doc, skip_handoff=True, stage_key=STAGE_ID)
        ctx.write_json(
            HITCH_KEEPERS_REL, {"keepers": new_rows}, skip_handoff=True, stage_key=STAGE_ID
        )
        ctx.write_json(
            PRE_KEEPERS_REL, {"keepers": old_keepers}, skip_handoff=True, stage_key=STAGE_ID
        )
        ctx.write_json(BOUNDARIES_REL, boundaries, skip_handoff=True, stage_key=STAGE_ID)
        rewritten = rewrite_upstream_segment_refs(ctx, mapping)
        rebind_vo_pickup_files(ctx, mapping)
        remap_omit_ledger(ctx, mapping)
        ctx.write_json(
            MATERIALIZED_REL,
            {
                **snapped,
                "snapped": True,
                "hitch": True,
                "cut_count": len(snapped.get("cuts") or []),
            },
            skip_handoff=True,
            stage_key=STAGE_ID,
        )
        _write_latch(
            ctx,
            {
                "version": 1,
                "status": "running",
                "seq": 1,
                "generated_at": str(prior.get("generated_at") or _now()),
                "wiped": True,
                "resume_count": resume_count,
                "any_end_changed": any_change,
                "remap_count": len(mapping),
            },
        )

    restaged = run_inner_walk(ctx)

    remap_doc = refresh_live_remap(ctx, old_keepers, must_keep_ids=must_keep)
    mapping = _mapping_from_remap_doc(remap_doc)
    new_ids = {str(s) for s in (remap_doc.get("new_ids") or []) if s}
    if ctx.artifact_exists(MANIFEST_REL):
        man = ctx.read_json(MANIFEST_REL)
        if isinstance(man, dict):
            live = {
                str(s.get("segment_id") or "")
                for s in (man.get("segments") or [])
                if isinstance(s, dict) and s.get("segment_id")
            }
            if live:
                new_ids = live
    patches = apply_post_walk_patches(
        ctx, intent=intent, mapping=mapping, new_ids=new_ids
    )
    rewritten = list(dict.fromkeys(list(rewritten) + list(patches.get("rewritten") or [])))
    authority = patches.get("chapter_authority") or {}

    _write_latch(
        ctx,
        {
            "version": 1,
            "status": "committed",
            "seq": 1,
            "generated_at": _now(),
            "any_end_changed": any_change,
            "remap_count": len(mapping),
            "rewritten": rewritten,
            "restaged": restaged,
            "unmatched_must_keep_ids": list(remap_doc.get("unmatched_must_keep_ids") or []),
            "chapter_authority": authority,
            "vo_reattach": patches.get("vo_gap"),
            "omit_updated": bool(patches.get("omit_updated")),
            "episode_structure": patches.get("episode_structure"),
            "layup_adopt": patches.get("layup_adopt"),
            "resume_count": resume_count,
            "listen_restage_count": listen_restage_n,
            "listen_restage": bool(listen_restage),
        },
    )
    ctx.mark_done(STAGE_ID, force=True)
    try:
        from interview_mux.remediation_framework import reconcile_invalidated_bundle

        reconcile_invalidated_bundle(ctx, [STAGE_ID], reason="chapter_close_hitch")
    except Exception:
        pass
    ctx.log(
        f"chapter_close_hitch: committed remap={len(mapping)} restage={len(restaged)} "
        f"authority={authority.get('adopted')}",
        stage=STAGE_ID,
    )
