"""Deterministic merge for content_brief_reanchor shard/collate outputs."""

from __future__ import annotations

from typing import Any


def _topic_key(name: Any) -> str:
    return str(name or "").strip().lower()


def _union_segment_ids(*groups: list[Any] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for raw in group or []:
            sid = str(raw).strip()
            if sid and sid not in seen:
                seen.add(sid)
                out.append(sid)
    return out


def _valid_segment_ids(ids: set[str], raw_ids: list[Any] | None) -> list[str]:
    if not ids:
        return [str(x) for x in (raw_ids or []) if str(x).strip()]
    return [sid for sid in _union_segment_ids(raw_ids) if sid in ids]


def merge_shard_content_brief(
    collate_env: dict[str, Any],
    shard_outputs: list[dict[str, Any]],
    *,
    baseline_brief: dict[str, Any] | None = None,
    valid_segment_ids: set[str] | None = None,
) -> dict[str, Any]:
    """
    Union topic segment_ids, key_claims, and relationships across shard envelopes.
    Preserves pass-1 brief fields when shards omit them.
    """
    if not shard_outputs:
        return collate_env

    baseline = baseline_brief if isinstance(baseline_brief, dict) else {}
    baseline_topics = {
        _topic_key(t.get("name")): dict(t)
        for t in (baseline.get("topics") or [])
        if isinstance(t, dict) and _topic_key(t.get("name"))
    }

    merged_topics: dict[str, dict[str, Any]] = dict(baseline_topics)
    merged_claims: dict[str, dict[str, Any]] = {
        str(c.get("id")): dict(c)
        for c in (baseline.get("key_claims") or [])
        if isinstance(c, dict) and c.get("id")
    }
    rel_seen: set[tuple[str, str, str]] = set()
    merged_relationships: list[dict[str, Any]] = []
    thesis = str(baseline.get("thesis") or "").strip()
    audience = baseline.get("audience")
    jargon = list(baseline.get("jargon_glossary") or []) if isinstance(baseline.get("jargon_glossary"), list) else []

    for shard in shard_outputs:
        env = shard.get("envelope") if isinstance(shard, dict) else {}
        artifacts = (env.get("artifacts") or {}) if isinstance(env, dict) else {}
        if not isinstance(artifacts, dict):
            continue
        if not thesis and str(artifacts.get("thesis") or "").strip():
            thesis = str(artifacts.get("thesis") or "").strip()
        if audience is None and artifacts.get("audience") is not None:
            audience = artifacts.get("audience")

        for topic in artifacts.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            key = _topic_key(topic.get("name"))
            if not key:
                continue
            prior = merged_topics.get(key, {})
            seg_ids = _valid_segment_ids(
                valid_segment_ids or set(),
                _union_segment_ids(prior.get("segment_ids"), topic.get("segment_ids")),
            )
            merged = dict(prior)
            merged.update({k: v for k, v in topic.items() if k != "segment_ids"})
            merged["segment_ids"] = seg_ids
            merged_topics[key] = merged

        for claim in artifacts.get("key_claims") or []:
            if not isinstance(claim, dict):
                continue
            cid = str(claim.get("id") or "").strip()
            if not cid:
                continue
            prior = merged_claims.get(cid, {})
            merged = dict(prior)
            merged.update(claim)
            for field in ("segment_ids", "evidence_segment_ids"):
                merged[field] = _valid_segment_ids(
                    valid_segment_ids or set(),
                    _union_segment_ids(prior.get(field), claim.get(field)),
                )
            merged_claims[cid] = merged

        for rel in artifacts.get("topic_relationships") or []:
            if not isinstance(rel, dict):
                continue
            sig = (
                _topic_key(rel.get("from_topic")),
                _topic_key(rel.get("to_topic")),
                str(rel.get("relation") or "").strip().lower(),
            )
            if not sig[0] or not sig[1] or sig in rel_seen:
                continue
            rel_seen.add(sig)
            entry = dict(rel)
            entry["evidence_segment_ids"] = _valid_segment_ids(
                valid_segment_ids or set(),
                rel.get("evidence_segment_ids"),
            )
            merged_relationships.append(entry)

        if not jargon and isinstance(artifacts.get("jargon_glossary"), list):
            jargon = list(artifacts.get("jargon_glossary") or [])

    llm_artifacts = (collate_env.get("artifacts") or {}) if isinstance(collate_env, dict) else {}
    if isinstance(llm_artifacts, dict):
        for topic in llm_artifacts.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            key = _topic_key(topic.get("name"))
            if not key:
                continue
            prior = merged_topics.get(key, {})
            seg_ids = _valid_segment_ids(
                valid_segment_ids or set(),
                _union_segment_ids(prior.get("segment_ids"), topic.get("segment_ids")),
            )
            merged = dict(prior)
            merged.update({k: v for k, v in topic.items() if k != "segment_ids"})
            merged["segment_ids"] = seg_ids
            merged_topics[key] = merged
        for claim in llm_artifacts.get("key_claims") or []:
            if not isinstance(claim, dict) or not claim.get("id"):
                continue
            cid = str(claim["id"])
            prior = merged_claims.get(cid, {})
            merged = dict(prior)
            merged.update(claim)
            for field in ("segment_ids", "evidence_segment_ids"):
                merged[field] = _valid_segment_ids(
                    valid_segment_ids or set(),
                    _union_segment_ids(prior.get(field), claim.get(field)),
                )
            merged_claims[cid] = merged
        for rel in llm_artifacts.get("topic_relationships") or []:
            if not isinstance(rel, dict):
                continue
            sig = (
                _topic_key(rel.get("from_topic")),
                _topic_key(rel.get("to_topic")),
                str(rel.get("relation") or "").strip().lower(),
            )
            if not sig[0] or not sig[1] or sig in rel_seen:
                continue
            rel_seen.add(sig)
            entry = dict(rel)
            entry["evidence_segment_ids"] = _valid_segment_ids(
                valid_segment_ids or set(),
                rel.get("evidence_segment_ids"),
            )
            merged_relationships.append(entry)
        if not thesis and str(llm_artifacts.get("thesis") or "").strip():
            thesis = str(llm_artifacts.get("thesis") or "").strip()

    topic_order = [_topic_key(t.get("name")) for t in (baseline.get("topics") or []) if isinstance(t, dict)]
    ordered_topics: list[dict[str, Any]] = []
    seen_topic_keys: set[str] = set()
    for key in topic_order:
        if key and key in merged_topics and key not in seen_topic_keys:
            ordered_topics.append(merged_topics[key])
            seen_topic_keys.add(key)
    for key, topic in merged_topics.items():
        if key not in seen_topic_keys:
            ordered_topics.append(topic)

    merged = dict(collate_env)
    artifacts = dict(llm_artifacts) if isinstance(llm_artifacts, dict) else {}
    if thesis:
        artifacts["thesis"] = thesis
    artifacts["topics"] = ordered_topics
    artifacts["key_claims"] = list(merged_claims.values())
    if merged_relationships or not artifacts.get("topic_relationships"):
        artifacts["topic_relationships"] = merged_relationships or artifacts.get("topic_relationships") or []
    if audience is not None:
        artifacts["audience"] = audience
    if jargon:
        artifacts["jargon_glossary"] = jargon
    merged["artifacts"] = artifacts
    routing = dict(merged.get("_routing_meta") or {})
    routing["deterministic_content_brief_collate"] = True
    merged["_routing_meta"] = routing
    if merged.get("status") != "complete" and ordered_topics and any(t.get("segment_ids") for t in ordered_topics):
        merged["status"] = "complete"
    return merged
