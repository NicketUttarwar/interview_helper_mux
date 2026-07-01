from __future__ import annotations

import pytest

from interview_mux.stage_acceptance import stage_acceptance_ok
from interview_mux.write_staging import write_pending_content
from run_fixtures import isolated_run_ctx, minimal_manifest, patch_merged_config


def _boundaries_doc(*, duplicate: bool = False) -> dict:
    rows = [
        {
            "segment_id": "seg_001",
            "start_ms": 0,
            "end_ms": 1000,
            "speaker_id": "spk_1",
            "type": "interview",
            "proposed_split_reason": "topic_shift",
        },
        {
            "segment_id": "seg_002",
            "start_ms": 1000,
            "end_ms": 2000,
            "speaker_id": "spk_1",
            "type": "interview",
            "proposed_split_reason": "topic_shift",
        },
    ]
    if duplicate:
        rows.append(
            {
                "segment_id": "seg_001",
                "start_ms": 900,
                "end_ms": 1100,
                "speaker_id": "spk_1",
                "type": "interview",
                "proposed_split_reason": "topic_shift",
            }
        )
    return {"boundaries": rows}


def test_stage_acceptance_ok_clean_boundaries(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"artifact_issue_triage": {"enabled": True}}},
    )
    monkeypatch.setattr(
        "interview_mux.interview_spine.config.spine_enabled",
        lambda *_a, **_k: False,
    )
    ctx = isolated_run_ctx(tmp_path, "accept_clean")
    write_pending_content(
        ctx,
        "boundary_detection",
        "segments/boundaries.json",
        data=_boundaries_doc(),
    )
    result = stage_acceptance_ok(
        ctx,
        "boundary_detection",
        staged=True,
        include_cross_validate=False,
        include_downstream=False,
    )
    assert result.ok


def test_stage_acceptance_blocks_duplicate_segment_id(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"artifact_issue_triage": {"enabled": True}}},
    )
    monkeypatch.setattr(
        "interview_mux.interview_spine.config.spine_enabled",
        lambda *_a, **_k: False,
    )
    ctx = isolated_run_ctx(tmp_path, "accept_dup")
    write_pending_content(
        ctx,
        "boundary_detection",
        "segments/boundaries.json",
        data=_boundaries_doc(duplicate=True),
    )
    result = stage_acceptance_ok(ctx, "boundary_detection", staged=True, include_cross_validate=False)
    assert not result.ok
    joined = " ".join(result.lint_errors + result.all_errors).lower()
    assert "duplicate" in joined or "seg_001" in joined


def test_stage_acceptance_nullable_topic_tags(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from run_fixtures import minimal_manifest_segment

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "artifact_issue_triage": {"enabled": True},
                "llm_null_policy": {"enabled": True, "hard_stop_on_critical_null": True},
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "accept_null")
    seg = minimal_manifest_segment("seg_001", topic_tags=None)
    seg["topic_tags_unavailable_reason"] = "not inferred"
    write_pending_content(
        ctx,
        "segment_classification",
        "segments/manifest.json",
        data=minimal_manifest([seg]),
    )
    result = stage_acceptance_ok(ctx, "segment_classification", staged=True, include_cross_validate=False)
    assert result.ok or not result.null_violations
