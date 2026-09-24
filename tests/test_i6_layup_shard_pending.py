"""i6: layup final-shard pending stamp must not thrash mark_done (MUX_FORENSICS=0)."""

from __future__ import annotations

from pathlib import Path

from interview_mux.nugget_layup import PLAN_REL
from interview_mux.stage_completion import stage_artifact_incompleteness
from run_fixtures import isolated_run_ctx


def test_final_shard_pending_stamp_does_not_block_completion(tmp_path: Path) -> None:
    """After batched compose, index==total + layups must not return shards_pending."""
    ctx = isolated_run_ctx(tmp_path, "i6_layup_shard_final")
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_a", "seg_b"]},
        skip_handoff=True,
    )
    ctx.write_json(
        PLAN_REL,
        {
            "ordered_segment_ids": ["seg_a", "seg_b"],
            "layups": [
                {"target_segment_id": "seg_a", "text": "Host setup before A.", "skip": False},
                {"target_segment_id": "seg_b", "text": "Host setup before B.", "skip": False},
            ],
            "_meta": {
                "compose_shards_pending": True,
                "compose_shard_index": 2,
                "compose_shard_total": 2,
            },
        },
        skip_handoff=True,
    )
    reason = stage_artifact_incompleteness(ctx, "nugget_layup_compose")
    assert reason is None or "layup_compose_shards_pending" not in str(reason)


def test_mid_shard_pending_still_blocks(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "i6_layup_shard_mid")
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_a", "seg_b"]},
        skip_handoff=True,
    )
    ctx.write_json(
        PLAN_REL,
        {
            "ordered_segment_ids": ["seg_a", "seg_b"],
            "layups": [{"target_segment_id": "seg_a", "text": "partial", "skip": False}],
            "_meta": {
                "compose_shards_pending": True,
                "compose_shard_index": 1,
                "compose_shard_total": 2,
            },
        },
        skip_handoff=True,
    )
    reason = stage_artifact_incompleteness(ctx, "nugget_layup_compose")
    assert reason is not None
    assert "layup_compose_shards_pending" in reason
    assert "shard 1/2" in reason
