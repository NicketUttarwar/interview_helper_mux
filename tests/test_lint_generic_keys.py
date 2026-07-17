from __future__ import annotations

from interview_mux.deterministic_lint import deterministic_lint, reconcile_envelope_confidence
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


def test_topic_coverage_segment_ratio_uses_topic_mappings(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": False}}})
    ctx = isolated_run_ctx(tmp_path, "lint_topic_cov")
    segs = [minimal_manifest(f"seg_{i:03d}")["segments"][0] for i in range(1, 6)]
    ctx.write_json("segments/manifest.json", {"segments": segs})
    envelope = {
        "status": "complete",
        "confidence": 0.9,
        "artifacts": {
            "topic_mappings": [
                {"topic": "Theme A", "segment_ids": ["seg_001", "seg_002"], "covered": True},
                {"topic": "Theme B", "segment_ids": ["seg_003", "seg_004"], "covered": True},
            ],
            "coverage_score": 0.8,
        },
    }
    errors = deterministic_lint("topic_coverage_audit", envelope, ctx)
    assert not any("segment_coverage_ratio" in e for e in errors)


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


def test_confidence_gte_min_reconciled_from_topic_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lint_conf_ok")
    errors = deterministic_lint(
        "content_context",
        {
            "status": "complete",
            "confidence": 0.23,
            "artifacts": {
                "thesis": "ok",
                "topics": [
                    {
                        "name": "Topic",
                        "summary": "s",
                        "confidence": 0.86,
                        "approx_time_range": "00:00-01:00",
                    }
                ],
            },
        },
        ctx,
    )
    assert not any("confidence_gte_min" in e for e in errors)


def test_reconcile_speaker_roles_envelope_confidence() -> None:
    envelope = {
        "status": "complete",
        "confidence": 0.3,
        "artifacts": {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.83},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.83},
            ]
        },
    }
    assert reconcile_envelope_confidence("speaker_roles", envelope) is True
    assert envelope["confidence"] == 0.83


def test_reconcile_content_context_envelope_confidence() -> None:
    envelope = {
        "status": "complete",
        "confidence": 0.23,
        "artifacts": {
            "thesis": "Example thesis",
            "topics": [
                {"name": "Topic A", "summary": "s", "confidence": 0.86},
                {"name": "Topic B", "summary": "s", "confidence": 0.82},
            ],
            "key_claims": [{"claim": "c", "confidence": 0.9, "approx_time_range": "00:00-01:00"}],
        },
    }
    assert reconcile_envelope_confidence("content_context", envelope) is True
    assert envelope["confidence"] == 0.82


def test_reconcile_content_context_skips_when_rows_low() -> None:
    envelope = {
        "status": "complete",
        "confidence": 0.23,
        "artifacts": {
            "thesis": "Example thesis",
            "topics": [{"name": "Topic A", "summary": "s", "confidence": 0.2}],
        },
    }
    assert reconcile_envelope_confidence("content_context", envelope) is False
    assert envelope["confidence"] == 0.23
