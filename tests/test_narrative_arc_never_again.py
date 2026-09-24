"""Guardrails for narrative_arc_plan never-again redesign."""

from __future__ import annotations

from interview_mux.artifact_ownership import write_permitted
from interview_mux.heal_success import SOFT_PRE_FLUSH_ALLOW, may_soft_pre_flush_pass
from interview_mux.llm_simple import _FAIL_OPEN_PARTIAL_STAGES
from interview_mux.talking_points_authority import synthesize_narrative_from_coverage
from interview_mux.write_staging import (
    enter_stage_staging,
    exit_stage_staging,
    write_pending_content,
)
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment


def test_narrative_arc_never_soft_pre_flush_allowlisted():
    assert "narrative_arc_plan" not in SOFT_PRE_FLUSH_ALLOW
    assert may_soft_pre_flush_pass("narrative_arc_plan", soft_reason="empty") is False
    assert "narrative_arc_plan" not in _FAIL_OPEN_PARTIAL_STAGES


def test_synthesize_narrative_from_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "nap_synth")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001", start_ms=0, end_ms=1000),
            minimal_manifest_segment("seg_002", start_ms=1000, end_ms=2000),
        ),
        skip_handoff=True,
    )
    # Brief optional for synthesize; avoid schema friction in unit test
    plan = synthesize_narrative_from_coverage(ctx)
    assert plan is not None
    assert len(plan.get("chapters") or []) >= 1
    assert plan["chapters"][0]["suggested_open_segment_id"] == "seg_001"


def test_mark_done_auto_flush_then_seal_pending(tmp_path, monkeypatch):
    """v2 auto-commit: in-body mark_done flushes pending then seals (exec_13177)."""
    from interview_mux.write_staging import has_pending_writes

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled", lambda: False
    )
    monkeypatch.setattr("interview_mux.v2.config.v2_auto_commit", lambda: True)
    ctx = isolated_run_ctx(tmp_path, "nap_pending_mark")
    enter_stage_staging("narrative_arc_plan")
    try:
        write_pending_content(
            ctx,
            "narrative_arc_plan",
            "master/narrative_plan.json",
            data={
                "arc_summary": "Arc",
                "chapters": [
                    {
                        "chapter_id": "ch_01",
                        "title": "Open",
                        "suggested_open_segment_id": "seg_001",
                        "segment_ids": ["seg_001"],
                    }
                ],
                "ordering_constraints": [],
            },
        )
        assert has_pending_writes(ctx, "narrative_arc_plan")
        ctx.mark_done("narrative_arc_plan")
        assert ctx.is_done("narrative_arc_plan")
        assert not has_pending_writes(ctx, "narrative_arc_plan")
        assert ctx.artifact_exists("master/narrative_plan.json")
    finally:
        exit_stage_staging()


def test_mark_done_refuses_unflushed_under_write_approval(tmp_path, monkeypatch):
    """Write-approval mode still defers stamp while pending (no silent seal)."""
    from interview_mux.write_staging import has_pending_writes

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled", lambda: True
    )
    ctx = isolated_run_ctx(tmp_path, "nap_pending_wa")
    enter_stage_staging("narrative_arc_plan")
    try:
        write_pending_content(
            ctx,
            "narrative_arc_plan",
            "master/narrative_plan.json",
            data={
                "arc_summary": "Arc",
                "chapters": [
                    {
                        "chapter_id": "ch_01",
                        "title": "Open",
                        "suggested_open_segment_id": "seg_001",
                        "segment_ids": ["seg_001"],
                    }
                ],
                "ordering_constraints": [],
            },
        )
        ctx.mark_done("narrative_arc_plan")
        assert not ctx.is_done("narrative_arc_plan")
        assert has_pending_writes(ctx, "narrative_arc_plan")
    finally:
        exit_stage_staging()


def test_hitch_spoof_narrative_arc_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "nap_spoof")
    enter_stage_staging("chapter_close_hitch")
    try:
        ok, reason = write_permitted(
            ctx,
            "master/narrative_plan.json",
            "narrative_arc_plan",
            mutation_class=None,
        )
        assert ok is False
        assert "spoof" in reason or "hitch" in reason
        ok2, reason2 = write_permitted(
            ctx,
            "master/narrative_plan.json",
            "chapter_close_hitch",
            mutation_class="hitch_chapter_authority",
        )
        assert ok2 is True, reason2
    finally:
        exit_stage_staging()


