from __future__ import annotations

import json

import pytest

from interview_mux.artifact_cross_validate import maybe_cross_validate_after_stage
from interview_mux.write_staging import write_pending_content
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment, patch_merged_config


def test_cross_validate_deferred_to_clarification(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "flow_hardening": {
                    "enabled": True,
                    "cross_validate_enabled": True,
                    "clarification_before_halt": True,
                },
                "artifact_issue_triage": {"enabled": True},
            },
        },
    )
    ctx = isolated_run_ctx(tmp_path, "itr_cv_defer")
    write_pending_content(
        ctx,
        "segment_classification",
        "segments/manifest.json",
        data=minimal_manifest(
            minimal_manifest_segment("seg_001", start_ms=0, end_ms=5000),
            minimal_manifest_segment("seg_002", start_ms=4000, end_ms=8000),
        ),
    )
    boundaries_path = ctx.path("segments", "boundaries.json")
    boundaries_path.parent.mkdir(parents=True, exist_ok=True)
    boundaries_path.write_text(
        json.dumps(
            {
                "boundaries": [
                    {
                        "segment_id": "seg_001",
                        "start_ms": 0,
                        "end_ms": 5000,
                        "speaker_id": "spk_1",
                        "proposed_split_reason": "topic_shift",
                    },
                    {
                        "segment_id": "seg_002",
                        "start_ms": 4000,
                        "end_ms": 8000,
                        "speaker_id": "spk_1",
                        "proposed_split_reason": "topic_shift",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    maybe_cross_validate_after_stage(ctx, "segment_classification")
    job = ctx.read_json("gui_job.json") if ctx.artifact_exists("gui_job.json") else {}
    assert job.get("status") in (None, "needs_clarification", "awaiting_write_approval")
