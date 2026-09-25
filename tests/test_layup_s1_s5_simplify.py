"""S1–S5 simplify: layup gap publish guard, foreign-write skip, CTA pre-LLM only."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.loud_fail import LoudStageFailure
from interview_mux.nugget_layup import (
    PLAN_REL,
    _compose_shards_block_gap_publish,
    commit_layup_gap_authority,
    layup_claimed_air_missing_high_gap,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    _high_gap_unframed_incompleteness,
    high_gap_heal_resume_stage,
)
from run_fixtures import isolated_run_ctx, minimal_gap_evaluations, minimal_gap_report


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return isolated_run_ctx(tmp_path, "layup_s1_s5")


def test_s1_mid_shard_blocks_gap_publish(ctx: RunContext) -> None:
    plan = {
        "ordered_segment_ids": ["seg_001"],
        "layups": [{"target_segment_id": "seg_001", "skip": True}],
        "_meta": {
            "compose_shards_pending": True,
            "compose_shard_index": 1,
            "compose_shard_total": 3,
        },
    }
    assert _compose_shards_block_gap_publish(plan) is True
    ctx.write_json(PLAN_REL, plan, skip_handoff=True)
    with pytest.raises((LoudStageFailure, RuntimeError)):
        commit_layup_gap_authority(ctx, plan)


def test_s1_final_shard_allows_publish_guard(ctx: RunContext) -> None:
    plan = {
        "ordered_segment_ids": ["seg_001"],
        "layups": [
            {
                "target_segment_id": "seg_001",
                "skip": False,
                "text": "A grounded host bridge into the native.",
            }
        ],
        "_meta": {
            "compose_shards_pending": True,
            "compose_shard_index": 2,
            "compose_shard_total": 2,
        },
    }
    assert _compose_shards_block_gap_publish(plan) is False


def test_s2_layup_skips_manifest_and_brief_writes(ctx: RunContext) -> None:
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "hi",
                    "start_ms": 0,
                    "end_ms": 1000,
                }
            ]
        },
        stage_key="segment_classification",
        skip_handoff=True,
    )
    before = ctx.read_json("segments/manifest.json")
    # Attempt under layup stage key — must no-op (S2).
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_999",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "poison",
                    "start_ms": 0,
                    "end_ms": 1000,
                }
            ]
        },
        stage_key="nugget_layup_compose",
        skip_handoff=True,
    )
    after = ctx.read_json("segments/manifest.json")
    assert after == before

    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "keep", "topics": [{"name": "guest", "summary": "guest arc"}]},
        stage_key="content_context",
        skip_handoff=True,
    )
    brief_before = ctx.read_json("understanding/content_brief.json")
    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "poison", "topics": [{"name": "guest", "summary": "guest arc"}]},
        stage_key="nugget_layup_compose",
        skip_handoff=True,
    )
    assert ctx.read_json("understanding/content_brief.json") == brief_before


def test_s5_layup_incompleteness_only_when_claimed_air(
    ctx: RunContext,
) -> None:
    ctx.write_json(
        "understanding/gap_evaluations.json",
        minimal_gap_evaluations(
            {
                "segment_id": "seg_001",
                "self_explanatory": False,
                "gap_type": "missing_setup",
                "listener_confusion": "who",
                "severity": "high",
            }
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(),
        skip_handoff=True,
    )
    # Empty plan — framing debt, not layup incompleteness.
    ctx.write_json(
        PLAN_REL,
        {"ordered_segment_ids": ["seg_001"], "layups": []},
        skip_handoff=True,
    )
    assert layup_claimed_air_missing_high_gap(ctx) == []
    assert _high_gap_unframed_incompleteness(ctx, "nugget_layup_compose") is None
    assert high_gap_heal_resume_stage(ctx) == "gap_framing_compose"

    ctx.write_json(
        PLAN_REL,
        {
            "ordered_segment_ids": ["seg_001"],
            "layups": [
                {
                    "target_segment_id": "seg_001",
                    "skip": False,
                    "text": "Host setup into the high-gap beat.",
                }
            ],
        },
        skip_handoff=True,
    )
    assert "seg_001" in layup_claimed_air_missing_high_gap(ctx)
    reason = _high_gap_unframed_incompleteness(ctx, "nugget_layup_compose")
    assert reason and "nugget_layup_compose" in reason
    assert high_gap_heal_resume_stage(ctx) == "nugget_layup_compose"
