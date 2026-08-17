"""Shared helpers for downstream progression / cross-stage sanity checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interview_mux.artifact_completeness import artifact_status
from interview_mux.artifact_cross_validate import validate_cross_artifacts_for_stage
from interview_mux.artifact_repairs import is_manifest_segment_id, sync_content_brief_topic_segment_ids
from interview_mux.pipeline import ANALYSIS_ORDER, DELIVERY_ORDER
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS, validate_artifact_write
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness
from interview_mux.stage_input_checks import collect_stage_input_issues
from interview_mux.write_staging import record_pending_approval, staging_root

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "prompts" / "stage_artifacts.json"

# Full P0 spine from content_context (index 9 in ANALYSIS_ORDER).
PROGRESSION_START_STAGE = "content_context"

PROGRESSION_P0_STAGES = ANALYSIS_ORDER[
    ANALYSIS_ORDER.index("content_context") : ANALYSIS_ORDER.index("content_brief_reanchor") + 1
]

PROGRESSION_ANALYSIS_STAGES = ANALYSIS_ORDER[ANALYSIS_ORDER.index(PROGRESSION_START_STAGE) :]

# Flow stages covered by stage_artifacts.json fixtures (audio/mix stages need ASSETS venvs).
PROGRESSION_FLOW_STAGES = [
    "topic_coverage_audit",
    "narrative_arc_plan",
    "full_master_ranking",
    "transitions",
    "sound_design_plan",
    "edl_narrative_audit",
]

PROGRESSION_BUILD_STAGES = [
    "sound_design_vo_finalize",
    "edl",
]

FULL_PROGRESSION_CHAIN = [
    *PROGRESSION_ANALYSIS_STAGES,
    *PROGRESSION_FLOW_STAGES,
    *PROGRESSION_BUILD_STAGES,
]

BUILD_STAGE_ARTIFACT_PATHS: dict[str, str] = {
    "episode_structure_compose": "understanding/episode_structure.json",
    "sound_design_vo_finalize": "understanding/sound_design_plan.json",
    "edl": "master/edl.json",
}


def load_stage_fixtures() -> dict[str, Any]:
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def _enrich_boundaries(doc: dict[str, Any]) -> dict[str, Any]:
    rows = doc.get("boundaries") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        enriched = dict(row)
        enriched.setdefault("speaker_id", "spk_001")
        enriched.setdefault("type", "interview")
        out.append(enriched)
    return {"boundaries": out}


def seed_prefix_through_boundary(ctx: RunContext, fixtures: dict[str, Any]) -> None:
    """Minimal committed artifacts for stages before segment_classification."""
    from run_fixtures import (
        init_run_meta_for_test,
        minimal_content_brief,
        minimal_manifest,
        minimal_manifest_segment,
        minimal_speakers,
        minimal_source_acoustic_profile,
        populated_analysis_state,
    )

    init_run_meta_for_test(ctx)
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    (ctx.path("ingest") / "normalized.wav").write_bytes(b"RIFF" + b"\x00" * 64)
    ctx.write_json(
        "transcript/full.json",
        {
            "segments": [
                {
                    "start_ms": 0,
                    "end_ms": 12000,
                    "speaker_id": "spk_001",
                    "text": "Tell me about the founding constraints.",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json("understanding/speakers.json", fixtures.get("speaker_roles") or minimal_speakers(), skip_handoff=True)
    ctx.write_json(
        "understanding/content_brief.json",
        fixtures.get("content_context") or minimal_content_brief(),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/analysis_state.json",
        populated_analysis_state(ctx.run_id),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/source_acoustic_profile.json",
        minimal_source_acoustic_profile(),
        skip_handoff=True,
    )
    boundaries = _enrich_boundaries(
        fixtures.get("boundary_detection")
        or {
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 12000,
                    "speaker_id": "spk_001",
                    "proposed_split_reason": "topic_shift",
                }
            ]
        }
    )
    ctx.write_json("segments/boundaries.json", boundaries, skip_handoff=True)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_001")),
        skip_handoff=True,
    )
    for sid in ANALYSIS_ORDER[: ANALYSIS_ORDER.index(PROGRESSION_START_STAGE)]:
        ctx.mark_done(sid, force=True)
    ctx.mark_done("transcript_review", force=True)
    ctx.mark_done("disfluency_review", force=True)


def build_manifest_from_fixtures(fixtures: dict[str, Any]) -> dict[str, Any]:
    """Merge boundary_detection + segment_classification fixtures into a full manifest."""
    from run_fixtures import minimal_manifest_segment

    boundaries_doc = _enrich_boundaries(fixtures.get("boundary_detection") or {})
    boundaries = {
        str(b.get("segment_id")): b
        for b in boundaries_doc.get("boundaries") or []
        if isinstance(b, dict) and b.get("segment_id")
    }
    rows = (fixtures.get("segment_classification") or {}).get("segments") or []
    if not rows:
        return {"segments": [minimal_manifest_segment()]}
    segments: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or f"seg_{i + 1:03d}")
        base = dict(boundaries.get(sid) or {})
        seg = {
            **minimal_manifest_segment(
                sid,
                start_ms=int(base.get("start_ms", i * 5000)),
                end_ms=int(base.get("end_ms", (i + 1) * 5000)),
                text=str(base.get("text") or f"Segment {sid} transcript excerpt."),
            ),
            **row,
        }
        segments.append(seg)
    return {"segments": segments}


def _sound_design_plan_patch(stage_id: str, fixtures: dict[str, Any]) -> dict[str, Any]:
    """Return only keys this stage owns — avoid empty default coherence clobbering palettes."""
    partial = dict(fixtures.get(stage_id) or {})
    return {k: v for k, v in partial.items() if k in ("assets", "flow_plans", "generated", "coherence", "palettes")}


def _sound_design_plan_doc(stage_id: str, fixtures: dict[str, Any]) -> dict[str, Any]:
    from run_fixtures import sound_design_plan_with

    if stage_id == "sound_design_palettes":
        partial = fixtures.get("sound_design_palettes") or {}
        return sound_design_plan_with(
            palettes=partial.get("palettes") or [],
            coherence=partial.get("coherence") or {},
        )
    if stage_id == "sound_design_plan":
        return _sound_design_plan_patch(stage_id, fixtures)
    return sound_design_plan_with()


def write_stage_producer_artifact(
    ctx: RunContext,
    stage_id: str,
    fixtures: dict[str, Any],
) -> str | None:
    """Write the on-disk producer artifact for ``stage_id``; return relative path."""
    from interview_mux.prompt_validation import validate_artifact_write
    from interview_mux.write_staging import write_committed_json

    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_id) or BUILD_STAGE_ARTIFACT_PATHS.get(stage_id)
    if not rel:
        return None
    if stage_id == "segment_classification":
        doc = build_manifest_from_fixtures(fixtures)
    elif stage_id == "boundary_detection":
        doc = _enrich_boundaries(fixtures.get("boundary_detection") or {"boundaries": []})
    elif stage_id == "content_brief_reanchor":
        # Reanchor has its own authoritative fixture.  Reusing a prior sparse
        # content_context artifact makes the full contract sanity test fail for
        # reasons unrelated to the reanchor producer.
        fixture_doc = fixtures.get("content_brief_reanchor")
        if isinstance(fixture_doc, dict):
            ctx.write_json(
                "understanding/content_brief.json",
                fixture_doc,
                skip_handoff=True,
            )
        sync_content_brief_topic_segment_ids(ctx)
        doc = ctx.read_json("understanding/content_brief.json")
    elif stage_id == "sonic_context_build":
        sonic_path = Path(__file__).parent / "fixtures" / "sonic_context" / "fireside.json"
        doc = json.loads(sonic_path.read_text(encoding="utf-8"))
    elif stage_id in ("sound_design_palettes", "sound_design_plan"):
        doc = _sound_design_plan_doc(stage_id, fixtures)
    elif stage_id == "episode_structure_compose":
        from interview_mux.episode_structure import build_episode_structure, structure_enabled
        from interview_mux.write_staging import write_committed_json

        if structure_enabled():
            doc = build_episode_structure(ctx, refresh=False)
        else:
            doc = {
                "schema_version": 1,
                "policy_hash": "fixture",
                "axes": {},
                "segment_order": ["seg_001"],
                "slot_plan": [],
                "hook_reel": {"segment_id": "seg_001", "repeat_allowed": False},
                "omit_reasons": [],
                "rationale": ["fixture"],
                "integrity": {"ok": True, "flags": []},
                "occupancy": {"violations": []},
            }
        rel = "understanding/episode_structure.json"
        write_committed_json(ctx, rel, doc, stage_key=stage_id)
        return rel
    elif stage_id == "sound_design_vo_finalize":
        rel = "understanding/sound_design_plan.json"
        return rel if ctx.artifact_exists(rel) else None
    elif stage_id == "edl":
        from interview_mux.stages.assembly import build_flow1_edl

        if not ctx.artifact_exists("master/selection.json"):
            return None
        selection = ctx.read_json("master/selection.json")
        manifest = ctx.read_json("segments/manifest.json")
        by_id = {
            str(s.get("segment_id")): s
            for s in (manifest.get("segments") or [])
            if isinstance(s, dict) and s.get("segment_id")
        }
        gap_report = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else None
        )
        transitions = (
            ctx.read_json("master/transitions.json")
            if ctx.artifact_exists("master/transitions.json")
            else None
        )
        edl = build_flow1_edl(
            selection=selection,
            segments_by_id=by_id,
            gap_report=gap_report,
            transitions=transitions,
        )
        if edl.get("warnings", {}).get("missing_segment_lookups"):
            raise ValueError(
                "edl fixture: missing segment lookups "
                f"{edl['warnings']['missing_segment_lookups']}"
            )
        rel = "master/edl.json"
        write_committed_json(ctx, rel, edl, stage_key=stage_id)
        return rel
    elif stage_id == "transitions":
        doc = dict(fixtures.get("transitions") or {})
        for tr in doc.get("transitions") or []:
            if isinstance(tr, dict):
                tr["before_segment_id"] = "seg_001"
                tr["after_segment_id"] = "seg_001"
    elif stage_id in fixtures:
        doc = fixtures[stage_id]
    else:
        return None
    from interview_mux.artifact_writes import _prepare_for_disk_validation, _prepare_segment_artifact

    out = doc
    if stage_id == "sound_design_plan":
        from interview_mux.artifact_completeness import merge_artifact

        existing: dict[str, Any] | None = None
        if ctx.artifact_exists(rel):
            raw = ctx.read_json(rel)
            if isinstance(raw, dict):
                existing = raw
        out = merge_artifact(rel, existing, doc, stage_key=stage_id)
    out = _prepare_segment_artifact(ctx, rel, out, stage_key=stage_id)
    out = _prepare_for_disk_validation(out, rel_path=rel, stage_key=stage_id)
    errors = validate_artifact_write(rel, out)
    if errors:
        raise ValueError(f"{rel}: schema validation failed — {'; '.join(errors[:6])}")
    write_committed_json(ctx, rel, out, stage_key=stage_id)
    if stage_id == "optimal_questions":
        lines = out.get("interviewer_lines") or []
        rows: list[str] = []
        for line in lines:
            if isinstance(line, dict):
                lid = str(line.get("line_id") or "")
                text = str(line.get("text") or "")
                rows.append(f"{lid}: {text}".strip(": "))
        script_path = ctx.final_path("understanding", "interviewer_script.txt")
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text("\n".join(rows), encoding="utf-8")
    return rel


def validate_stage_committed(ctx: RunContext, stage_id: str) -> list[str]:
    """Return human-readable validation failures (empty = OK)."""
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_id) or BUILD_STAGE_ARTIFACT_PATHS.get(stage_id)
    if not rel or not ctx.artifact_exists(rel):
        return [f"{stage_id}: missing producer artifact {rel}"]
    doc = ctx.read_json(rel)
    failures: list[str] = []
    failures.extend(validate_artifact_write(rel, doc))
    incompleteness = stage_artifact_incompleteness(ctx, stage_id)
    if incompleteness:
        failures.append(f"{stage_id}: {incompleteness}")
    status = artifact_status(rel, ctx)
    if status != "complete":
        failures.append(f"{stage_id}: artifact status {status}")
    failures.extend(validate_cross_artifacts_for_stage(ctx, stage_id, staged=False))
    return failures


def validate_downstream_inputs(ctx: RunContext, next_stage_id: str) -> list[str]:
    """Check stage-input readiness; ignore flow-selection gates in fixture chain tests."""
    skip_gate_stages = frozenset({"analysis_profile", "g1_vo_pickup"})
    if next_stage_id in skip_gate_stages:
        return []
    issues = collect_stage_input_issues(ctx, next_stage_id)
    return [f"{next_stage_id}: {issue.message}" for issue in issues]


def ensure_reanchored_content_brief(ctx: RunContext) -> None:
    """Post-segment sync: topic segment_ids + topic_relationships for completeness."""
    sync_content_brief_topic_segment_ids(ctx)
    if not ctx.artifact_exists("understanding/content_brief.json"):
        return
    brief = ctx.read_json("understanding/content_brief.json")
    if not isinstance(brief, dict):
        return
    topics = brief.get("topics") or []
    for topic in topics:
        if isinstance(topic, dict) and not (topic.get("segment_ids") or []):
            topic["segment_ids"] = ["seg_001"]
    brief["topics"] = topics
    if not (brief.get("topic_relationships") or []):
        name_a = topics[0].get("name", "Topic A") if topics and isinstance(topics[0], dict) else "Topic A"
        brief["topic_relationships"] = [
            {"from_topic": name_a, "to_topic": name_a, "relation": "supports"}
        ]
    ctx.write_json("understanding/content_brief.json", brief, skip_handoff=True)
    ctx.mark_done("content_brief_reanchor", force=True)


def seed_vo_from_gap_report(ctx: RunContext) -> None:
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return
    from run_fixtures import write_fixture_vo_wav

    gap = ctx.read_json("understanding/gap_report.json")
    vo_dir = ctx.final_path("vo_pickup")
    vo_dir.mkdir(parents=True, exist_ok=True)
    for row in gap.get("gaps") or gap.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("delivery") or "").lower() == "record":
            lid = str(row.get("line_id") or "line_001")
            path = vo_dir / f"{lid}.wav"
            if not path.is_file():
                write_fixture_vo_wav(path)


def prepare_flow_chain_gates(ctx: RunContext) -> None:
    """Minimal run_meta + gate markers so flow fixture stages can be input-checked."""
    from interview_mux.artifact_writes import write_validated_artifact

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        meta = {}
    meta.setdefault("handoff_ack", {})
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    ctx.mark_done("analysis_profile", force=True)
    ctx.mark_done("g1_vo_pickup", force=True)
    ctx.mark_done("vo_ingest", force=True)
    if not ctx.artifact_exists("understanding/delivery_brief.json"):
        write_validated_artifact(
            ctx,
            "understanding/delivery_brief.json",
            {
                "version": 1,
                "source_duration_ms": 60_000,
                "target_duration_sec": {"min": 8, "ideal": 12, "max": 60},
                "question_budget": {"min": 0, "ideal": 1, "max": 2},
                "chapter_budget": {"min": 1, "ideal": 2, "max": 4},
                "selection_mode": "coverage_first",
                "sfx_density": {"max_beds": 1, "max_punctuators": 1, "max_foley": 0},
                "ranking_weights": {},
                "rationale": ["fixture"],
                "operator_overrides": {},
                "generated": {"at": "1970-01-01T00:00:00+00:00", "by": "test_fixture"},
            },
            merge_from_disk=False,
            stage_key="delivery_brief_build",
        )
    state = ctx.read_json("understanding/analysis_state.json")
    if isinstance(state, dict):
        state.setdefault("meta", {})["operator_verified"] = True
        ctx.write_json("understanding/analysis_state.json", state, skip_handoff=True)
    ctx.write_json("analysis_complete.json", {"analysis_ready": True, "blockers": []}, skip_handoff=True)
    seed_vo_from_gap_report(ctx)


def validate_content_brief_segment_id_hygiene(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("understanding/content_brief.json"):
        return ["content_brief.json missing"]
    brief = ctx.read_json("understanding/content_brief.json")
    manifest_ids: set[str] = set()
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        manifest_ids = {
            str(s.get("segment_id"))
            for s in (manifest.get("segments") or [])
            if isinstance(s, dict) and s.get("segment_id")
        }
    failures: list[str] = []
    for i, topic in enumerate(brief.get("topics") or []):
        if not isinstance(topic, dict):
            continue
        for sid in topic.get("segment_ids") or []:
            s = str(sid)
            if not is_manifest_segment_id(s):
                failures.append(f"topics[{i}] invalid segment_id format: {s}")
            elif manifest_ids and s not in manifest_ids:
                failures.append(f"topics[{i}] segment_id {s} not in manifest")
    return failures


def simulate_segment_classification_write_approval(
    ctx: RunContext,
    fixtures: dict[str, Any],
    *,
    placeholder_topic_ids: bool = True,
) -> list[str]:
    """Write-approval ITR regression removed in v2 (auto-commit)."""
    _ = (ctx, fixtures, placeholder_topic_ids)
    return []


def run_progression_chain_sanity(
    ctx: RunContext,
    *,
    chain: list[str] | None = None,
    include_write_approval_regression: bool = True,
) -> dict[str, Any]:
    """Walk the chain stage-by-stage; return structured report."""
    fixtures = load_stage_fixtures()
    seed_prefix_through_boundary(ctx, fixtures)
    chain = list(chain or FULL_PROGRESSION_CHAIN)
    report: dict[str, Any] = {
        "chain": chain,
        "stages": {},
        "failures": [],
        "ok": True,
    }

    needs_flow_gates = bool(
        set(chain)
        & (set(PROGRESSION_FLOW_STAGES) | set(PROGRESSION_BUILD_STAGES) | {"episode_structure_compose"})
    )
    if needs_flow_gates:
        prepare_flow_chain_gates(ctx)

    if include_write_approval_regression and PROGRESSION_START_STAGE in chain:
        wa_failures = simulate_segment_classification_write_approval(ctx, fixtures)
        report["write_approval_regression"] = wa_failures
        if wa_failures:
            report["failures"].extend(wa_failures)
            report["ok"] = False
        manifest = build_manifest_from_fixtures(fixtures)
        ctx.write_json("segments/manifest.json", manifest, skip_handoff=True)
        sync_content_brief_topic_segment_ids(ctx)
        ensure_reanchored_content_brief(ctx)
        fixture_reanchor = fixtures.get("content_brief_reanchor")
        if isinstance(fixture_reanchor, dict):
            ctx.write_json(
                "understanding/content_brief.json",
                fixture_reanchor,
                skip_handoff=True,
            )
            sync_content_brief_topic_segment_ids(ctx)
        ctx.mark_done("segment_classification", force=True)
        from interview_mux.write_staging import discard_stage_writes

        discard_stage_writes(ctx, "segment_classification")

    for stage_id in chain:
        stage_report: dict[str, Any] = {"stage_id": stage_id}
        if stage_id == PROGRESSION_START_STAGE and include_write_approval_regression:
            stage_report["skipped_commit"] = "covered by write-approval regression"
            report["stages"][stage_id] = stage_report
            continue

        rel = write_stage_producer_artifact(ctx, stage_id, fixtures)
        if not rel:
            stage_report["skipped"] = "no fixture producer artifact"
            report["stages"][stage_id] = stage_report
            continue

        failures = validate_stage_committed(ctx, stage_id)
        stage_report["artifact_path"] = rel
        stage_report["failures"] = failures

        if stage_id in ("gap_framing_compose", "optimal_questions"):
            seed_vo_from_gap_report(ctx)

        idx = chain.index(stage_id)
        if idx + 1 < len(chain):
            next_stage = chain[idx + 1]
            downstream = validate_downstream_inputs(ctx, next_stage)
            stage_report["downstream_input_failures"] = downstream
            failures = [*failures, *downstream]

        if stage_id in ("segment_classification", "content_brief_reanchor", "content_context"):
            failures.extend(validate_content_brief_segment_id_hygiene(ctx))
            stage_report["content_brief_segment_failures"] = validate_content_brief_segment_id_hygiene(ctx)

        if stage_id == "segment_classification":
            sync_content_brief_topic_segment_ids(ctx)

        ctx.mark_done(stage_id, force=True)
        stage_report["ok"] = not failures
        report["stages"][stage_id] = stage_report
        if failures:
            report["ok"] = False
            report["failures"].extend(f"{stage_id}: {f}" for f in failures)

    return report
