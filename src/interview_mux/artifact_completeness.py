"""Semantic completeness, gap-fill context, and incremental artifact merge."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable

from interview_mux.prompt_validation import (
    STAGE_ARTIFACT_DISK_PATHS,
    validate_artifact_write,
    validate_stage_artifacts,
)
from interview_mux.run_context import RunContext

GapRule = Callable[[dict[str, Any] | None], list[str]]

@dataclass(frozen=True)
class Gap:
    path: str
    reason: str

GAP_FILL_PROTECTED_PATHS: frozenset[str] = frozenset(
    {
        "thesis",
        "topics",
        "topics[].segment_ids",
        "topics[].name",
        "topics[].summary",
        "ordered_segment_ids",
        "segments",
        "segments[].segment_id",
        "segments[].type",
        "boundaries",
        "speakers",
        "speakers[].role",
        "speakers[].speaker_id",
        "evaluations",
        "gaps",
        "topic_relationships",
    }
)

def _is_protected_gap_path(path: str) -> bool:
    if path in GAP_FILL_PROTECTED_PATHS:
        return True
    for pat in GAP_FILL_PROTECTED_PATHS:
        if "[]" in pat:
            prefix = pat.split("[")[0]
            if path.startswith(prefix):
                return True
    return False

def _filter_protected_skip_fields(skip_fields: list[str]) -> list[str]:
    return [f for f in skip_fields if not _is_protected_gap_path(f)]

def _non_empty_str(val: Any) -> bool:
    return isinstance(val, str) and bool(val.strip())

def _gaps_analysis_state(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return ["(root)"]
    gaps: list[str] = []
    if not (data.get("themes") or []):
        gaps.append("themes")
    narrative = data.get("narrative") or {}
    if not _non_empty_str(narrative.get("thesis")):
        gaps.append("narrative.thesis")
    ident = data.get("interview_identity") or {}
    if not _non_empty_str(ident.get("one_line_summary")):
        gaps.append("interview_identity.one_line_summary")
    style = data.get("style") or {}
    if not _non_empty_str(style.get("tone")):
        gaps.append("style.tone")
    if not _non_empty_str(style.get("tone_class")):
        gaps.append("style.tone_class")
    if not _non_empty_str(style.get("format_class")):
        gaps.append("style.format_class")
    return gaps

def _gaps_analysis_state_speakers_only(data: dict[str, Any] | None) -> list[str]:
    """Incremental analysis_state check after speaker_roles memory merge."""
    if not data:
        return ["speakers"]
    return _gaps_speakers({"speakers": data.get("speakers") or []})

def _gaps_content_brief(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return ["thesis", "topics"]
    gaps: list[str] = []
    if not _non_empty_str(data.get("thesis")):
        gaps.append("thesis")
    topics = data.get("topics") or []
    if not topics:
        gaps.append("topics")
    else:
        for i, t in enumerate(topics):
            if isinstance(t, dict) and not _non_empty_str(t.get("summary")):
                gaps.append(f"topics[{i}].summary")
    return gaps

def _gaps_content_brief_reanchor(data: dict[str, Any] | None) -> list[str]:
    gaps = _gaps_content_brief(data)
    if not data:
        return gaps
    for i, t in enumerate(data.get("topics") or []):
        if isinstance(t, dict) and not (t.get("segment_ids") or []):
            gaps.append(f"topics[{i}].segment_ids")
    if not (data.get("topic_relationships") or []):
        gaps.append("topic_relationships")
    return gaps

def _gaps_speakers(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return ["speakers"]
    speakers = data.get("speakers") if "speakers" in data else data
    if not isinstance(speakers, list) or not speakers:
        return ["speakers"]
    gaps: list[str] = []
    for i, sp in enumerate(speakers):
        if not isinstance(sp, dict):
            gaps.append(f"speakers[{i}]")
            continue
        if not sp.get("role"):
            gaps.append(f"speakers[{i}].role")
    if speakers and all(
        isinstance(sp, dict) and str(sp.get("role", "")).strip().lower() == "unknown"
        for sp in speakers
    ):
        gaps.append("speakers.all_unknown_roles")
    return gaps

def _gaps_sound_design_plan(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return ["coherence"]
    gaps: list[str] = []
    coherence = data.get("coherence") or {}
    if not _non_empty_str(coherence.get("sonic_identity")):
        gaps.append("coherence.sonic_identity")
    if not (data.get("palettes") or []):
        gaps.append("palettes")
    return gaps

def _gaps_investigation_queue(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return []
    return []

def _gaps_generic_nonempty(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return ["(root)"]
    return []

def _gaps_manifest(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return ["segments"]
    segs = data.get("segments") or []
    if not segs:
        return ["segments"]
    return []

def _gaps_gap_report(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return ["interviewer_lines"]
    if "interviewer_lines" not in data:
        return ["interviewer_lines"]
    if not isinstance(data.get("interviewer_lines"), list):
        return ["interviewer_lines"]
    return []

def _gaps_mmaudio_qa(data: dict[str, Any] | None) -> list[str]:
    if not data:
        return ["assets"]
    assets = data.get("assets")
    if not isinstance(assets, list):
        return ["assets"]
    return []

STAGE_GAP_RULES: dict[str, GapRule] = {
    "content_brief_reanchor": _gaps_content_brief_reanchor,
}

STAGED_ANALYSIS_STATE_GAP_RULES: dict[str, GapRule] = {
    "speaker_roles": _gaps_analysis_state_speakers_only,
}

ARTIFACT_COMPLETENESS_RULES: dict[str, GapRule] = {
    "understanding/analysis_state.json": _gaps_analysis_state,
    "understanding/content_brief.json": _gaps_content_brief,
    "understanding/speakers.json": _gaps_speakers,
    "understanding/sound_design_plan.json": _gaps_sound_design_plan,
    "understanding/investigation_queue.json": _gaps_investigation_queue,
    "understanding/gap_evaluations.json": _gaps_generic_nonempty,
    "understanding/gap_report.json": _gaps_gap_report,
    "understanding/delivery_brief.json": _gaps_generic_nonempty,
    "segments/boundaries.json": _gaps_generic_nonempty,
    "segments/manifest.json": _gaps_manifest,
    "master/coverage_audit.json": _gaps_generic_nonempty,
    "master/narrative_plan.json": _gaps_generic_nonempty,
    "master/selection.json": _gaps_generic_nonempty,
    "master/transitions.json": _gaps_generic_nonempty,
    "master/podcast_sfx_brief.json": _gaps_generic_nonempty,
    "show_notes/show_description.json": _gaps_generic_nonempty,
    "sound_design/sfx_prompts.json": _gaps_generic_nonempty,
    "sound_design/mmaudio_qa.json": _gaps_mmaudio_qa,
}

def _gap_rule_for(rel_path: str, stage_key: str | None = None) -> GapRule | None:
    if stage_key and stage_key in STAGE_GAP_RULES:
        rel_for_stage = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
        if rel_for_stage == rel_path:
            return STAGE_GAP_RULES[stage_key]
    return ARTIFACT_COMPLETENESS_RULES.get(rel_path)

def compute_gaps(
    rel_path: str,
    data: dict[str, Any] | None,
    *,
    stage_key: str | None = None,
    ctx: RunContext | None = None,
) -> list[Gap]:
    if stage_key:
        from interview_mux.sufficiency_engine import evaluate, findings_to_gap_paths

        findings = evaluate(stage_key, data, ctx)
        if findings:
            return [Gap(path=p, reason="incomplete") for p in findings_to_gap_paths(findings)]
    rule = _gap_rule_for(rel_path, stage_key)
    if not rule:
        return []
    return [Gap(path=p, reason="incomplete") for p in rule(data)]

def compute_staged_write_gaps(
    rel_path: str,
    data: dict[str, Any] | None,
    *,
    stage_id: str,
) -> list[Gap]:
    """
    Semantic gap checks when flushing staged writes.
    Bundled sidecar artifacts (e.g. analysis_state during speaker_roles) use
    stage-appropriate rules instead of full downstream completeness.
    """
    producer = STAGE_ARTIFACT_DISK_PATHS.get(stage_id)
    if rel_path == "understanding/analysis_state.json" and producer != rel_path:
        rule = STAGED_ANALYSIS_STATE_GAP_RULES.get(stage_id)
        if rule is not None:
            return [Gap(path=p, reason="incomplete") for p in rule(data)]
        return []
    return compute_gaps(rel_path, data, stage_key=stage_id)

def _status_stage_key(rel_path: str, ctx: RunContext) -> str | None:
    if rel_path == "understanding/content_brief.json" and ctx.is_done("content_brief_reanchor"):
        return "content_brief_reanchor"
    return None

def artifact_status(rel_path: str, ctx: RunContext) -> str:
    """pending | partial | complete"""
    if not ctx.artifact_exists(rel_path):
        return "pending"
    if rel_path.endswith(".txt"):
        from interview_mux.write_staging import resolve_read_path

        p = resolve_read_path(ctx, rel_path)
        return "complete" if p.is_file() and p.stat().st_size > 0 else "partial"
    raw = ctx.read_json(rel_path)
    data = raw if isinstance(raw, dict) else None
    from interview_mux.llm_output_resilience import artifact_resilience_partial

    if artifact_resilience_partial(data):
        return "partial"
    schema_errors = validate_artifact_write(rel_path, data) if data else ["missing"]
    semantic = compute_gaps(rel_path, data, stage_key=_status_stage_key(rel_path, ctx), ctx=ctx)
    if rel_path == "sound_design/mmaudio_qa.json" and data:
        semantic.extend([Gap(path=p, reason="incomplete") for p in _mmaudio_qa_wav_parity_gaps(ctx, data)])
    if schema_errors or semantic:
        return "partial"
    return "complete"

def _mmaudio_qa_wav_parity_gaps(ctx: RunContext, data: dict[str, Any]) -> list[str]:
    out: list[str] = []
    assets = data.get("assets") if isinstance(data.get("assets"), list) else []
    qa_ids = {
        str(row.get("asset_id"))
        for row in assets
        if isinstance(row, dict) and row.get("asset_id")
    }
    wav_ids = {p.stem for p in ctx.final_path("sound_design", "assets").glob("*.wav")}
    for aid in sorted(wav_ids - qa_ids):
        out.append(f"assets_missing_qa:{aid}")
    for aid in sorted(qa_ids - wav_ids):
        out.append(f"qa_missing_wav:{aid}")
    return out

def artifact_ready_for_review(rel_path: str, ctx: RunContext) -> bool:
    """True when artifact exists and passes schema + semantic completeness."""
    return artifact_status(rel_path, ctx) == "complete"

def analysis_profile_ready_for_review(ctx: RunContext) -> bool:
    """True after understanding analysis populated the interview profile."""
    from interview_mux.llm_flow_hardening import ANALYSIS_READY_ARTIFACT_PATHS, flow_hardening_enabled

    if not ctx.is_done("optimal_questions"):
        return False
    if flow_hardening_enabled():
        for rel in ANALYSIS_READY_ARTIFACT_PATHS:
            if artifact_status(rel, ctx) != "complete":
                return False
    if not ctx.artifact_exists("understanding/analysis_state.json"):
        return False
    raw = ctx.read_json("understanding/analysis_state.json")
    if not isinstance(raw, dict):
        return False
    completion = raw.get("completion") or {}
    if completion.get("analysis_ready"):
        return True
    return artifact_ready_for_review("understanding/analysis_state.json", ctx)

def story_board_ready_for_gui(ctx: RunContext) -> bool:
    """True when Story board panel has meaningful workspace content."""
    if not ctx.is_done("content_context"):
        return False
    return ctx.artifact_exists("understanding/content_brief.json")

def timeline_ready_for_gui(ctx: RunContext) -> bool:
    """True when NLE timeline has classified segments."""
    if not ctx.artifact_exists("segments/manifest.json"):
        return False
    manifest = ctx.read_json("segments/manifest.json")
    if not isinstance(manifest, dict):
        return False
    segments = manifest.get("segments")
    return isinstance(segments, list) and len(segments) > 0

def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, val in patch.items():
        if val is None:
            continue
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        elif key in out and isinstance(out[key], list) and isinstance(val, list):
            if not val:
                continue
            if key in ("themes", "major_questions", "entities", "hypotheses", "open_questions"):
                from interview_mux.analysis_memory import merge_memory_updates

                merged, _ = merge_memory_updates({key: out.get(key, [])}, {key: val})
                out[key] = merged.get(key, out.get(key))
            else:
                out[key] = val if patch.get(f"{key}_replace") else out[key] + [
                    x for x in val if x not in out[key]
                ]
        else:
            out[key] = copy.deepcopy(val)
    return out

def merge_artifact(
    rel_path: str,
    existing: dict[str, Any] | None,
    patch: dict[str, Any],
    *,
    stage_key: str | None = None,
    preserve_operator: bool = True,
) -> dict[str, Any]:
    if not existing:
        return copy.deepcopy(patch)
    if not patch:
        return copy.deepcopy(existing)

    if rel_path == "understanding/analysis_state.json" and preserve_operator:
        verified = bool((existing.get("meta") or {}).get("operator_verified"))
        if verified:
            protected = ("themes", "major_questions", "narrative", "style")
            patch = {k: v for k, v in patch.items() if k not in protected}

    if rel_path == "segments/manifest.json" and "segments" in patch:
        ex_segs = {s.get("segment_id"): s for s in (existing.get("segments") or []) if isinstance(s, dict)}
        for seg in patch.get("segments") or []:
            if isinstance(seg, dict) and seg.get("segment_id"):
                sid = seg["segment_id"]
                if sid in ex_segs:
                    ex_segs[sid] = {**ex_segs[sid], **seg}
                else:
                    ex_segs[sid] = seg
        from interview_mux.segment_timeline import sort_segments_by_start_ms

        merged_segments = sort_segments_by_start_ms(list(ex_segs.values()))
        return {**existing, "segments": merged_segments}

    if rel_path == "understanding/sound_design_plan.json":
        return _deep_merge(existing, patch)

    if rel_path == "understanding/speakers.json" and "speakers" in patch:
        ex_by_id: dict[str, dict[str, Any]] = {}
        for sp in existing.get("speakers") or []:
            if isinstance(sp, dict) and sp.get("speaker_id"):
                ex_by_id[str(sp["speaker_id"])] = copy.deepcopy(sp)
        for sp in patch.get("speakers") or []:
            if isinstance(sp, dict) and sp.get("speaker_id"):
                sid = str(sp["speaker_id"])
                if sid in ex_by_id:
                    ex_by_id[sid] = {**ex_by_id[sid], **sp}
                else:
                    ex_by_id[sid] = copy.deepcopy(sp)
        return {**existing, "speakers": list(ex_by_id.values())}

    return _deep_merge(existing, patch)

def hydrate_manifest_from_boundaries(ctx: RunContext, manifest: dict[str, Any]) -> dict[str, Any]:
    """Fill timeline fields on manifest segments from segments/boundaries.json."""
    if not isinstance(manifest, dict):
        return manifest
    segs = manifest.get("segments")
    if not isinstance(segs, list):
        return manifest

    from interview_mux.segment_timeline_standard import contract_ordered_segment_ids, segmentation_cfg

    boundary_doc: dict[str, Any] | None = None
    if ctx.artifact_exists("segments/boundaries.json"):
        raw = ctx.read_json("segments/boundaries.json")
        if isinstance(raw, dict):
            boundary_doc = raw

    boundary_by_id: dict[str, dict[str, Any]] = {}
    if boundary_doc:
        for row in boundary_doc.get("boundaries") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                boundary_by_id[str(row["segment_id"])] = row

    contract_ids = contract_ordered_segment_ids(boundary_doc)
    if not contract_ids and not segs:
        return manifest
    if not boundary_by_id:
        return manifest

    words: list[dict[str, Any]] = []
    if ctx.artifact_exists("transcript/full.json"):
        tr = ctx.read_json("transcript/full.json")
        if isinstance(tr, dict):
            words = [w for w in (tr.get("words") or []) if isinstance(w, dict)]

    speakers_by_id: dict[str, str] = {}
    if ctx.artifact_exists("understanding/speakers.json"):
        sp_doc = ctx.read_json("understanding/speakers.json")
        if isinstance(sp_doc, dict):
            for sp in sp_doc.get("speakers") or []:
                if isinstance(sp, dict) and sp.get("speaker_id"):
                    speakers_by_id[str(sp["speaker_id"])] = str(sp.get("role") or "unknown")

    manifest_by_id = {
        str(seg.get("segment_id")): dict(seg)
        for seg in segs
        if isinstance(seg, dict) and seg.get("segment_id")
    }
    seg_cfg = segmentation_cfg()
    order = contract_ids or sorted(manifest_by_id.keys())
    hydrated: list[dict[str, Any]] = []
    for sid in order:
        out = dict(manifest_by_id.get(sid) or {"segment_id": sid})
        out["segment_id"] = sid
        boundary = boundary_by_id.get(sid)
        if not boundary:
            hydrated.append(out)
            continue
        if boundary.get("start_ms") is not None:
            out["start_ms"] = int(boundary["start_ms"])
        if boundary.get("end_ms") is not None:
            out["end_ms"] = int(boundary["end_ms"])
        if boundary.get("speaker_id"):
            out["speaker_id"] = str(boundary["speaker_id"])
        speaker_id = str(out.get("speaker_id") or "")
        if speaker_id:
            out["speaker_role"] = speakers_by_id.get(speaker_id, out.get("speaker_role") or "unknown")
        if words and out.get("start_ms") is not None and out.get("end_ms") is not None:
            start_ms = int(out["start_ms"])
            end_ms = int(out["end_ms"])
            span = [
                w
                for w in words
                if int(w.get("start_ms", 0)) < end_ms and int(w.get("end_ms", 0)) > start_ms
            ]
            text = " ".join(str(w.get("text", "")) for w in span if w.get("text"))
            if text:
                out["text"] = text
        hydrated.append(out)

    from interview_mux.segment_timeline import sort_segments_by_start_ms

    if seg_cfg.get("drop_orphan_manifest_rows", True) and contract_ids:
        allowed = set(contract_ids)
        hydrated = [row for row in hydrated if str(row.get("segment_id")) in allowed]

    return {**manifest, "segments": sort_segments_by_start_ms(hydrated)}

def build_gap_fill_context(ctx: RunContext, stage_key: str) -> dict[str, Any] | None:
    from interview_mux.null_field_policy import null_acknowledged_paths

    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel:
        return None
    existing: dict[str, Any] | None = None
    if ctx.artifact_exists(rel):
        raw = ctx.read_json(rel)
        if isinstance(raw, dict):
            existing = raw
    gaps = compute_gaps(rel, existing, stage_key=stage_key)
    schema_errors = validate_artifact_write(rel, existing) if existing else []
    stage_errors = []
    if existing and stage_key:
        stage_errors = validate_stage_artifacts(stage_key, existing)

    all_gaps = list({g.path for g in gaps})
    for e in schema_errors + stage_errors:
        all_gaps.append(e.split(":")[0] if ":" in e else e)
    if existing:
        ack = set(null_acknowledged_paths(existing))
        all_gaps = [g for g in all_gaps if g not in ack and not any(g.startswith(a) for a in ack)]

    if not existing and not all_gaps:
        all_gaps = ["(root)"]

    skip_fields: list[str] = []
    if existing:
        skip_fields.extend(null_acknowledged_paths(existing))
        rule = _gap_rule_for(rel, stage_key)
        if rule:
            complete_paths = set()
            probe = copy.deepcopy(existing)
            for g in gaps:
                pass
            for key in list(existing.keys()):
                trial = copy.deepcopy(existing)
                if key in trial:
                    del trial[key]
                if rule(trial) == rule(existing):
                    skip_fields.append(key)

    if existing and not all_gaps:
        return {
            "artifact_path": rel,
            "existing": existing,
            "gaps": [],
            "skip_fields": _filter_protected_skip_fields(list(existing.keys())),
            "instructions": "Artifact is complete; return empty artifacts unless correcting errors.",
        }

    return {
        "artifact_path": rel,
        "existing": existing,
        "gaps": all_gaps[:24],
        "skip_fields": _filter_protected_skip_fields(skip_fields[:32]),
        "instructions": (
            "Only fill listed gaps. Do not overwrite skip_fields or satisfied keys in existing. "
            "Return patch-only artifacts when existing is non-null."
        ),
    }

def attach_gap_fill_to_input(ctx: RunContext, stage_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    gfc = build_gap_fill_context(ctx, stage_key)
    if gfc:
        payload = {**payload, "gap_fill_context": gfc}
    return payload

def should_run_stage_for_artifact(ctx: RunContext, stage_key: str) -> bool:
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel:
        return True
    if not ctx.artifact_exists(rel):
        return True
    raw = ctx.read_json(rel)
    if not isinstance(raw, dict):
        return True
    from interview_mux.llm_output_resilience import artifact_resilience_partial

    if artifact_resilience_partial(raw):
        return True
    if validate_artifact_write(rel, raw):
        return True
    if compute_gaps(rel, raw, stage_key=stage_key):
        return True
    stage_errors = validate_stage_artifacts(stage_key, raw)
    return bool(stage_errors)

def stage_keys_for_artifact_path(rel_path: str) -> list[str]:
    return [k for k, p in STAGE_ARTIFACT_DISK_PATHS.items() if p == rel_path]

def make_stage_persist(
    rel_path: str,
    stage_key: str,
    *,
    transform: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> Callable[[RunContext, dict[str, Any]], None]:
    from interview_mux.artifact_writes import write_validated_artifact

    def persist(ctx: RunContext, artifacts: dict[str, Any]) -> None:
        data = transform(artifacts) if transform else artifacts
        write_validated_artifact(
            ctx,
            rel_path,
            data,
            merge_from_disk=True,
            stage_key=stage_key,
        )

    return persist
