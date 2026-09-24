"""ensure_gap_fill_skipped writes valid artifacts and marks stages done."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_completeness import artifact_status, analysis_profile_ready_for_review
from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
from interview_mux.stages.gaps import ensure_gap_fill_skipped
from run_fixtures import isolated_run_ctx, minimal_manifest, patch_merged_config


def test_ensure_gap_fill_skipped_writes_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "gap_skip")
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest("seg_001", "seg_002"),
        skip_handoff=True,
    )
    ensure_gap_fill_skipped(ctx, reason="test skip", signals={"skip_signal": "test"})

    assert gap_fill_was_skipped(ctx)
    assert ctx.is_done("missing_framing")
    assert ctx.is_done("optimal_questions")
    assert artifact_status("understanding/gap_evaluations.json", ctx) == "complete"
    assert artifact_status("understanding/gap_report.json", ctx) == "complete"
    report = ctx.read_json("understanding/gap_report.json")
    assert report.get("interviewer_lines") == []
    assert (report.get("_meta") or {}).get("producer_stage") == "missing_framing"


def test_skip_unlocks_profile_when_analysis_state_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from run_fixtures import seed_analysis_ready_artifacts

    ctx = isolated_run_ctx(tmp_path, "gap_skip_profile")
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    seed_analysis_ready_artifacts(ctx, verified=False)
    ensure_gap_fill_skipped(ctx, reason="topology skip", signals={})
    assert ctx.is_done("optimal_questions")
    assert analysis_profile_ready_for_review(ctx)


def test_skip_hydrates_partial_analysis_state_for_profile_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.analysis_memory import default_analysis_state, save_analysis_state, update_completion_from_analysis
    from interview_mux.artifact_writes import write_validated_artifact
    from run_fixtures import minimal_content_brief, minimal_manifest, minimal_speakers

    ctx = isolated_run_ctx(tmp_path, "gap_skip_hydrate")
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    write_validated_artifact(
        ctx,
        "understanding/speakers.json",
        {
            **minimal_speakers(),
            "conversation_profile": {
                "format_class_candidate": "one_on_one",
                "tone_class_candidate": "journalistic",
            },
        },
        merge_from_disk=False,
        stage_key="speaker_roles",
    )
    write_validated_artifact(
        ctx,
        "understanding/content_brief.json",
        minimal_content_brief(),
        merge_from_disk=False,
        stage_key="content_brief_reanchor",
    )
    write_validated_artifact(
        ctx,
        "segments/manifest.json",
        minimal_manifest("seg_001", "seg_002"),
        merge_from_disk=False,
        stage_key="segment_classification",
    )
    brief = {
        "version": 1,
        "source_duration_ms": 60_000,
        "target_duration_sec": {"min": 30, "ideal": 45, "max": 60},
        "question_budget": {"min": 0, "ideal": 0, "max": 0},
        "chapter_budget": {"min": 1, "ideal": 2, "max": 4},
        "selection_mode": "coverage_first",
        "sfx_density": {},
        "ranking_weights": {},
        "rationale": ["fixture"],
        "operator_overrides": {},
        "generated": {"at": "1970-01-01T00:00:00+00:00", "by": "test_fixture"},
    }
    write_validated_artifact(
        ctx,
        "understanding/delivery_brief.json",
        brief,
        merge_from_disk=False,
        stage_key="delivery_brief_build",
    )
    state = default_analysis_state(ctx.run_id)
    state["themes"] = [{"id": "t1", "label": "Theme", "summary": "Summary text"}]
    save_analysis_state(ctx, state, stage="content_context")
    ensure_gap_fill_skipped(ctx, reason="operator skip", signals={})
    update_completion_from_analysis(ctx)
    assert analysis_profile_ready_for_review(ctx)


def test_operator_skip_gap_fill_from_pickup_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped, operator_skip_gap_fill

    ctx = isolated_run_ctx(tmp_path, "gap_operator_skip")
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest("seg_001", "seg_002"),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/flow_adaptation.json",
        {
            "topology_class": "one_on_one_asymmetric",
            "production_style": "standard",
            "ranking_weights": {},
            "sfx_density": {},
            "summary_plain": "test",
        },
        skip_handoff=True,
    )

    operator_skip_gap_fill(ctx, reason="operator chose skip")

    assert gap_fill_was_skipped(ctx)
    assert ctx.is_done("missing_framing")
    assert ctx.is_done("optimal_questions")
    adapt = ctx.read_json("understanding/flow_adaptation.json")
    assert adapt["operator_overrides"]["gap_fill_skipped"] is True
    assert adapt["operator_overrides"]["pickup_speaker_confirmed"] is True
    report = ctx.read_json("understanding/gap_report.json")
    assert report.get("interviewer_lines") == []
    assert report.get("gaps") == []


def test_gap_fill_skip_api_does_not_double_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from interview_mux.web.server import create_app
    from run_fixtures import init_run_meta_for_test, patch_executions_root, patch_server_ctx

    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "gap_skip_api")
    init_run_meta_for_test(ctx)
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest("seg_001"),
        skip_handoff=True,
    )
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app(), raise_server_exceptions=False)
    res = client.post(f"/api/runs/{ctx.run_id}/gap-fill/skip", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True
    assert body.get("gap_fill_mode") == "skipped"
    assert gap_fill_was_skipped(ctx)
