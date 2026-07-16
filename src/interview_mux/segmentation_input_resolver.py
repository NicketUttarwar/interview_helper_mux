"""Resolve segmentation inputs and enforce field parity across artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.segment_timeline_standard import (
    contract_ordered_segment_ids,
    segmentation_cfg,
    validate_boundary_timeline,
)
from interview_mux.stage_coupling import contract_timeline_valid, read_segment_contract


SEGMENTATION_INPUT_DEPS: tuple[tuple[str, str, bool], ...] = (
    ("boundaries", "segments/boundaries.json", True),
    ("transcript", "transcript/full.json", True),
    ("speakers", "understanding/speakers.json", True),
    ("content_brief", "understanding/content_brief.json", False),
    ("analysis_state", "understanding/analysis_state.json", False),
)


@dataclass
class SegmentationInputBundle:
    boundaries: dict[str, Any] | None = None
    transcript: dict[str, Any] | None = None
    speakers: dict[str, Any] | None = None
    content_brief: dict[str, Any] | None = None
    analysis_state: dict[str, Any] | None = None
    source_paths: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _path_meta(ctx: RunContext, rel: str) -> dict[str, Any]:
    from interview_mux.write_staging import pending_stage_for_path, resolve_read_path

    resolved = resolve_read_path(ctx, rel)
    pending = pending_stage_for_path(ctx, rel)
    run_dir = Path(ctx.run_dir)
    try:
        display = str(resolved.relative_to(run_dir))
    except ValueError:
        display = str(resolved)
    return {
        "path": display,
        "staged": bool(pending),
        "pending_stage": pending,
    }


def resolve_segmentation_inputs(
    ctx: RunContext,
    *,
    staged_boundary_ok: bool = True,
) -> SegmentationInputBundle:
    bundle = SegmentationInputBundle()
    for key, rel, required in SEGMENTATION_INPUT_DEPS:
        if not ctx.artifact_exists(rel):
            if required:
                bundle.errors.append(f"missing required artifact: {rel}")
            continue
        try:
            data = ctx.read_json(rel)
        except (ValueError, OSError) as exc:
            bundle.errors.append(f"failed to read {rel}: {exc}")
            continue
        if not isinstance(data, dict):
            bundle.errors.append(f"{rel} is not a JSON object")
            continue
        setattr(bundle, key, data)
        bundle.source_paths[key] = _path_meta(ctx, rel)
    if not staged_boundary_ok and bundle.source_paths.get("boundaries", {}).get("staged"):
        bundle.errors.append("staged boundaries not allowed for this operation")
    return bundle


def assert_boundary_contract_ready(bundle: SegmentationInputBundle) -> list[str]:
    errors: list[str] = []
    if not bundle.boundaries:
        return ["segments/boundaries.json missing"]
    contract = read_segment_contract(bundle.boundaries)
    ids = contract_ordered_segment_ids(bundle.boundaries)
    if not ids:
        errors.append("segment_contract has no segment_ids")
    if not contract_timeline_valid(bundle.boundaries):
        timeline_errors = (contract or {}).get("timeline_errors") or ["boundary timeline invalid"]
        errors.append(f"boundary timeline invalid: {timeline_errors[0]}")
    return errors


def _speakers_by_id(speakers_doc: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(speakers_doc, dict):
        return out
    for sp in speakers_doc.get("speakers") or []:
        if isinstance(sp, dict) and sp.get("speaker_id"):
            out[str(sp["speaker_id"])] = str(sp.get("role") or "unknown")
    return out


def assert_field_parity(
    boundaries_doc: dict[str, Any] | None,
    manifest_doc: dict[str, Any] | None,
    speakers_doc: dict[str, Any] | None,
    *,
    cfg: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(boundaries_doc, dict) or not isinstance(manifest_doc, dict):
        return ["boundaries and manifest required for parity check"]
    contract_ids = contract_ordered_segment_ids(boundaries_doc)
    if not contract_ids:
        return ["no segment_contract segment_ids"]
    boundary_by_id = {
        str(b["segment_id"]): b
        for b in (boundaries_doc.get("boundaries") or [])
        if isinstance(b, dict) and b.get("segment_id")
    }
    manifest_by_id = {
        str(s["segment_id"]): s
        for s in (manifest_doc.get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }
    speakers = _speakers_by_id(speakers_doc)
    seg_cfg = segmentation_cfg(cfg)
    snap_tol = int(
        ((cfg or merged_config()).get("analysis") or {})
        .get("artifact_issue_triage", {})
        .get("boundary_snap_tolerance_ms", 500)
    )

    for sid in contract_ids:
        if sid not in manifest_by_id:
            errors.append(f"manifest missing segment_id {sid}")
            continue
        brow = boundary_by_id.get(sid)
        mrow = manifest_by_id[sid]
        if not brow:
            errors.append(f"boundaries missing segment_id {sid}")
            continue
        for field_name in ("start_ms", "end_ms"):
            bv, mv = brow.get(field_name), mrow.get(field_name)
            if bv is None or mv is None:
                errors.append(f"{sid} missing {field_name}")
                continue
            if abs(int(bv) - int(mv)) > snap_tol:
                errors.append(f"{sid} {field_name} mismatch: boundary={bv} manifest={mv}")
        b_spk = str(brow.get("speaker_id") or "")
        m_spk = str(mrow.get("speaker_id") or "")
        if b_spk and m_spk and b_spk != m_spk:
            errors.append(f"{sid} speaker_id mismatch: boundary={b_spk} manifest={m_spk}")
        if b_spk and b_spk not in speakers:
            errors.append(f"{sid} speaker_id {b_spk} not in speakers.json")
        if seg_cfg.get("enforce_field_parity", True):
            role = str(mrow.get("speaker_role") or "")
            expected = speakers.get(b_spk or m_spk, "")
            if expected and role and role != expected and role != "unknown":
                errors.append(f"{sid} speaker_role mismatch: manifest={role} speakers={expected}")

    if seg_cfg.get("drop_orphan_manifest_rows", True):
        for sid in manifest_by_id:
            if sid not in contract_ids:
                errors.append(f"manifest orphan segment_id {sid} not in contract")

    return errors


def assert_reference_closure(
    ctx: RunContext,
    manifest_doc: dict[str, Any] | None,
    *,
    require_full_coverage: bool = True,
) -> list[str]:
    errors: list[str] = []
    bundle = resolve_segmentation_inputs(ctx)
    errors.extend(bundle.errors)
    errors.extend(assert_boundary_contract_ready(bundle))
    if isinstance(manifest_doc, dict):
        errors.extend(assert_field_parity(bundle.boundaries, manifest_doc, bundle.speakers))
        if require_full_coverage:
            contract_ids = set(contract_ordered_segment_ids(bundle.boundaries))
            manifest_ids = {
                str(s.get("segment_id"))
                for s in (manifest_doc.get("segments") or [])
                if isinstance(s, dict) and s.get("segment_id")
            }
            missing = sorted(contract_ids - manifest_ids)
            if missing:
                errors.append(f"reference closure: missing manifest ids: {', '.join(missing[:4])}")
    return errors


def build_classification_payload(ctx: RunContext) -> dict[str, Any]:
    """Canonical segment_classification stage input."""
    from interview_mux.analysis_memory import load_analysis_state
    from interview_mux.classification_obligation import (
        build_obligation,
        classification_context_cfg,
    )
    from interview_mux.context_volley import transcript_quality_for_ctx
    from interview_mux.disfluency.context import attach_disfluency_context
    from interview_mux.interview_spine.compact import attach_spine_to_payload
    from interview_mux.conversation_context import attach_conversation_context
    from interview_mux.source_topology import attach_adaptation_to_payload
    from interview_mux.stage_enrichment import compact_value_features_summary

    bundle = resolve_segmentation_inputs(ctx)
    if bundle.errors:
        raise ValueError("; ".join(bundle.errors[:4]))
    contract_errors = assert_boundary_contract_ready(bundle)
    if contract_errors:
        raise ValueError("; ".join(contract_errors[:4]))

    payload: dict[str, Any] = {
        "boundaries": bundle.boundaries,
        "transcript": bundle.transcript,
        "speakers": bundle.speakers,
        "content_brief": bundle.content_brief,
        "_segmentation_source_paths": bundle.source_paths,
    }
    quality = transcript_quality_for_ctx(ctx)
    if quality:
        payload["transcript_quality"] = quality
    vf = compact_value_features_summary(ctx)
    if vf:
        payload["value_features_summary"] = vf
    attach_spine_to_payload(ctx, payload, "segment_classification")
    if classification_context_cfg().get("classification_obligation_enabled", True):
        payload["classification_obligation"] = build_obligation(
            ctx,
            bundle.boundaries or {},
            bundle.speakers,
        )
    payload = attach_conversation_context(ctx, payload, "segment_classification")
    return attach_disfluency_context(attach_adaptation_to_payload(ctx, payload), ctx)


def segmentation_review_report(ctx: RunContext) -> dict[str, Any]:
    """Parity and cross-artifact summary for unified review API."""
    from interview_mux.artifact_cross_validate import validate_cross_artifacts_for_stage
    from interview_mux.write_staging import has_pending_writes, list_pending_paths

    bundle = resolve_segmentation_inputs(ctx)
    boundaries = bundle.boundaries or {}
    contract = read_segment_contract(boundaries) or {}
    manifest = None
    if has_pending_writes(ctx, "segment_classification"):
        from interview_mux.artifact_issue_triage import _read_stage_artifact

        _rel, manifest = _read_stage_artifact(ctx, "segment_classification", staged=True)

    parity_errors: list[str] = []
    if isinstance(manifest, dict):
        parity_errors = assert_field_parity(bundle.boundaries, manifest, bundle.speakers)

    cross_errors: list[str] = []
    if has_pending_writes(ctx, "segment_classification"):
        cross_errors = validate_cross_artifacts_for_stage(ctx, "segment_classification", staged=True)

    return {
        "source_paths": bundle.source_paths,
        "contract": {
            "segment_count": contract.get("segment_count"),
            "timeline_valid": contract.get("timeline_valid"),
            "segment_ids": (contract.get("segment_ids") or [])[:4],
            "timeline_errors": (contract.get("timeline_errors") or [])[:4],
        },
        "parity_errors": parity_errors[:12],
        "cross_validate_errors": cross_errors[:12],
        "pending_paths": list_segmentation_review_paths(ctx),
        "ready": not bundle.errors and not parity_errors and not cross_errors,
    }


def list_segmentation_review_paths(ctx: RunContext) -> list[str]:
    from interview_mux.write_staging import staging_root

    paths: list[str] = []
    for stage_id in ("boundary_detection", "segment_classification"):
        root = staging_root(ctx, stage_id)
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.name != ".write.lock":
                rel = str(p.relative_to(root)).replace("\\", "/")
                if rel not in paths:
                    paths.append(rel)
    return sorted(paths)


def segmentation_pending_stages(ctx: RunContext) -> list[str]:
    from interview_mux.write_staging import has_pending_writes

    out: list[str] = []
    for stage_id in ("boundary_detection", "segment_classification"):
        if has_pending_writes(ctx, stage_id):
            out.append(stage_id)
    return out
