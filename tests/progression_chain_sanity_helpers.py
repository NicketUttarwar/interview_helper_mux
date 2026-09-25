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
from run_fixtures import mark_done_raw

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "prompts" / "stage_artifacts.json"
PROGRESSION_WALK_FIXTURES = Path(__file__).parent / "fixtures" / "progression_walk"
PROGRESSION_WALK_HOST_SPEAKER_ID = "spk_001"

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
    "vo_line_adjudicate",
    "vo_synthesize",
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


def _seed_gap_vo_wavs_for_progression(
    ctx: RunContext, gap_report: dict[str, Any] | None
) -> None:
    """Minimal WAV + synthesis audit so EDL vo_pickup clips pass schema validation."""
    import wave

    from interview_mux.vo_synthesis_audit import record_synthesis

    if not isinstance(gap_report, dict):
        return
    pickup = ctx.final_path("vo_pickup")
    pickup.mkdir(parents=True, exist_ok=True)
    for line in gap_report.get("interviewer_lines") or []:
        if not isinstance(line, dict) or line.get("skipped_optional"):
            continue
        lid = str(line.get("line_id") or "").strip()
        if not lid:
            continue
        wav = pickup / f"{lid}.wav"
        if wav.is_file() and wav.stat().st_size > 1000:
            continue
        with wave.open(str(wav), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(48_000)
            handle.writeframes(b"\x00\x00" * 48_000)
        try:
            record_synthesis(ctx, line, backend="record", out_wav=wav)
        except Exception:
            pass


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
        mark_done_raw,
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
        mark_done_raw(ctx, sid)
    mark_done_raw(ctx, "transcript_review")
    mark_done_raw(ctx, "disfluency_review")


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


def _stamp_selection_sanitary_for_progression(ctx: RunContext) -> None:
    """Progression fixtures: bump order lock + sanitize stamp so consumers don't block."""
    if not ctx.artifact_exists("master/selection.json"):
        return
    try:
        from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta
        from interview_mux.file_store import write_json as fs_write_json
        from interview_mux.order_hash import bump_order_lock

        doc = ctx.read_json("master/selection.json")
        if not isinstance(doc, dict):
            return
        try:
            doc = bump_order_lock(doc, source="progression_chain_sanity")
        except Exception:
            pass
        doc = stamp_sanitize_meta(
            doc,
            ok=True,
            source="progression_chain_sanity",
            actions_n=0,
        )
        fs_write_json(ctx.path("master/selection.json"), doc)
        mark_done_raw(ctx, "selection_order_sanitize")
    except Exception:
        pass


def _ensure_layup_for_progression(
    ctx: RunContext, fixtures: dict[str, Any] | None = None
) -> None:
    """SDP consumers require a sanitary layup plan; seed fixture + hash stamp."""
    rel = "understanding/nugget_layup_plan.json"
    from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta
    from interview_mux.file_store import write_json as fs_write_json

    content_keys = ["ordered_segment_ids", "layups", "status"]
    ordered: list[str] = ["seg_001"]
    try:
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict) and isinstance(sel.get("ordered_segment_ids"), list):
                ordered = [str(x) for x in sel["ordered_segment_ids"] if x] or ordered
    except Exception:
        pass

    doc: dict[str, Any] | None = None
    if ctx.artifact_exists(rel):
        try:
            existing = ctx.read_json(rel)
            if isinstance(existing, dict):
                doc = existing
        except Exception:
            doc = None
    if doc is None and isinstance(fixtures, dict):
        fixture_doc = fixtures.get("nugget_layup_compose")
        if isinstance(fixture_doc, dict):
            doc = dict(fixture_doc)
            doc.setdefault("version", 1)
    if doc is None:
        doc = {
            "version": 1,
            "ordered_segment_ids": ordered,
            "layups": [
                {
                    "target_segment_id": sid,
                    "nugget_ids": [],
                    "selected_nugget_ids": [],
                    "skip": True,
                    "skip_reason_code": "progression_fixture",
                }
                for sid in ordered
            ],
            "discharged_talking_point_ids": [],
            "open_talking_point_ids": [],
        }
    # Align order to current selection so stamp stays valid across ranking.
    if ordered:
        doc["ordered_segment_ids"] = list(ordered)
    doc = stamp_sanitize_meta(
        doc,
        ok=True,
        source="progression_chain_sanity",
        actions_n=0,
        content_keys=content_keys,
    )
    meta = dict(doc.get("_meta") or {})
    meta.pop("needs_recompose", None)
    doc["_meta"] = meta
    fs_write_json(ctx.path(rel), doc)
    mark_done_raw(ctx, "nugget_layup_compose")


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
        partial = _sound_design_plan_patch(stage_id, fixtures)
        palettes_doc = fixtures.get("sound_design_palettes") or {}
        return sound_design_plan_with(
            palettes=palettes_doc.get("palettes") or [],
            coherence=palettes_doc.get("coherence")
            or {
                "sonic_identity": "Walk fixture warm documentary bed under spoken word.",
                "primary_mood": "reflective",
                "density": "sparse",
            },
            assets=partial.get("assets") or [],
            flow_plans=partial.get("flow_plans") or {},
            generated=partial.get("generated") or {},
        )
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
        _stamp_selection_sanitary_for_progression(ctx)
        _ensure_layup_for_progression(ctx, fixtures)
        doc = _sound_design_plan_doc(stage_id, fixtures)
    elif stage_id == "full_master_ranking":
        doc = fixtures.get(stage_id) or {"ordered_segment_ids": ["seg_001"]}
        # Ranking is the selection producer in this fixture walk — stamp sanitary
        # immediately so transitions / SDP preflight don't refuse.
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
        from run_fixtures import write_fixture_json

        rel = "mastering/sound_design_vo_finalize.json"
        write_fixture_json(
            ctx,
            rel,
            {
                "schema_version": 1,
                "status": "complete",
                "skipped": True,
                "refused": False,
                "errors": [],
                "reason": "progression_fixture",
                "adjusted": 0,
                "skipped_cues": 0,
                "missing": [],
            },
        )
        mark_done_raw(ctx, "sound_design_vo_finalize")
        return rel
    elif stage_id in ("vo_line_adjudicate", "vo_synthesize", "edl_narrative_audit"):
        rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_id)
        if not rel:
            return None
        doc = fixtures.get(stage_id)
        if not isinstance(doc, dict) and stage_id == "vo_synthesize":
            from run_fixtures import minimal_vo_synthesize

            doc = minimal_vo_synthesize()
        if isinstance(doc, dict):
            write_committed_json(ctx, rel, doc, stage_key=stage_id)
            if stage_id == "vo_synthesize":
                mark_done_raw(ctx, "vo_synthesize")
            return rel
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
        _omit_opening_orientation_for_progression(ctx)
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
        _seed_gap_vo_wavs_for_progression(ctx, gap_report)
        from interview_mux.stages.assembly import resolve_vo_pickup_path, vo_pickup_relpath

        edl = build_flow1_edl(
            selection=selection,
            segments_by_id=by_id,
            gap_report=gap_report,
            transitions=transitions,
            resolve_vo_path=lambda line: resolve_vo_pickup_path(ctx, line),
            vo_relpath=lambda p: vo_pickup_relpath(ctx, p),
            ctx=ctx,
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
        # Single-segment walk: empty junctions are complete (selection_count < 2).
        doc = {
            "transitions": [],
            "empty_ok": True,
            "selection_count": 1,
            "_meta": {"empty_allowlist": "selection_lt_2"},
        }
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
        meta = dict(out.get("_meta") or {})
        meta["producer_stage"] = "sound_design_plan"
        out["_meta"] = meta
    out = _prepare_segment_artifact(ctx, rel, out, stage_key=stage_id)
    out = _prepare_for_disk_validation(out, rel_path=rel, stage_key=stage_id)
    errors = validate_artifact_write(rel, out)
    if errors:
        raise ValueError(f"{rel}: schema validation failed — {'; '.join(errors[:6])}")
    if stage_id == "sound_design_plan":
        try:
            from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta

            out = stamp_sanitize_meta(
                out,
                ok=True,
                source="progression_chain_sanity",
                actions_n=0,
            )
        except Exception:
            meta = dict(out.get("_meta") or {})
            meta["sanitize"] = {"ok": True, "source": "progression_chain_sanity"}
            out["_meta"] = meta
    write_committed_json(ctx, rel, out, stage_key=stage_id)
    if stage_id == "full_master_ranking":
        _stamp_selection_sanitary_for_progression(ctx)
        _ensure_layup_for_progression(ctx, fixtures)
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
    mark_done_raw(ctx, "content_brief_reanchor")


def _omit_opening_orientation_for_progression(ctx: RunContext) -> None:
    """Single-segment walk: waive opening orientation so EDL is not pinned to VO."""
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return
    from run_fixtures import write_fixture_json

    gap = ctx.read_json("understanding/gap_report.json")
    if not isinstance(gap, dict):
        return
    gap["opening_orientation"] = {
        "omitted": True,
        "required": False,
        "reason": "progression_fixture",
    }
    write_fixture_json(ctx, "understanding/gap_report.json", gap)


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


def seed_progression_walk_gates(ctx: RunContext) -> None:
    """Demo operator gate state so the fixture walk can enter delivery without a real GUI.

    Uses a committed walk-only host voice clip (from a historic execution) and
    stamps the same approvals the product expects before gap/VO delivery stages.
    """
    import shutil

    from run_fixtures import write_fixture_vo_wav

    host_id = PROGRESSION_WALK_HOST_SPEAKER_ID
    approved_at = "1970-01-01T00:00:00+00:00"

    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology": "one_on_one_asymmetric",
            "pickup_eligible_speaker_id": host_id,
            "speaker_stats": [
                {"speaker_id": host_id, "talk_ratio": 0.25},
                {"speaker_id": "spk_guest", "talk_ratio": 0.75},
            ],
        },
        skip_handoff=True,
    )
    adapt = (
        ctx.read_json("understanding/flow_adaptation.json")
        if ctx.artifact_exists("understanding/flow_adaptation.json")
        else {}
    )
    if not isinstance(adapt, dict):
        adapt = {}
    overrides = dict(adapt.get("operator_overrides") or {})
    overrides.update(
        {
            "pickup_speaker_confirmed": True,
            "gap_framing_enabled": True,
            "pickup_eligible_speaker_id": host_id,
        }
    )
    adapt["operator_overrides"] = overrides
    adapt["pickup_eligible_speaker_id"] = host_id
    ctx.write_json("understanding/flow_adaptation.json", adapt, skip_handoff=True)

    clip_dir = ctx.final_path("understanding", "voice_reference", "clips", host_id)
    clip_dir.mkdir(parents=True, exist_ok=True)
    clip_path = clip_dir / "candidate_00.wav"
    demo = PROGRESSION_WALK_FIXTURES / "demo_host_voice.wav"
    if demo.is_file():
        shutil.copy2(demo, clip_path)
    else:
        write_fixture_vo_wav(clip_path)

    ctx.write_json(
        f"understanding/voice_reference/{host_id}.json",
        {
            "speaker_id": host_id,
            "approved": True,
            "approved_at": approved_at,
            "selected_clip": "candidate_00.wav",
            "clip_relpath": f"understanding/voice_reference/clips/{host_id}/candidate_00.wav",
            "fixture_source": "progression_walk/demo_host_voice.wav",
        },
        skip_handoff=True,
    )

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        meta = {}
    meta.update(
        {
            "gap_framing_enabled": True,
            "gap_vo_delivery": "chatterbox",
            "gap_fill_mode": "active",
            "voice_reference_approved_at": approved_at,
            "voice_clone_consent": {
                "speaker_id": host_id,
                "granted": True,
                "granted_by": "pytest",
                "granted_at": approved_at,
                "scopes": ["cold_open", "bridges", "outro"],
                "reference_path": f"understanding/voice_reference/{host_id}.json",
                "reference_approved": True,
                "disclosure": "none",
                "revoked_at": None,
            },
        }
    )
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    mark_done_raw(ctx, "source_topology_build")


