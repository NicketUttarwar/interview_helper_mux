from __future__ import annotations

import pytest

from interview_mux.artifact_cross_validate import validate_cross_artifacts
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment


def test_post_segmentation_boundary_not_in_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_seg")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), stage_key="segment_classification")
    boundaries_path = ctx.path("segments", "boundaries.json")
    boundaries_path.parent.mkdir(parents=True, exist_ok=True)
    boundaries_path.write_text(
        '{"boundaries": [{"segment_id": "seg_999", "start_ms": 0, "end_ms": 1000}]}',
        encoding="utf-8",
    )
    errors = validate_cross_artifacts(ctx, "post_segmentation")
    assert any("seg_999" in e for e in errors)


def test_post_gaps_evaluation_segment_not_in_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_gaps")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), stage_key="segment_classification")
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {"evaluations": [{"segment_id": "seg_missing", "self_explanatory": False}]},
        skip_handoff=True,
    )
    errors = validate_cross_artifacts(ctx, "post_gaps")
    assert any("seg_missing" in e for e in errors)


def test_maybe_cross_validate_raises_on_failure(tmp_path, monkeypatch):
    from interview_mux.artifact_cross_validate import maybe_cross_validate_after_stage
    from run_fixtures import patch_merged_config

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "cross_validate_enabled": True}}},
    )
    ctx = isolated_run_ctx(tmp_path, "cv_raise")
    manifest_path = ctx.path("segments", "manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text('{"segments": []}', encoding="utf-8")
    with pytest.raises(SystemExit, match="Cross-artifact gate"):
        maybe_cross_validate_after_stage(ctx, "segment_classification")
