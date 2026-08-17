"""Deterministic volley packer: conductor picks fact IDs; code renders turns."""

from __future__ import annotations

import json
from typing import Any

from interview_mux.homunculus.admit import memory_facts, read_admitted
from interview_mux.homunculus.ledger import append_ledger, packet_hash_for
from interview_mux.run_context import RunContext
from interview_mux.volley_packet_lint import strip_forbidden_metadata

PACKS_REL = "mastering/homunculus/volley_packs"


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


def pack_volley(
    ctx: RunContext,
    *,
    fact_ids: list[str],
    tool_id: str,
    require_facts: list[str] | None = None,
) -> dict[str, Any]:
    """Render user/assistant turns from selected fact IDs. No LLM-written packet."""
    available = {str(f.get("fact_id")): f for f in memory_facts(ctx)}
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


def operator_must_keep_ids(ctx: RunContext) -> list[str]:
    """Existing volley-contract must-keep IDs if present on disk."""
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
    admitted = [r.get("fact_id") for r in read_admitted(ctx) if r.get("action") != "drop"]
    return [str(x) for x in admitted if x]
