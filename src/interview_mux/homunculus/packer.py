"""Deterministic volley packer: conductor picks fact IDs; code renders turns."""

from __future__ import annotations

import json
from typing import Any

from interview_mux.homunculus.admit import memory_facts, read_admitted
from interview_mux.homunculus.ledger import append_ledger, packet_hash_for
from interview_mux.run_context import RunContext
from interview_mux.volley_packet_lint import strip_forbidden_metadata

PACKS_REL = "mastering/homunculus/volley_packs"
_RANKING_TOOLS = frozenset(
    {
        "full_master_ranking",
        "ranking",
        "selection",
        "edl",
        "nugget_layup_compose",
        "nugget_corpus_mine",
    }
)
_MIX_TOOLS = frozenset({"mix", "master_finalize", "end_judgment", "complete_master"})
_GAP_EVAL_TOOLS = frozenset(
    {
        "missing_framing",
        "gap_framing_compose",
        "optimal_questions",
    }
)
_SPINE_TOOLS = _RANKING_TOOLS | {
    "topic_coverage_audit",
    "narrative_arc_plan",
    "edl_narrative_audit",
} | _GAP_EVAL_TOOLS
_HOST_PACKET_MARKERS = (
    "natives",
    "ordered_segment_ids",
    "nugget_corpus",
    "opening_owner",
    "already_aired",
    "key_claims",
    "segment_ids",
    "_layup_compose_shard",
    "speaker_role",
    "content_brief",
    "vo_coverage",
    "air_script_vo_seats",
    "interviewer_lines",
    "prior_native_contexts",
    "target_native_contexts",
    "vo_missions",
    "gap_evaluations",
    "gap_framing_policy",
)


def bootstrap_g0_text(ctx: RunContext) -> str:
    for rel in (
        "transcript/full.json",
        "transcripts/g0_reviewed.json",
        "transcript_review/reviewed.json",
        "ingest/transcript.json",
        "transcripts/index.json",
    ):
        if not ctx.artifact_exists(rel):
            continue
        try:
            data = ctx.read_json(rel)
        except Exception:
            continue
        timed = _timestamped_transcript(data)
        if timed.strip():
            return timed
        text = _extract_text(data)
        if text.strip():
            return text
    return ""


def g0_closed(ctx: RunContext) -> bool:
    """True only after transcript review is signed off *and* a real transcript exists.

    ``check_transcript_review_pending`` is false both when G0 is done and when
    the review queue has not been built yet. Treating the latter as closed made
    0.1.0 refuse (and hollow-mark) transcribe/ingest on a fresh run.
    """
    if not ctx.is_done("transcript_review"):
        return False
    return bool(bootstrap_g0_text(ctx))


