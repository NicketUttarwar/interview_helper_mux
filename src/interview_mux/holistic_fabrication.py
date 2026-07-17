"""Global holistic fabrication fallback — LLM + deterministic repair using stage context."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from interview_mux.config import merged_config
from interview_mux.deterministic_lint import deterministic_lint
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS, validate_stage_artifacts
from interview_mux.run_context import RunContext
from interview_mux.stage_contract import load_contract

_PROMPT_REL = "_shared/holistic-fabrication.system.txt"

# Known stage inputs when contract inputs.hard is empty (topic_coverage, etc.)
_STAGE_INPUT_FALLBACK: dict[str, list[str]] = {
    "topic_coverage_audit": [
        "understanding/content_brief.json",
        "segments/manifest.json",
        "understanding/delivery_brief.json",
    ],
    "content_context": [
        "understanding/speakers.json",
        "transcript/corrected.json",
    ],
    "content_brief_reanchor": [
        "understanding/content_brief.json",
        "segments/manifest.json",
    ],
    "segment_classification": [
        "segments/boundaries.json",
        "understanding/content_brief.json",
    ],
    "narrative_arc_plan": [
        "master/coverage_audit.json",
        "understanding/content_brief.json",
        "understanding/delivery_brief.json",
    ],
    "full_master_ranking": [
        "master/narrative_plan.json",
        "master/coverage_audit.json",
        "segments/manifest.json",
    ],
}


def holistic_fabrication_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    base = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "enabled": True,
        "llm_enabled": True,
        "deterministic_first": True,
        "model_tier": "economy",
        "max_calls_per_stage_attempt": 2,
        "max_calls_per_run": 24,
        "override_arbiter_on_clear": True,
        "allow_upstream_patches": True,
        "stages": "*",
    }
    raw = base.get("holistic_fabrication") or {}
    return {**defaults, **raw}


def holistic_fabrication_enabled(stage_key: str, cfg: dict[str, Any] | None = None) -> bool:
    hf = holistic_fabrication_cfg(cfg)
    if not hf.get("enabled", True):
        return False
    allowed = hf.get("stages")
    if allowed in (None, "", "*"):
        return True
    if isinstance(allowed, list):
        return stage_key in allowed
    return str(allowed) == stage_key


def _norm_topic(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _topic_keywords(name: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", _norm_topic(name))
    return {w for w in words if len(w) > 3}


def _segment_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in (manifest.get("segments") or []) if isinstance(manifest, dict) else []:
        if isinstance(row, dict) and row.get("segment_id"):
            out[str(row["segment_id"])] = row
    return out


def _best_topic_for_segment(
    seg: dict[str, Any],
    topics: list[dict[str, Any]],
) -> str | None:
    if not topics:
        return None
    tags = seg.get("topic_tags") or []
    if tags:
        tag = _norm_topic(str(tags[0]).replace("_", " "))
        for t in topics:
            name = str(t.get("name") or "")
            if tag in _norm_topic(name) or _norm_topic(name) in tag:
                return name
    text = _norm_topic(str(seg.get("text") or ""))
    best_name: str | None = None
    best_score = 0
    for t in topics:
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "")
        if not name:
            continue
        keys = _topic_keywords(name)
        summary_keys = _topic_keywords(str(t.get("summary") or ""))
        keys |= summary_keys
        if not keys:
            continue
        score = sum(1 for k in keys if k in text)
        if score > best_score:
            best_score = score
            best_name = name
    if best_score >= 1:
        return best_name
    seg_type = str(seg.get("type") or "")
    if seg_type in ("setup", "interviewer_reaction"):
        return str(topics[0].get("name") or "") or None
    return None


def _dedupe_topic_mappings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        topic = str(row.get("topic") or "").strip()
        if not topic:
            continue
        key = _norm_topic(topic)
        seg_ids = [str(s) for s in (row.get("segment_ids") or []) if s]
        if key not in merged:
            merged[key] = {
                "topic": topic,
                "segment_ids": list(dict.fromkeys(seg_ids)),
                "covered": bool(row.get("covered", True)),
            }
        else:
            existing = merged[key]["segment_ids"]
            for sid in seg_ids:
                if sid not in existing:
                    existing.append(sid)
            merged[key]["covered"] = merged[key]["covered"] or bool(row.get("covered"))
    return list(merged.values())


def _repair_topic_coverage_deterministic(
    ctx: RunContext,
    artifacts: dict[str, Any],
    *,
    stage_inputs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Map orphan segments, synthesize claims when brief is empty. Returns (artifacts, upstream, actions)."""
    out = copy.deepcopy(artifacts)
    upstream: dict[str, Any] = {}
    actions: list[str] = []

    brief = stage_inputs.get("content_brief") or {}
    if not brief and ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
    manifest = stage_inputs.get("segments") or stage_inputs.get("manifest") or {}
    if not manifest and ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")

    topics = [t for t in (brief.get("topics") or []) if isinstance(t, dict)]
    by_id = _segment_by_id(manifest if isinstance(manifest, dict) else {"segments": manifest})

    topic_mappings = _dedupe_topic_mappings(list(out.get("topic_mappings") or []))
    mapped_ids: set[str] = set()
    for row in topic_mappings:
        for sid in row.get("segment_ids") or []:
            mapped_ids.add(str(sid))

    orphans = [str(s) for s in (out.get("orphan_segment_ids") or []) if s]
    resolved_orphans: list[str] = []
    for sid in orphans:
        seg = by_id.get(sid)
        if not seg:
            resolved_orphans.append(sid)
            continue
        topic_name = _best_topic_for_segment(seg, topics)
        if not topic_name:
            resolved_orphans.append(sid)
            continue
        key = _norm_topic(topic_name)
        found = False
        for row in topic_mappings:
            if _norm_topic(str(row.get("topic") or "")) == key:
                ids = row.setdefault("segment_ids", [])
                if sid not in ids:
                    ids.append(sid)
                row["covered"] = True
                found = True
                actions.append(f"map_orphan:{sid}->{topic_name}")
                break
        if not found:
            topic_mappings.append({"topic": topic_name, "segment_ids": [sid], "covered": True})
            actions.append(f"map_orphan_new:{sid}->{topic_name}")
        mapped_ids.add(sid)

    out["topic_mappings"] = topic_mappings
    out["orphan_segment_ids"] = sorted(set(resolved_orphans))

    key_claims = list(brief.get("key_claims") or [])
    if not key_claims and topics:
        synthesized: list[dict[str, Any]] = []
        seen_topics: set[str] = set()
        for t in topics:
            name = str(t.get("name") or "").strip()
            if not name or _norm_topic(name) in seen_topics:
                continue
            seen_topics.add(_norm_topic(name))
            seg_ids: list[str] = []
            for row in topic_mappings:
                if _norm_topic(str(row.get("topic") or "")) == _norm_topic(name):
                    seg_ids = list(row.get("segment_ids") or [])
                    break
            if not seg_ids:
                seg_ids = list(t.get("segment_ids") or [])
            claim_text = str(t.get("summary") or name).strip()
            if len(claim_text) > 220:
                claim_text = claim_text[:217] + "..."
            synthesized.append(
                {
                    "id": f"claim_{len(synthesized) + 1:03d}",
                    "claim": claim_text,
                    "claim_type": "fact",
                    "speaker_role": "interviewee",
                    "segment_ids": seg_ids[:6],
                    "evidence_segment_ids": seg_ids[:6],
                }
            )
        if synthesized:
            upstream["understanding/content_brief.json"] = {"key_claims": synthesized}
            key_claims = synthesized
            actions.append(f"synthesize_key_claims:{len(synthesized)}")

    if key_claims:
        claim_mappings: list[dict[str, Any]] = []
        for claim in key_claims:
            if not isinstance(claim, dict):
                continue
            text = str(claim.get("claim") or claim.get("text") or "").strip()
            if not text:
                continue
            seg_ids = [str(s) for s in (claim.get("segment_ids") or claim.get("evidence_segment_ids") or []) if s]
            claim_mappings.append(
                {"claim": text, "segment_ids": seg_ids, "covered": bool(seg_ids)}
            )
        out["claim_mappings"] = claim_mappings
        actions.append(f"claim_mappings:{len(claim_mappings)}")

    topic_count = len({ _norm_topic(str(r.get("topic") or "")) for r in topic_mappings if r.get("topic") })
    covered_topics = sum(
        1 for r in topic_mappings if r.get("covered") and (r.get("segment_ids") or [])
    )
    claim_count = len(key_claims)
    covered_claims = sum(
        1 for r in (out.get("claim_mappings") or []) if r.get("covered") and (r.get("segment_ids") or [])
    )
    denom = max(topic_count + claim_count, 1)
    out["coverage_score"] = round((covered_topics + covered_claims) / denom, 3)
    if out.get("coverage_score") is None:
        out["coverage_score"] = 0.0
    actions.append(f"coverage_score:{out['coverage_score']}")

    return out, upstream, actions


