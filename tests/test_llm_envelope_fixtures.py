"""Golden bad envelopes — deterministic_lint regression without API calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.deterministic_lint import deterministic_lint
from run_fixtures import (
    isolated_run_ctx,
    minimal_content_brief,
    minimal_flow2_selection,
    minimal_gap_evaluations,
    minimal_gap_report,
    minimal_manifest,
    patch_merged_config,
    seed_flow1_sound_spend_ready,
    sound_design_plan_with,
)

FIXTURES = Path(__file__).parent / "fixtures" / "llm_envelopes"


def _fixture_paths() -> list[Path]:
    return sorted(
        p
        for p in FIXTURES.glob("*.json")
        if p.name != "README.md" and p.name not in FULL_STACK_FIXTURES
    )


def _seed_context(ctx, stage_key: str) -> None:
    if stage_key in (
        "segment_classification",
        "boundary_detection",
        "content_brief_reanchor",
        "missing_framing",
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "optimal_questions",
        "edl_narrative_audit",
        "sound_design_palettes",
    ):
        ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), stage_key="segment_classification")
    if stage_key == "content_brief_reanchor":
        ctx.write_json("understanding/content_brief.json", minimal_content_brief(), skip_handoff=True)
    if stage_key in ("topic_coverage_audit", "narrative_arc_plan"):
        ctx.write_json("understanding/content_brief.json", minimal_content_brief(), skip_handoff=True)
    if stage_key == "full_master_ranking":
        ctx.write_json(
            "flow_1_master/selection.json",
            {"ordered_segment_ids": ["seg_001"]},
            skip_handoff=True,
        )
    if stage_key == "optimal_questions":
        ctx.write_json(
            "understanding/gap_evaluations.json",
            minimal_gap_evaluations(
                {"segment_id": "seg_001", "severity": "high", "self_explanatory": False, "gap_type": "missing_context"}
            ),
            skip_handoff=True,
        )
    if stage_key == "edl_narrative_audit":
        ctx.write_json(
            "flow_1_master/selection.json",
            {"ordered_segment_ids": ["seg_001"]},
            skip_handoff=True,
        )
    if stage_key in ("sound_design_palettes", "sound_design_plan_flow1", "sound_design_plan_flow2"):
        ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), stage_key="segment_classification")
    if stage_key == "sound_design_plan_flow1":
        ctx.write_json(
            "flow_1_master/selection.json",
            {"ordered_segment_ids": ["seg_001"]},
            skip_handoff=True,
        )
    if stage_key == "sound_design_plan_flow2":
        ctx.write_json(
            "flow_2_highlights/selection.json",
            minimal_flow2_selection(),
            skip_handoff=True,
        )
    if stage_key in ("podcast_sfx_brief",):
        seed_flow1_sound_spend_ready(ctx)
    if stage_key == "transitions":
        from run_fixtures import minimal_gap_line

        ctx.write_json(
            "understanding/gap_report.json",
            minimal_gap_report(minimal_gap_line(text="this is a long pickup line for overlap test")),
            skip_handoff=True,
        )


FULL_STACK_FIXTURES = {
    "content_context_low_confidence.json",
    "missing_framing_low_coverage.json",
    "boundary_detection_truncation_no_decompose.json",
}


@pytest.mark.parametrize("fixture_path", _fixture_paths(), ids=lambda p: p.name)
def test_golden_envelope_stage_lint(tmp_path, monkeypatch, fixture_path: Path) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": False}}})
    monkeypatch.setattr(
        "interview_mux.deterministic_lint._lint_generic",
        lambda *_a, **_k: [],
    )
    ctx = isolated_run_ctx(tmp_path, "env_lint")
    doc = json.loads(fixture_path.read_text(encoding="utf-8"))
    stage_key = str(doc["stage_key"])
    expected = str(doc.get("expected_substring", "")).lower()
    envelope = {"artifacts": doc.get("artifacts") or doc}
    if "status" not in envelope:
        envelope = {"status": "complete", "artifacts": doc.get("artifacts") or {}}
    _seed_context(ctx, stage_key)
    errors = deterministic_lint(stage_key, envelope, ctx)
    assert errors, f"expected lint failure for {fixture_path.name}"
    if expected:
        joined = " ".join(errors).lower()
        assert expected in joined, f"expected {expected!r} in {errors}"


@pytest.mark.parametrize(
    "fixture_name",
    sorted(FULL_STACK_FIXTURES),
    ids=lambda n: n,
)
def test_golden_envelope_full_stack_lint(tmp_path, monkeypatch, fixture_name: str) -> None:
    """Generic lint integration without mocking _lint_generic."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": False}}})
    fixture_path = FIXTURES / fixture_name
    ctx = isolated_run_ctx(tmp_path, "env_full")
    doc = json.loads(fixture_path.read_text(encoding="utf-8"))
    stage_key = str(doc["stage_key"])
    expected = str(doc.get("expected_substring", "")).lower()
    envelope = {
        "status": doc.get("status", "complete"),
        "confidence": doc.get("confidence", 0.9),
        "artifacts": doc.get("artifacts") or {},
    }
    _seed_context(ctx, stage_key)
    if fixture_name == "missing_framing_low_coverage.json":
        segs = [minimal_manifest(f"seg_{i:03d}")["segments"][0] for i in range(1, 11)]
        ctx.write_json("segments/manifest.json", {"segments": segs}, stage_key="segment_classification")
    if stage_key == "boundary_detection":
        segs = [minimal_manifest(f"seg_{i:03d}")["segments"][0] for i in range(1, 6)]
        ctx.write_json("segments/manifest.json", {"segments": segs}, stage_key="segment_classification")
    if doc.get("truncation_flags"):
        errors = deterministic_lint(
            stage_key,
            envelope,
            ctx,
            truncation_flags=doc["truncation_flags"],
            routed_via_collate=False,
        )
    else:
        errors = deterministic_lint(stage_key, envelope, ctx)
    assert errors, f"expected lint failure for {fixture_name}"
    if expected:
        joined = " ".join(errors).lower()
        assert expected in joined, f"expected {expected!r} in {errors}"
