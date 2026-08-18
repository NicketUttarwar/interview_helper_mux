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


def bootstrap_g0_text(ctx: RunContext) -> str:
    for rel in (
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
        text = _extract_text(data)
        if text.strip():
            return text
    return ""


def g0_closed(ctx: RunContext) -> bool:
    try:
        from interview_mux.gates import check_transcript_review_pending

        return not check_transcript_review_pending(ctx)
    except Exception:
        return ctx.artifact_exists(".stage_done/transcript_review_build")


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
    if g0_closed(ctx) and bootstrap_g0_text(ctx):
        ids.append("g0_transcript")
    for kid in _explicit_must_keep_ids(ctx)[:12]:
        ids.append(kid)
    if card:
        ids.append("source_card")
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
    """Replace user turns with a host-rendered pack. Keep system messages."""
    from interview_mux.homunculus.ledger import last_fact_ids_for_tool

    tool_id = identity.split("axis_select:", 1)[-1] if identity.startswith("axis_select:") else identity
    fact_ids = last_fact_ids_for_tool(ctx, tool_id) or default_pack_fact_ids(ctx, tool_id)
    pack = pack_volley(ctx, fact_ids=fact_ids, tool_id=tool_id)
    packed_user = ""
    if pack.get("turns"):
        packed_user = str(pack["turns"][0].get("content") or "")
    messages = list(kwargs.get("messages") or [])
    new_msgs: list[dict[str, Any]] = []
    replaced = False
    for msg in messages:
        if not isinstance(msg, dict):
            new_msgs.append(msg)
            continue
        if msg.get("role") == "user" and not replaced:
            new_msgs.append({"role": "user", "content": packed_user})
            replaced = True
        elif msg.get("role") == "user":
            continue
        else:
            new_msgs.append(msg)
    if not replaced:
        new_msgs.append({"role": "user", "content": packed_user})
    out = dict(kwargs)
    out["messages"] = new_msgs
    return out


def pack_volley(
    ctx: RunContext,
    *,
    fact_ids: list[str],
    tool_id: str,
    require_facts: list[str] | None = None,
) -> dict[str, Any]:
    """Render user/assistant turns from selected fact IDs. No LLM-written packet."""
    available = {str(f.get("fact_id")): f for f in memory_facts(ctx)}
    _inject_bootstrap_facts(ctx, available)
    omitted = [fid for fid in available if fid not in fact_ids]
    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    for fid in fact_ids:
        fact = available.get(fid)
        if fact is None:
            missing.append(fid)
            continue
        selected.append(fact)

    g0 = ""
    if "g0_transcript" in available and (
        not fact_ids or "g0_transcript" in fact_ids or not selected
    ):
        meaning = available["g0_transcript"].get("meaning")
        g0 = str(meaning or "")
        if "g0_transcript" not in fact_ids and not selected:
            # Bootstrap: empty store still packs closed G0.
            pass

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
        user_parts.append("G0 transcript (closed):\n" + g0[:12000])
    for fact in selected:
        meaning = fact.get("meaning")
        if isinstance(meaning, (dict, list)):
            blob = json.dumps(meaning, ensure_ascii=False, default=str)
        else:
            blob = str(meaning or "")
        user_parts.append(f"[{fact.get('fact_id')} {fact.get('identity')}]\n{blob[:8000]}")

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