def _repair_content_context_deterministic(
    ctx: RunContext,
    artifacts: dict[str, Any],
    *,
    stage_inputs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    out = copy.deepcopy(artifacts)
    actions: list[str] = []
    if out.get("key_claims"):
        return out, {}, actions
    topics = [t for t in (out.get("topics") or []) if isinstance(t, dict)]
    if not topics:
        return out, {}, actions
    claims: list[dict[str, Any]] = []
    for i, t in enumerate(topics[:8]):
        name = str(t.get("name") or "").strip()
        if not name:
            continue
        claims.append(
            {
                "id": f"claim_{i + 1:03d}",
                "claim": str(t.get("summary") or name)[:220],
                "claim_type": "fact",
                "speaker_role": "interviewee",
                "approx_time_range": t.get("approx_time_range"),
                "segment_ids": t.get("segment_ids"),
                "evidence_segment_ids": t.get("evidence_segment_ids"),
            }
        )
    if claims:
        out["key_claims"] = claims
        actions.append(f"key_claims_from_topics:{len(claims)}")
    return out, {}, actions


_DETERMINISTIC_REPAIRERS = {
    "topic_coverage_audit": _repair_topic_coverage_deterministic,
    "content_context": _repair_content_context_deterministic,
    "content_brief_reanchor": _repair_content_context_deterministic,
}


def load_stage_inputs_for_fabrication(
    ctx: RunContext,
    stage_key: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load on-disk inputs referenced by stage contract + fallbacks."""
    out: dict[str, Any] = dict(extra or {})
    paths: list[str] = []
    try:
        contract = load_contract(stage_key)
        for dep in contract.inputs:
            if dep.path:
                paths.append(dep.path)
    except Exception:
        pass
    for p in _STAGE_INPUT_FALLBACK.get(stage_key, []):
        if p not in paths:
            paths.append(p)
    for rel in paths:
        key = rel.split("/")[-1].replace(".json", "")
        if key in out:
            continue
        if ctx.artifact_exists(rel):
            try:
                doc = ctx.read_json(rel)
                if isinstance(doc, dict):
                    out[key] = doc
                    if rel == "understanding/content_brief.json":
                        out["content_brief"] = doc
                    elif rel == "segments/manifest.json":
                        out["segments"] = doc
            except Exception:
                continue
    return out


def _volley_excerpt(volley: list[dict[str, str]] | None, *, max_chars: int = 12000) -> list[dict[str, str]]:
    if not volley:
        return []
    tail = volley[-6:]
    out: list[dict[str, str]] = []
    total = 0
    for msg in tail:
        content = str(msg.get("content") or "")
        if total + len(content) > max_chars:
            content = content[: max_chars - total] + "…"
        out.append({"role": msg.get("role", "user"), "content": content})
        total += len(content)
        if total >= max_chars:
            break
    return out


def _collect_gaps(
    *,
    lint_errors: list[str],
    schema_errors: list[str],
    envelope: dict[str, Any],
    arbiter_result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for err in lint_errors:
        gaps.append({"kind": "lint", "message": err})
    for err in schema_errors:
        gaps.append({"kind": "schema", "message": err})
    if envelope.get("status") != "complete":
        gaps.append({"kind": "envelope_status", "message": f"status={envelope.get('status')}"})
    if arbiter_result:
        verdict = str(arbiter_result.get("verdict") or "")
        if verdict and verdict != "accept":
            gaps.append(
                {
                    "kind": "arbiter",
                    "verdict": verdict,
                    "gaps": arbiter_result.get("gaps") or [],
                    "question": (arbiter_result.get("suggested_investigation") or {}).get("question"),
                    "reasoning": arbiter_result.get("reasoning_summary"),
                }
            )
    return gaps


def _parse_llm_fabrication_response(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        if raw.get("artifact_patches") is not None or raw.get("upstream_patches") is not None:
            return raw
        art = raw.get("artifacts")
        if isinstance(art, dict) and ("artifact_patches" in art or "upstream_patches" in art):
            return art
        if art and not raw.get("artifact_patches"):
            return {"artifact_patches": art, "upstream_patches": {}, "envelope_patches": {}}
    if isinstance(raw, str):
        try:
            return _parse_llm_fabrication_response(json.loads(raw))
        except json.JSONDecodeError:
            return None
    return None


def _run_holistic_fabrication_llm(
    ctx: RunContext,
    stage_key: str,
    payload: dict[str, Any],
    *,
    attempt: int = 1,
) -> dict[str, Any] | None:
    hf = holistic_fabrication_cfg()
    if not hf.get("llm_enabled", True):
        return None

    from interview_mux.stages.llm_runner import run_prompt_envelope

    user_content = json.dumps(payload, default=str, ensure_ascii=False)
    try:
        response = run_prompt_envelope(
            "_holistic_fabrication",
            _PROMPT_REL,
            user_content=user_content,
            ctx=ctx,
            include_preamble=False,
            task_kind="fabricate",
            record_stage_key=stage_key,
            call_attempt=attempt,
            bump_tier=False,
            explicit_tier=str(hf.get("model_tier") or "economy"),
        )
    except Exception as exc:
        ctx.log(
            f"Holistic fabrication LLM failed ({stage_key}): {exc}",
            level="warning",
            stage=stage_key,
            action_id="holistic_fabrication.llm_failed",
            origin="pipeline",
        )
        return None

    parsed = response
    if isinstance(response, dict) and "artifacts" in response:
        parsed = response.get("artifacts") or response
    if isinstance(response, dict) and response.get("status") == "complete":
        parsed = response.get("artifacts") or response
    return _parse_llm_fabrication_response(parsed)


def _deep_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, val in patch.items():
        if key.startswith("_"):
            continue
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(out[key], val)
        elif isinstance(val, list) and not val:
            continue
        else:
            out[key] = copy.deepcopy(val)
    return out


def _apply_upstream_patches(ctx: RunContext, patches: dict[str, Any]) -> list[str]:
    applied: list[str] = []
    hf = holistic_fabrication_cfg()
    if not hf.get("allow_upstream_patches", True):
        return applied
    for rel, patch in patches.items():
        if not isinstance(patch, dict) or not rel.endswith(".json"):
            continue
        try:
            existing = ctx.read_json(rel) if ctx.artifact_exists(rel) else {}
            if not isinstance(existing, dict):
                existing = {}
            merged = _deep_merge_dict(existing, patch)
            meta = merged.setdefault("_meta", {})
            meta["holistic_fabrication"] = {
                "patched_at": datetime.now(timezone.utc).isoformat(),
                "paths": sorted(patch.keys()),
            }
            ctx.write_json(rel, merged)
            applied.append(rel)
        except Exception:
            continue
    return applied


def _relint(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    *,
    volley: list[dict[str, str]] | None,
    schema_errors: list[str],
    routed_via_collate: bool,
) -> tuple[list[str], list[str]]:
    art = envelope.get("artifacts") or {}
    schema = validate_stage_artifacts(stage_key, art)
    lint = deterministic_lint(
        stage_key,
        envelope,
        ctx,
        schema_errors=schema,
        volley=volley,
        routed_via_collate=routed_via_collate,
    )
    return lint, schema


def mark_holistic_fabrication_cleared(
    envelope: dict[str, Any],
    arbiter_result: dict[str, Any] | None,
    *,
    actions: list[str],
) -> dict[str, Any] | None:
    hf = holistic_fabrication_cfg()
    envelope["status"] = "complete"
    routing = envelope.setdefault("_routing_meta", {})
    routing["holistic_fabrication_cleared"] = True
    routing["holistic_fabrication_actions"] = actions[-20:]
    routing["deterministic_lint_errors"] = []
    routing.pop("envelope_blocked", None)
    meta = (envelope.get("artifacts") or {}).setdefault("_meta", {})
    meta["holistic_fabrication"] = {
        "cleared_at": datetime.now(timezone.utc).isoformat(),
        "actions": actions[-20:],
    }
    updated_arbiter = arbiter_result
    if hf.get("override_arbiter_on_clear", True) and arbiter_result:
        updated_arbiter = {
            **arbiter_result,
            "verdict": "accept",
            "reasoning_summary": (
                (arbiter_result.get("reasoning_summary") or "")
                + " Cleared by holistic fabrication fallback."
            ).strip(),
            "gaps": [],
            "holistic_fabrication_override": True,
        }
    envelope.setdefault("needs", [])
    envelope["follow_up_investigations"] = [
        f
        for f in (envelope.get("follow_up_investigations") or [])
        if isinstance(f, dict) and not f.get("blocking")
    ]
    return updated_arbiter


@dataclass
class HolisticFabricationResult:
    cleared: bool = False
    envelope: dict[str, Any] = field(default_factory=dict)
    arbiter_result: dict[str, Any] | None = None
    lint_errors: list[str] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    used_llm: bool = False
    message: str = ""


def try_holistic_fabrication(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    *,
    volley: list[dict[str, str]] | None = None,
    stage_input: dict[str, Any] | None = None,
    arbiter_result: dict[str, Any] | None = None,
    lint_errors: list[str] | None = None,
    schema_errors: list[str] | None = None,
    routed_via_collate: bool = False,
    attempt: int = 1,
) -> HolisticFabricationResult:
    """Attempt deterministic + LLM holistic repair. Returns cleared=True when gates pass."""
    result = HolisticFabricationResult(
        envelope=envelope,
        arbiter_result=arbiter_result,
        lint_errors=list(lint_errors or []),
        schema_errors=list(schema_errors or []),
    )
    if not holistic_fabrication_enabled(stage_key):
        result.message = "holistic fabrication disabled for stage"
        return result

    gaps = _collect_gaps(
        lint_errors=result.lint_errors,
        schema_errors=result.schema_errors,
        envelope=envelope,
        arbiter_result=arbiter_result,
    )
    if not gaps and envelope.get("status") == "complete":
        if not result.lint_errors and not result.schema_errors:
            return result
    if not gaps and not result.lint_errors:
        return result

    stage_inputs = load_stage_inputs_for_fabrication(ctx, stage_key, extra=stage_input)
    artifacts = copy.deepcopy(envelope.get("artifacts") or {})
    actions: list[str] = []
    upstream_patches: dict[str, Any] = {}

    hf = holistic_fabrication_cfg()
    if hf.get("deterministic_first", True):
        repairer = _DETERMINISTIC_REPAIRERS.get(stage_key)
        if repairer:
            artifacts, up, det_actions = repairer(ctx, artifacts, stage_inputs=stage_inputs)
            actions.extend(det_actions)
            upstream_patches.update(up)

    envelope = copy.deepcopy(envelope)
    envelope["artifacts"] = artifacts
    if upstream_patches:
        applied = _apply_upstream_patches(ctx, upstream_patches)
        actions.extend([f"upstream:{p}" for p in applied])
        stage_inputs = load_stage_inputs_for_fabrication(ctx, stage_key, extra=stage_input)

    if actions:
        envelope["status"] = "complete"

    lint, schema = _relint(
        ctx,
        stage_key,
        envelope,
        volley=volley,
        schema_errors=[],
        routed_via_collate=routed_via_collate,
    )
    if not lint and not schema:
        result.arbiter_result = mark_holistic_fabrication_cleared(
            envelope, arbiter_result, actions=actions
        )
        result.cleared = True
        result.lint_errors = []
        result.schema_errors = []
        result.actions = actions
        result.envelope = envelope
        result.message = "cleared by deterministic holistic repair"
        ctx.log(
            f"Holistic fabrication cleared ({stage_key}) — {len(actions)} action(s)",
            level="success",
            stage=stage_key,
            action_id="holistic_fabrication.cleared",
            detail={"actions": actions[:12], "deterministic": True},
            origin="pipeline",
        )
        return result

    if hf.get("llm_enabled", True) and int(hf.get("max_calls_per_stage_attempt") or 2) > 0:
        payload = {
            "stage_key": stage_key,
            "gaps": gaps,
            "stage_inputs": stage_inputs,
            "current_artifacts": envelope.get("artifacts") or {},
            "volley_excerpt": _volley_excerpt(volley),
            "arbiter_summary": {
                "verdict": (arbiter_result or {}).get("verdict"),
                "gaps": (arbiter_result or {}).get("gaps"),
                "reasoning_summary": (arbiter_result or {}).get("reasoning_summary"),
            }
            if arbiter_result
            else None,
        }
        llm_patch = _run_holistic_fabrication_llm(ctx, stage_key, payload, attempt=attempt)
        if llm_patch:
            result.used_llm = True
            art_patch = llm_patch.get("artifact_patches") or {}
            if art_patch:
                envelope["artifacts"] = _deep_merge_dict(envelope.get("artifacts") or {}, art_patch)
                actions.append("llm:artifact_patches")
            up_patch = llm_patch.get("upstream_patches") or {}
            if up_patch:
                applied = _apply_upstream_patches(ctx, up_patch)
                actions.extend([f"llm_upstream:{p}" for p in applied])
            env_patch = llm_patch.get("envelope_patches") or {}
            for key in ("status", "confidence", "reasoning_summary"):
                if key in env_patch and env_patch[key] is not None:
                    envelope[key] = env_patch[key]
            if llm_patch.get("reasoning_summary"):
                envelope["reasoning_summary"] = llm_patch["reasoning_summary"]
            if actions:
                envelope["status"] = "complete"

            lint, schema = _relint(
                ctx,
                stage_key,
                envelope,
                volley=volley,
                schema_errors=[],
                routed_via_collate=routed_via_collate,
            )

    if not lint and not schema:
        result.arbiter_result = mark_holistic_fabrication_cleared(
            envelope, arbiter_result, actions=actions
        )
        result.cleared = True
        result.lint_errors = []
        result.schema_errors = []
        result.actions = actions
        result.envelope = envelope
        result.message = "cleared by holistic fabrication"
        ctx.log(
            f"Holistic fabrication cleared ({stage_key}) — llm={result.used_llm}",
            level="success",
            stage=stage_key,
            action_id="holistic_fabrication.cleared",
            detail={"actions": actions[:12], "used_llm": result.used_llm},
            origin="pipeline",
        )
    else:
        result.lint_errors = lint
        result.schema_errors = schema
        result.envelope = envelope
        result.actions = actions
        result.message = f"holistic fabrication incomplete — lint={len(lint)} schema={len(schema)}"

    return result


def try_holistic_fabrication_from_staged(
    ctx: RunContext,
    stage_key: str,
    lint_errors: list[str] | None = None,
) -> bool:
    """Load staged artifact + last attempt; run holistic repair; write back if cleared."""
    from interview_mux.artifact_issue_triage import _read_stage_artifact, _write_stage_artifact

    rel, artifact = _read_stage_artifact(ctx, stage_key, staged=True)
    if not rel or not artifact:
        return False

    attempt_doc: dict[str, Any] = {}
    base = ctx.path("understanding", "stage_runs", stage_key)
    if base.is_dir():
        attempts = sorted(base.glob("attempt_*.json"))
        if attempts:
            try:
                attempt_doc = ctx.read_json(
                    f"understanding/stage_runs/{stage_key}/{attempts[-1].name}"
                )
            except Exception:
                attempt_doc = {}

    envelope = attempt_doc.get("envelope") or {
        "status": "blocked",
        "artifacts": artifact,
        "memory_updates": {},
        "needs": [],
        "follow_up_investigations": [],
    }
    if not envelope.get("artifacts"):
        envelope["artifacts"] = artifact

    hf_result = try_holistic_fabrication(
        ctx,
        stage_key,
        envelope,
        volley=attempt_doc.get("context_volley"),
        arbiter_result=attempt_doc.get("arbiter_result"),
        lint_errors=lint_errors or attempt_doc.get("deterministic_lint_errors"),
        schema_errors=attempt_doc.get("schema_errors"),
    )
    if not hf_result.cleared:
        return False

    _write_stage_artifact(ctx, stage_key, rel, hf_result.envelope.get("artifacts") or artifact)
    routing = hf_result.envelope.setdefault("_routing_meta", {})
    routing["structural_repair_cleared"] = True
    return True


def should_accept_holistic_fabrication(envelope: dict[str, Any]) -> bool:
    routing = envelope.get("_routing_meta") or {}
    return bool(routing.get("holistic_fabrication_cleared"))