def plant_progression_research_ready(ctx: RunContext) -> None:
    """Fat W1–3 dossier so Shape/gap consumers are not pinned to a thin rollup."""
    from interview_mux.mastering_research import (
        DOSSIER_REL,
        ROLLUP_REL,
        SHAPE_CORE_WAVES,
        WAVE_FIELDS,
    )
    from run_fixtures import write_fixture_json

    fields: dict[str, Any] = {}
    for wave, fids in WAVE_FIELDS.items():
        status = "complete" if wave in SHAPE_CORE_WAVES else "skipped_or_thin"
        for fid in fids:
            fields[fid] = {
                "version": 1,
                "field_id": fid,
                "wave": wave,
                "status": status,
                "evidence_refs": [],
            }
    complete = [fid for fid, row in fields.items() if row["status"] == "complete"]
    thin = [fid for fid, row in fields.items() if row["status"] != "complete"]
    doc = {
        "version": 1,
        "fields": fields,
        "complete_fields": complete,
        "thin_fields": thin,
        "field_reports": [],
        "salience_map": {},
        "generated_at": "1970-01-01T00:00:00+00:00",
    }
    write_fixture_json(ctx, DOSSIER_REL, doc)
    write_fixture_json(ctx, ROLLUP_REL, doc)
    mark_done_raw(ctx, "mastering_research_routing")
    mark_done_raw(ctx, "mastering_research_waves")
    mark_done_raw(ctx, "mastering_research_rollup")


def prepare_flow_chain_gates(ctx: RunContext) -> None:
    """Minimal run_meta + gate markers so flow fixture stages can be input-checked."""
    from interview_mux.artifact_writes import write_validated_artifact

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        meta = {}
    meta.setdefault("handoff_ack", {})
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    mark_done_raw(ctx, "analysis_profile")
    mark_done_raw(ctx, "g1_vo_pickup")
    mark_done_raw(ctx, "vo_ingest")
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
    seed_progression_walk_gates(ctx)
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
        mark_done_raw(ctx, "segment_classification")
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
            _omit_opening_orientation_for_progression(ctx)

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

        mark_done_raw(ctx, stage_id)
        stage_report["ok"] = not failures
        report["stages"][stage_id] = stage_report
        if failures:
            report["ok"] = False
            report["failures"].extend(f"{stage_id}: {f}" for f in failures)

    return report