def _inject_bootstrap_facts(ctx: RunContext, available: dict[str, dict[str, Any]]) -> None:
    if g0_closed(ctx):
        g0_text = bootstrap_g0_text(ctx)
        if g0_text:
            available.setdefault(
                "g0_transcript",
                {"fact_id": "g0_transcript", "identity": "g0_transcript", "meaning": g0_text},
            )
    for kid in operator_must_keep_ids(ctx):
        available.setdefault(
            kid,
            {"fact_id": kid, "identity": "must_keep", "meaning": kid},
        )
    from interview_mux.homunculus.source_card import read_source_card

    card = read_source_card(ctx)
    if card:
        available.setdefault(
            "source_card",
            {"fact_id": "source_card", "identity": "source_card", "meaning": card},
        )
    try:
        from interview_mux.homunculus.kb import lessons

        for row in lessons(ctx):
            fid = str(row.get("lesson_id") or "")
            if fid:
                available.setdefault(
                    fid,
                    {"fact_id": fid, "identity": "kb_lesson", "meaning": row},
                )
    except Exception:
        pass
    if ctx.artifact_exists("analysis/low_conf_must_keep.json"):
        mk = ctx.read_json("analysis/low_conf_must_keep.json")
        available.setdefault(
            "low_conf_must_keep",
            {"fact_id": "low_conf_must_keep", "identity": "low_conf_must_keep", "meaning": mk},
        )
    if ctx.artifact_exists("analysis/high_value_speech_islands.json"):
        hv = ctx.read_json("analysis/high_value_speech_islands.json")
        available.setdefault(
            "language_islands",
            {"fact_id": "language_islands", "identity": "language_islands", "meaning": hv},
        )
    brief = _compact_content_brief(ctx)
    if brief:
        available.setdefault(
            "content_brief",
            {"fact_id": "content_brief", "identity": "content_brief", "meaning": brief},
        )
    manifest = _compact_segment_manifest(ctx)
    if manifest:
        available.setdefault(
            "segment_manifest",
            {"fact_id": "segment_manifest", "identity": "segment_manifest", "meaning": manifest},
        )
    selection = _compact_selection(ctx)
    if selection:
        available.setdefault(
            "selection",
            {"fact_id": "selection", "identity": "selection", "meaning": selection},
        )
    corpus = _compact_nugget_corpus(ctx)
    if corpus:
        available.setdefault(
            "nugget_corpus",
            {"fact_id": "nugget_corpus", "identity": "nugget_corpus", "meaning": corpus},
        )
    cta = _compact_media_ip_cta(ctx)
    if cta:
        available.setdefault(
            "media_ip_cta",
            {"fact_id": "media_ip_cta", "identity": "media_ip_cta", "meaning": cta},
        )
    hints = _compact_editorial_omit_hints(ctx)
    if hints:
        available.setdefault(
            "editorial_omit_hints",
            {
                "fact_id": "editorial_omit_hints",
                "identity": "editorial_omit_hints",
                "meaning": hints,
            },
        )


def heuristic_axes(tool_id: str, card: dict[str, Any] | None) -> list[str]:
    axes = ["source_card"]
    circumstances = [str(x).lower() for x in (card or {}).get("circumstances") or []]
    if any(c in circumstances for c in ("panel", "monologue", "sparse_host", "guest_heavy")):
        axes.append("topology")
    if "language_islands" in circumstances or (card or {}).get("language_islands"):
        axes.append("language_islands")
    if "noisy" in circumstances or "video" in circumstances:
        axes.append("acoustics")
    if "short" in circumstances or "long" in circumstances:
        axes.append("duration")
    if tool_id in _RANKING_TOOLS:
        axes.extend(["language_islands", "must_keep"])
    if tool_id in _MIX_TOOLS:
        axes.extend(["lessons", "acoustics"])
    seen: list[str] = []
    for a in axes:
        if a not in seen:
            seen.append(a)
    return seen


def default_pack_fact_ids(ctx: RunContext, tool_id: str) -> list[str]:
    from interview_mux.homunculus.source_card import read_source_card

    card = read_source_card(ctx)
    axes = heuristic_axes(tool_id, card)
    ids: list[str] = []
    # Gap eval needs classified segment_id + speaker_role. A timestamped G0
    # word dump (transcript.segments often empty) makes the nested LLM ask
    # to rerun segment_classification even when the manifest is complete.
    if g0_closed(ctx) and bootstrap_g0_text(ctx) and tool_id not in _GAP_EVAL_TOOLS:
        ids.append("g0_transcript")
    for kid in _explicit_must_keep_ids(ctx)[:12]:
        ids.append(kid)
    if card:
        ids.append("source_card")
    if tool_id in _SPINE_TOOLS:
        if ctx.artifact_exists("understanding/content_brief.json"):
            ids.append("content_brief")
        if ctx.artifact_exists("segments/manifest.json"):
            ids.append("segment_manifest")
        if tool_id in {"nugget_layup_compose", "nugget_corpus_mine", "full_master_ranking", "ranking", "selection"}:
            if ctx.artifact_exists("master/selection.json"):
                ids.append("selection")
            if ctx.artifact_exists("understanding/nugget_corpus.json") and tool_id in {
                "nugget_layup_compose",
                "nugget_corpus_mine",
            }:
                ids.append("nugget_corpus")
            if ctx.artifact_exists("mastering/media_ip_cta.json"):
                ids.append("media_ip_cta")
        if tool_id in _RANKING_TOOLS and ctx.artifact_exists("master/selection.json"):
            ids.append("editorial_omit_hints")
    if "language_islands" in axes:
        if ctx.artifact_exists("analysis/low_conf_must_keep.json"):
            ids.append("low_conf_must_keep")
        if ctx.artifact_exists("analysis/high_value_speech_islands.json"):
            ids.append("language_islands")
    if "lessons" in axes or tool_id in _MIX_TOOLS:
        from interview_mux.homunculus.kb import lesson_ids

        ids.extend(lesson_ids(ctx))
    seen: list[str] = []
    for i in ids:
        if i and i not in seen:
            seen.append(i)
    return seen


