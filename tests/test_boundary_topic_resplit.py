"""Tests for boundary_topic_resplit stage (post-reanchor overloaded-segment pass)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.stages.segmentation import run_boundary_topic_resplit
from interview_mux.v2.config import ANALYSIS_ORDER
from run_fixtures import (
    isolated_run_ctx,
    minimal_content_brief,
    minimal_manifest,
    minimal_manifest_segment,
    patch_merged_config,
)


def _boundary(segment_id: str, start_ms: int, end_ms: int, reason: str = "topic_shift") -> dict:
    return {
        "segment_id": segment_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "boundary_type": "topic",
        "proposed_split_reason": reason,
    }


def test_analysis_order_places_resplit_after_reanchor() -> None:
    assert ANALYSIS_ORDER.index("content_brief_reanchor") < ANALYSIS_ORDER.index(
        "boundary_topic_resplit"
    )
    assert ANALYSIS_ORDER.index("boundary_topic_resplit") < ANALYSIS_ORDER.index(
        "sonic_context_build"
    )


def test_boundary_topic_resplit_skips_when_no_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "resplit_empty")
    run_boundary_topic_resplit(ctx)
    assert ctx.is_done("boundary_topic_resplit")


def test_boundary_topic_resplit_marks_done_when_not_overloaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "resplit_ok")
    patch_merged_config(
        monkeypatch,
        {"analysis": {"segmentation": {"fine_grained": False, "resegment_pass": False}}},
    )
    ctx.write_json(
        "segments/boundaries.json",
        {"boundaries": [_boundary("seg_001", 0, 5_000)]},
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001", start_ms=0, end_ms=5_000, topic_tags=["intro"])
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        minimal_content_brief(
            topics=[{"name": "intro", "summary": "Intro topic.", "segment_ids": ["seg_001"]}]
        ),
        skip_handoff=True,
    )
    run_boundary_topic_resplit(ctx)
    assert ctx.is_done("boundary_topic_resplit")
    boundaries = ctx.read_json("segments/boundaries.json")
    assert len(boundaries.get("boundaries") or []) == 1


def test_boundary_topic_resplit_enriches_without_llm_when_resegment_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "resplit_enrich")
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "segmentation": {
                    "fine_grained": True,
                    "resegment_pass": False,
                    "max_segment_duration_ms": 8_000,
                }
            }
        },
    )
    ctx.write_json(
        "segments/boundaries.json",
        {"boundaries": [_boundary("seg_001", 0, 60_000)]},
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_001", start_ms=0, end_ms=60_000, topic_tags=["a", "b", "c"]
            )
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        minimal_content_brief(
            topics=[
                {"name": "a", "summary": "A.", "segment_ids": ["seg_001"]},
                {"name": "b", "summary": "B.", "segment_ids": ["seg_001"]},
                {"name": "c", "summary": "C.", "segment_ids": ["seg_001"]},
            ]
        ),
        skip_handoff=True,
    )
    ctx.write_json("transcript/full.json", {"words": []}, skip_handoff=True)
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {
                    "speaker_id": "spk_001",
                    "role": "interviewer",
                    "confidence": 0.9,
                    "evidence": ["asks questions"],
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/flow_adaptation.json",
        {"segmentation_policy": {"resegment_pass": False}},
        skip_handoff=True,
    )

    run_boundary_topic_resplit(ctx)
    assert ctx.is_done("boundary_topic_resplit")
    assert ctx.artifact_exists("segments/boundaries.json")
