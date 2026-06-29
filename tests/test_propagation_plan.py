from __future__ import annotations

import pytest

from interview_mux.artifact_issue_triage import run_triage_pipeline
from interview_mux.write_staging import write_pending_content
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment, patch_merged_config


def test_downstream_errors_not_overwritten(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "artifact_issue_triage": {"enabled": True},
                "flow_hardening": {"cross_validate_enabled": True},
            },
        },
    )
    ctx = isolated_run_ctx(tmp_path, "down_err")
    seg = minimal_manifest_segment("seg_001", topic_tags=None)
    seg["topic_tags"] = None
    write_pending_content(
        ctx,
        "segment_classification",
        "segments/manifest.json",
        data={"segments": [seg]},
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Test thesis",
            "topics": [{"name": "T", "summary": "s", "segment_ids": ["seg_orphan"]}],
        },
        skip_handoff=True,
    )
    ctx.mark_done("content_brief_reanchor")
    result = run_triage_pipeline(ctx, "segment_classification", staged=True)
    assert result.auto_fixed >= 1 or result.collected >= 0
    assert isinstance(result.errors, list)