def select_axes(ctx: RunContext, tool_id: str) -> dict[str, Any]:
    """Heuristic axis pick (no network). Conductor may override via pack_volley fact_ids."""
    from interview_mux.homunculus.source_card import read_source_card

    card = read_source_card(ctx)
    axes = heuristic_axes(tool_id, card)
    fact_ids = default_pack_fact_ids(ctx, tool_id)
    return {"axes": axes, "fact_ids": fact_ids, "reason": f"heuristic for {tool_id}"}


def apply_pack_to_kwargs(ctx: RunContext, identity: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Render packed facts into the user turn. Keep a real host stage packet when present."""
    from interview_mux.homunculus.ledger import last_fact_ids_for_tool

    tool_id = identity.split("axis_select:", 1)[-1] if identity.startswith("axis_select:") else identity
    extras = last_fact_ids_for_tool(ctx, tool_id) or []
    fact_ids: list[str] = []
    for fid in list(extras) + default_pack_fact_ids(ctx, tool_id):
        if fid and fid not in fact_ids:
            fact_ids.append(fid)
    messages = list(kwargs.get("messages") or [])
    host_user = _primary_host_user_content(messages, tool_id)
    keep_host = _keep_host_user_packet(host_user) or tool_id in _GAP_EVAL_TOOLS
    pack = pack_volley(ctx, fact_ids=fact_ids, tool_id=tool_id, omit_g0=keep_host)
    packed_user = ""
    if pack.get("turns"):
        packed_user = str(pack["turns"][0].get("content") or "")
    if keep_host:
        if tool_id in _GAP_EVAL_TOOLS:
            from interview_mux.gap_packet_guard import (
                host_packet_from_user_text,
                merge_gap_bootstrap_keys,
            )

            host_obj = host_packet_from_user_text(host_user)
            if isinstance(host_obj, dict):
                facts: dict[str, Any] = {}
                brief = _compact_content_brief(ctx)
                if brief:
                    facts["content_brief"] = brief
                manifest = _compact_segment_manifest(ctx)
                if manifest and isinstance(manifest.get("segments"), list):
                    facts["segments"] = manifest["segments"]
                merge_gap_bootstrap_keys(host_obj, facts)
                merged = json.dumps(host_obj, ensure_ascii=False, default=str)
            else:
                merged = host_user
        else:
            merged = (
                f"{packed_user}\n\n--- stage input ---\n{host_user}" if packed_user else host_user
            )
    else:
        merged = packed_user
    new_msgs: list[dict[str, Any]] = []
    replaced = False
    for msg in messages:
        if not isinstance(msg, dict):
            new_msgs.append(msg)
            continue
        if msg.get("role") == "user" and not replaced:
            new_msgs.append({"role": "user", "content": merged})
            replaced = True
        elif msg.get("role") == "user":
            continue
        else:
            new_msgs.append(msg)
    if not replaced:
        new_msgs.append({"role": "user", "content": merged})
    out = dict(kwargs)
    out["messages"] = new_msgs
    return out


def pack_volley(
    ctx: RunContext,
    *,
    fact_ids: list[str],
    tool_id: str,
    require_facts: list[str] | None = None,
    omit_g0: bool = False,
) -> dict[str, Any]:
    """Render user/assistant turns from selected fact IDs. No LLM-written packet."""
    available = {str(f.get("fact_id")): f for f in memory_facts(ctx)}
    _inject_bootstrap_facts(ctx, available)
    aliases = {"transcript_integrity": "g0_transcript", "g0": "g0_transcript"}
    resolved_ids = [aliases.get(fid, fid) for fid in fact_ids]
    omitted = [fid for fid in available if fid not in resolved_ids]
    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    for fid in resolved_ids:
        fact = available.get(fid)
        if fact is None:
            missing.append(fid)
            continue
        selected.append(fact)

    g0 = ""
    # Closed G0 is always-eligible bootstrap — pack it even when the conductor
    # asked for transcript_integrity or omitted g0_transcript from fact_ids.
    # Skip when a large host stage packet is already in the user turn, and
    # never dump word-level G0 into gap-eval volleys (they need the manifest).
    skip_g0 = omit_g0 or tool_id in _GAP_EVAL_TOOLS
    if not skip_g0 and g0_closed(ctx) and "g0_transcript" in available:
        meaning = available["g0_transcript"].get("meaning")
        g0 = str(meaning or "")
    if skip_g0:
        selected = [
            f for f in selected if str(f.get("fact_id") or "") != "g0_transcript"
        ]

    # Coverage/ranking always get thesis + classified segments, even if the
    # conductor packed only source_card / G0.
    if tool_id in _SPINE_TOOLS:
        extra_ids = ["content_brief", "segment_manifest"]
        if tool_id in {"nugget_layup_compose", "nugget_corpus_mine"}:
            extra_ids.extend(["selection", "nugget_corpus", "media_ip_cta"])
        for fid in extra_ids:
            if fid not in resolved_ids and fid in available:
                selected.append(available[fid])

    required = list(require_facts or [])
    starved = [r for r in required if r not in available and r not in fact_ids]
    if starved:
        from interview_mux.homunculus.issues import emit_issue

        emit_issue(
            ctx,
            kind=f"starvation_{starved[0]}",
            source="pack_volley",
            evidence={"missing": starved, "tool_id": tool_id},
        )
        raise RuntimeError(f"starvation_{starved[0]}")

    user_parts: list[str] = []
    if g0:
        # Full closed G0 — a 12k slice truncates mid-tape and the boundary LLM
        # asks for the rest (needs_input transcript_excerpt).
        chunk = 24000
        pieces = [g0[i : i + chunk] for i in range(0, len(g0), chunk)] or [""]
        if len(pieces) == 1:
            user_parts.append("G0 transcript (closed):\n" + pieces[0])
        else:
            total = len(pieces)
            for i, piece in enumerate(pieces, 1):
                user_parts.append(f"G0 transcript (closed) part {i}/{total}:\n{piece}")
    for fact in selected:
        if g0 and str(fact.get("fact_id") or "") == "g0_transcript":
            continue
        meaning = fact.get("meaning")
        if isinstance(meaning, (dict, list)):
            blob = json.dumps(meaning, ensure_ascii=False, default=str)
        else:
            blob = str(meaning or "")
        user_parts.append(f"[{fact.get('fact_id')} {fact.get('identity')}]\n{blob[:24000]}")

    user_content = "\n\n".join(user_parts) or "(no admitted facts; G0 not closed)"
    payload = strip_forbidden_metadata({"task": tool_id, "context": user_content})
    context = ""
    if isinstance(payload, dict):
        context = str(payload.get("context") or user_content)
    else:
        context = user_content
    turns = [{"role": "user", "content": context}]
    pack = {
        "tool_id": tool_id,
        "fact_ids": fact_ids,
        "omitted_available": omitted[:40],
        "missing_ids": missing,
        "turns": turns,
        "packet_hash": packet_hash_for(turns),
        "g0_bootstrapped": bool(g0),
    }
    rel = f"{PACKS_REL}/{tool_id.replace('/', '_')}_{pack['packet_hash']}.json"
    ctx.write_json(rel, pack)
    append_ledger(
        ctx,
        {
            "kind": "pack_volley",
            "identity": "pack_volley",
            "tool_id": tool_id,
            "fact_ids": fact_ids,
            "packet_hash": pack["packet_hash"],
            "rel": rel,
        },
    )
    return pack


def _timestamped_transcript(data: Any) -> str:
    """Word- or turn-level G0 with times + speaker — untimed `text` is not enough for boundaries."""
    if not isinstance(data, dict):
        return ""
    words = data.get("words")
    if isinstance(words, list) and words:
        lines: list[str] = []
        cur_spk: str | None = None
        start = 0
        end = 0
        bits: list[str] = []

        def _flush() -> None:
            if cur_spk is None or not bits:
                return
            lines.append(f"{cur_spk} {start / 1000:.2f}-{end / 1000:.2f} {' '.join(bits)}")

        for w in words:
            if not isinstance(w, dict):
                continue
            tok = str(w.get("text") or w.get("word") or "").strip()
            if not tok:
                continue
            spk = str(w.get("speaker_id") or w.get("speaker") or "unk")
            t0 = int(w.get("start_ms") or 0)
            t1 = int(w.get("end_ms") or t0)
            if cur_spk is None:
                cur_spk, start, end, bits = spk, t0, t1, [tok]
                continue
            if spk != cur_spk or t0 - end > 800:
                _flush()
                cur_spk, start, end, bits = spk, t0, t1, [tok]
                continue
            bits.append(tok)
            end = t1
        _flush()
        if lines:
            return "\n".join(lines)
    for key in ("segments", "utterances", "turns", "cues"):
        segs = data.get(key)
        if not isinstance(segs, list) or not segs:
            continue
        lines = []
        for s in segs:
            if not isinstance(s, dict):
                continue
            tok = str(s.get("text") or "").strip()
            if not tok:
                continue
            spk = str(s.get("speaker_id") or s.get("speaker") or "unk")
            t0 = s.get("start_ms")
            t1 = s.get("end_ms")
            if t0 is None and s.get("start") is not None:
                t0 = int(float(s["start"]) * 1000)
            if t1 is None and s.get("end") is not None:
                t1 = int(float(s["end"]) * 1000)
            if t0 is None:
                continue
            t1 = int(t1 if t1 is not None else t0)
            lines.append(f"{spk} {int(t0) / 1000:.2f}-{t1 / 1000:.2f} {tok}")
        if lines:
            return "\n".join(lines)
    return ""


def _compact_content_brief(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("understanding/content_brief.json"):
        return None
    try:
        doc = ctx.read_json("understanding/content_brief.json")
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    out: dict[str, Any] = {}
    for key in ("thesis", "topics", "key_claims", "narrative_beats", "audience"):
        if key in doc:
            out[key] = doc[key]
    return out or None


def _compact_row(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "segment_id": s.get("segment_id"),
        "start_ms": s.get("start_ms"),
        "end_ms": s.get("end_ms"),
        "speaker_id": s.get("speaker_id"),
        "speaker_role": s.get("speaker_role"),
        "type": s.get("type"),
        "topic_tags": s.get("topic_tags"),
        "text": str(s.get("text") or "")[:240],
    }


def _compact_segment_manifest(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("segments/manifest.json"):
        return None
    try:
        doc = ctx.read_json("segments/manifest.json")
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    story_ids: set[str] = set()
    try:
        from interview_mux.media_ip_cta import admitted_story_segment_ids

        story_ids = admitted_story_segment_ids(ctx)
    except Exception:
        story_ids = set()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    segs = [s for s in (doc.get("segments") or []) if isinstance(s, dict)]
    for s in segs[:80]:
        sid = str(s.get("segment_id") or "")
        rows.append(_compact_row(s))
        if sid:
            seen.add(sid)
    # Recut remainders often land after the 80-row cap — pin them so ranking sees text.
    for s in segs:
        sid = str(s.get("segment_id") or "")
        if sid and sid in story_ids and sid not in seen:
            rows.append(_compact_row(s))
            seen.add(sid)
    return {"segments": rows} if rows else None


def _compact_selection(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("master/selection.json"):
        return None
    try:
        doc = ctx.read_json("master/selection.json")
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    ordered = [str(s) for s in (doc.get("ordered_segment_ids") or []) if s]
    excluded = list(doc.get("excluded_segment_ids") or [])[:40]
    excl_ids: set[str] = set()
    for row in excluded:
        if isinstance(row, dict):
            sid = str(row.get("segment_id") or row.get("id") or "").strip()
        else:
            sid = str(row or "").strip()
        if sid:
            excl_ids.add(sid)
    ordered_set = set(ordered)
    rationales = (
        dict(doc.get("exclude_rationales") or {})
        if isinstance(doc.get("exclude_rationales"), dict)
        else {}
    )
    rationales = {
        str(k): str(v)
        for k, v in rationales.items()
        if str(k) in excl_ids and str(k) not in ordered_set
    }
    return {
        "ordered_segment_ids": ordered,
        "admitted_story_segment_ids": list(doc.get("admitted_story_segment_ids") or [])[:24],
        "considerable_segment_ids": list(doc.get("considerable_segment_ids") or [])[:24],
        "excluded_segment_ids": excluded,
        "exclude_rationales": rationales,
        "media_ip_cta": list(doc.get("media_ip_cta") or [])[:12],
        "notes": str(doc.get("notes") or "")[:400] or None,
    }


def _compact_nugget_corpus(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("understanding/nugget_corpus.json"):
        return None
    try:
        doc = ctx.read_json("understanding/nugget_corpus.json")
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    rows: list[dict[str, Any]] = []
    for n in (doc.get("nuggets") or [])[:40]:
        if not isinstance(n, dict):
            continue
        rows.append(
            {
                "nugget_id": n.get("nugget_id"),
                "claim": n.get("claim") or n.get("text"),
                "already_aired_in_selection": n.get("already_aired_in_selection"),
                "in_selection": n.get("in_selection"),
                "source_segment_ids": n.get("source_segment_ids"),
            }
        )
    return {"nuggets": rows} if rows else None


def _compact_media_ip_cta(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("mastering/media_ip_cta.json"):
        return None
    try:
        doc = ctx.read_json("mastering/media_ip_cta.json")
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    return {
        "dropped_segment_ids": list(doc.get("dropped_segment_ids") or [])[:24],
        "never_touch_segment_ids": list(doc.get("never_touch_segment_ids") or [])[:24],
        "cover_target_ids": list(doc.get("cover_target_ids") or [])[:24],
        "admitted_story_segment_ids": list(doc.get("admitted_story_segment_ids") or [])[:24],
        "considerable_segment_ids": list(doc.get("considerable_segment_ids") or [])[:24],
        "open_choice": doc.get("open_choice"),
        "notes": list(doc.get("notes") or [])[:12],
        "seed_count": doc.get("seed_count"),
        "seed_ids": list(doc.get("seed_ids") or [])[:24],
        "prune_tree": list(doc.get("prune_tree") or [])[:12],
    }


def _compact_editorial_omit_hints(ctx: RunContext) -> dict[str, Any] | None:
    """Prior-stage keep/avoid suggestions for ranking (tape meaning only)."""
    hints: dict[str, Any] = {}
    if ctx.artifact_exists("master/selection.json"):
        try:
            sel = ctx.read_json("master/selection.json")
        except Exception:
            sel = None
        if isinstance(sel, dict):
            rationales = sel.get("exclude_rationales")
            if isinstance(rationales, dict) and rationales:
                hints["exclude_rationales"] = {
                    str(k): str(v)[:200] for k, v in list(rationales.items())[:40]
                }
            editorial_excl = []
            for row in sel.get("excluded_segment_ids") or []:
                if not isinstance(row, dict):
                    continue
                reason = str(row.get("reason") or "")
                try:
                    from interview_mux.media_ip_cta import is_editorial_exclude_reason

                    if not is_editorial_exclude_reason(reason):
                        continue
                except Exception:
                    pass
                editorial_excl.append(
                    {
                        "segment_id": row.get("segment_id"),
                        "reason": reason[:200],
                    }
                )
            if editorial_excl:
                hints["editorial_excluded"] = editorial_excl[:40]
            notes = str(sel.get("notes") or "").strip()
            if notes:
                hints["selection_notes"] = notes[:400]
    cta = _compact_media_ip_cta(ctx)
    if cta and (cta.get("dropped_segment_ids") or cta.get("notes")):
        hints["media_ip_cta"] = cta
    return hints or None


def _primary_host_user_content(messages: list[Any], tool_id: str) -> str:
    """Pick the stage JSON packet, not an earlier prior-beat volley turn.

    Gap stages prepend PRIOR NATIVE BEATS user turns. Using the first user
    message as the host packet drops segments / gap_evaluations / policy and
    the nested LLM asks to rerun for missing stage input.
    """
    users = [
        str(msg.get("content") or "")
        for msg in messages
        if isinstance(msg, dict) and msg.get("role") == "user"
    ]
    if not users:
        return ""
    json_users = [u for u in users if u.lstrip().startswith(("{", "["))]
    if json_users:
        return max(json_users, key=len)
    if tool_id in _GAP_EVAL_TOOLS:
        marked = [u for u in users if _keep_host_user_packet(u)]
        if marked:
            return max(marked, key=len)
        return users[-1]
    return users[0]


def _keep_host_user_packet(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    if any(m in low for m in _HOST_PACKET_MARKERS) and len(t) >= 80:
        return True
    return (t.startswith("{") or t.startswith("[")) and len(t) >= 400


def _extract_text(data: Any) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("text", "transcript", "reviewed_text"):
            if isinstance(data.get(key), str) and data[key].strip():
                return str(data[key])
        segs = data.get("segments") or data.get("utterances") or data.get("cues")
        if isinstance(segs, list):
            bits = []
            for s in segs[:400]:
                if isinstance(s, dict):
                    bits.append(str(s.get("text") or s.get("word") or ""))
            return " ".join(x for x in bits if x)
    return ""


def _explicit_must_keep_ids(ctx: RunContext) -> list[str]:
    for rel in ("mastering/must_keep_ids.json", "selection/must_keep.json"):
        if not ctx.artifact_exists(rel):
            continue
        raw = ctx.read_json(rel)
        if isinstance(raw, list):
            return [str(x) for x in raw]
        if isinstance(raw, dict):
            ids = raw.get("ids") or raw.get("must_keep") or []
            if isinstance(ids, list):
                return [str(x) for x in ids]
    return []


def operator_must_keep_ids(ctx: RunContext) -> list[str]:
    """Existing volley-contract must-keep IDs if present on disk."""
    explicit = _explicit_must_keep_ids(ctx)
    if explicit:
        return explicit
    admitted = [r.get("fact_id") for r in read_admitted(ctx) if r.get("action") != "drop"]
    return [str(x) for x in admitted if x]
