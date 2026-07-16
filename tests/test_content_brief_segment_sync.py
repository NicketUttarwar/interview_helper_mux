"""Content brief topic segment_ids sync from manifest topic_tags."""

from __future__ import annotations

import pytest

from interview_mux.artifact_repairs import repair_content_brief, sync_content_brief_topic_segment_ids
from interview_mux.write_staging import record_pending_approval, staging_root
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment


def test_repair_content_brief_strips_placeholder_topic_segment_ids(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "brief_strip")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            {
                **minimal_manifest_segment("seg_001"),
                "topic_tags": ["early_life"],
            },
            {
                **minimal_manifest_segment("seg_002"),
                "topic_tags": ["early_life"],
            },
        ),
        skip_handoff=True,
    )
    brief = {
        "thesis": "Test thesis about the interview.",
        "topics": [
            {
                "name": "Foundations: Early life and education",
                "summary": "Background.",
                "segment_ids": ["t_early_life"],
            }
        ],
    }
    repaired, applied = repair_content_brief(ctx, brief)
    seg_ids = repaired["topics"][0]["segment_ids"]
    assert "t_early_life" not in seg_ids
    assert set(seg_ids) == {"seg_001", "seg_002"}
    assert applied


def test_repair_content_brief_keeps_claims_with_approx_time_range_only(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "brief_time_claim")
    brief = {
        "thesis": "Test thesis about the interview.",
        "topics": [{"name": "Pivot", "summary": "Market shift.", "approx_time_range": "03:00-05:00"}],
        "key_claims": [
            {
                "id": "claim_001",
                "claim": "They pivoted to protein bars.",
                "approx_time_range": "03:20-04:10",
                "segment_ids": [],
            }
        ],
    }
    repaired, applied = repair_content_brief(ctx, brief)
    assert len(repaired["key_claims"]) == 1
    assert repaired["key_claims"][0]["approx_time_range"] == "03:20-04:10"
    assert not any(a.get("reason") == "no_evidence" for a in applied)


def test_sync_content_brief_uses_staged_manifest_during_write_approval(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "brief_staged")
    stage_key = "segment_classification"

    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": "Test thesis about the interview subject.",
            "topics": [
                {
                    "name": "Protein bar pivot",
                    "summary": "Market shift.",
                    "segment_ids": ["t_protein_bars"],
                }
            ],
        },
        skip_handoff=True,
    )

    staged_manifest = staging_root(ctx, stage_key) / "segments" / "manifest.json"
    staged_manifest.parent.mkdir(parents=True, exist_ok=True)
    staged_manifest.write_text(
        __import__("json").dumps(
            minimal_manifest(
                {
                    **minimal_manifest_segment("seg_010"),
                    "topic_tags": ["protein_bar_pivot"],
                },
                {
                    **minimal_manifest_segment("seg_011"),
                    "topic_tags": ["protein_bar_pivot"],
                },
            )
        )
    )
    record_pending_approval(ctx, stage_key)

    applied = sync_content_brief_topic_segment_ids(ctx, overlay_stage=stage_key)
    assert applied

    brief = ctx.read_json("understanding/content_brief.json")
    seg_ids = brief["topics"][0]["segment_ids"]
    assert "t_protein_bars" not in seg_ids
    assert set(seg_ids) == {"seg_010", "seg_011"}
