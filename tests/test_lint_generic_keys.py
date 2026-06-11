from __future__ import annotations

from interview_mux.deterministic_lint import deterministic_lint
from run_fixtures import isolated_run_ctx, minimal_manifest, patch_merged_config


def test_cross_artifact_refs_valid_rejects_orphan(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": False}}})
    ctx = isolated_run_ctx(tmp_path, "lint_refs")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"))
    envelope = {
        "status": "complete",
        "confidence": 0.9,
        "artifacts": {
            "evaluations": [{"segment_id": "seg_orphan", "self_explanatory": False, "gap_type": "x"}]
        },
    }
    errors = deterministic_lint("missing_framing", envelope, ctx)
    assert any("cross_artifact_refs_valid" in e for e in errors)


def test_segment_coverage_ratio_low(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": False}}})
    ctx = isolated_run_ctx(tmp_path, "lint_cov")
    segs = [minimal_manifest(f"seg_{i:03d}")["segments"][0] for i in range(1, 11)]
    ctx.write_json("segments/manifest.json", {"segments": segs})
    envelope = {
        "status": "complete",
        "confidence": 0.9,
        "artifacts": {"evaluations": [{"segment_id": "seg_001", "self_explanatory": True, "gap_type": "ok"}]},
    }
    errors = deterministic_lint("missing_framing", envelope, ctx)
    assert any("segment_coverage_ratio" in e for e in errors)


def test_min_row_count_met_speaker_roles(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_min")
    errors = deterministic_lint(
        "speaker_roles",
        {"status": "complete", "confidence": 0.9, "artifacts": {"speakers": []}},
        ctx,
    )
    assert any("min_row_count_met" in e for e in errors)


def test_truncation_requires_decompose(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_trunc")
    errors = deterministic_lint(
        "content_context",
        {"status": "complete", "confidence": 0.9, "artifacts": {"thesis": "ok", "topics": []}},
        ctx,
        truncation_flags=["max_stage_data_chars"],
        routed_via_collate=False,
    )
    assert any("truncation_requires_decompose" in e for e in errors)


def test_confidence_gte_min(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_conf")
    errors = deterministic_lint(
        "content_context",
        {"status": "complete", "confidence": 0.5, "artifacts": {"thesis": "ok", "topics": [{"name": "T"}]}},
        ctx,
    )
    assert any("confidence_gte_min" in e for e in errors)