def test_narrative_plan_schema_rejects_empty_chapters():
    from interview_mux.prompt_validation import validate_artifact_write

    errs = validate_artifact_write(
        "master/narrative_plan.json",
        {"arc_summary": "x", "chapters": [], "ordering_constraints": []},
    )
    assert errs, "empty chapters must fail schema"


def test_staged_overlay_pending_plan_not_missing(tmp_path, monkeypatch):
    from interview_mux.artifact_cross_validate import validate_cross_artifacts_for_stage

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "nap_overlay")
    plan = {
        "arc_summary": "Arc",
        "chapters": [
            {
                "chapter_id": "ch_01",
                "title": "Open",
                "suggested_open_segment_id": "seg_001",
                "segment_ids": ["seg_001"],
            }
        ],
        "ordering_constraints": [],
    }
    enter_stage_staging("narrative_arc_plan")
    try:
        write_pending_content(
            ctx, "narrative_arc_plan", "master/narrative_plan.json", data=plan
        )
        errs = validate_cross_artifacts_for_stage(
            ctx, "narrative_arc_plan", staged=True
        )
        missing = [e for e in errs if "narrative_plan.json missing" in str(e)]
        assert not missing, errs
    finally:
        exit_stage_staging()


def test_narrative_arc_r5_synthesize_after_stage_error(tmp_path, monkeypatch):
    """Honest LLM StageError still lands a committed plan via R5 synthesize."""
    from interview_mux.stages.analysis_extended import run_narrative_arc

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "nap_r5")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001", start_ms=0, end_ms=1000),
            minimal_manifest_segment("seg_002", start_ms=1000, end_ms=2000),
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Test thesis for synthesize",
            "topics": [{"name": "t1", "summary": "topic one"}],
        },
        skip_handoff=True,
    )
    # Manifest alone is enough substrate for R5; skip schema-heavy coverage_audit.

    def _boom(*_a, **_k):
        from interview_mux.llm_simple import StageError

        raise StageError("narrative_arc_plan", "forced LLM fail")

    monkeypatch.setattr(
        "interview_mux.stages.analysis_extended.run_flow_llm_stage",
        _boom,
    )
    monkeypatch.setattr(
        "interview_mux.talking_points_authority.try_deterministic_narrative",
        lambda _c: None,
    )
    enter_stage_staging("narrative_arc_plan")
    try:
        run_narrative_arc(ctx)
        assert ctx.artifact_exists("master/narrative_plan.json")
        plan = ctx.read_json("master/narrative_plan.json")
        assert len(plan.get("chapters") or []) >= 1
        assert (plan.get("_meta") or {}).get("source")
    finally:
        exit_stage_staging()


def test_hosted_floor_advisory_before_layup_front(tmp_path, monkeypatch):
    from interview_mux.vo_contract import _record_hosted_floor_unmet

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "nap_floor")
    # NAP incomplete → layup is not seed-front
    _record_hosted_floor_unmet(ctx, need=3, active=0, cta_only=True)
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    assert not meta.get("needs_operator"), meta
    assert meta.get("hosted_vo_floor_unmet") is True


def test_repair_narrative_clamps_chapter_budget(tmp_path, monkeypatch):
    from interview_mux.artifact_repairs import repair_narrative_plan

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "nap_clamp")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            *[
                minimal_manifest_segment(f"seg_{i:03d}", start_ms=i * 1000, end_ms=(i + 1) * 1000)
                for i in range(1, 12)
            ]
        ),
        skip_handoff=True,
    )
    # Default max is 8 when delivery_brief is absent.
    doc = {
        "arc_summary": "Arc",
        "chapters": [
            {
                "chapter_id": f"ch_{i:02d}",
                "title": f"C{i}",
                "suggested_open_segment_id": f"seg_{i:03d}",
                "segment_ids": [f"seg_{i:03d}"],
            }
            for i in range(1, 11)
        ],
        "ordering_constraints": [],
    }
    repaired, notes = repair_narrative_plan(ctx, doc)
    assert len(repaired.get("chapters") or []) <= 8
    assert any(n.get("action") == "merge_chapters_to_budget" for n in notes)
