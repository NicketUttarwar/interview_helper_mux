from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.nle_state import (
    clamp_trim_bounds,
    nle_edit_categories,
    snap_boundary_for_segment,
)
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run_id = "exec_nle_snap"
    c = RunContext(run_id, create=True)
    init_run_meta_for_test(c)
    c.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_a",
                    "start_ms": 0,
                    "end_ms": 10_000,
                    "type": "interviewee_answer",
                    "speaker_id": "spk1",
                    "speaker_role": "interviewee",
                    "topic_tags": ["topic"],
                }
            ]
        },
    )
    c.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "hello", "start_ms": 1000, "end_ms": 1500},
                {"text": "world", "start_ms": 1600, "end_ms": 2100},
            ]
        },
    )
    return c


def test_clamp_trim_bounds_enforces_minimum() -> None:
    start, end = clamp_trim_bounds(
        manifest_start=0,
        manifest_end=10_000,
        start_ms=100,
        end_ms=500,
    )
    assert end - start >= 300


def test_snap_boundary_nudges_toward_word(ctx: RunContext) -> None:
    snapped = snap_boundary_for_segment(
        ctx, segment_id="seg_a", ms=1520, edge="end"
    )
    assert 1400 <= snapped <= 2200


def test_nle_edit_categories_trim_only() -> None:
    cats = nle_edit_categories(
        {"segment_overrides": {"seg_a": {"start_ms": 100, "end_ms": 9000}}}
    )
    assert cats["trim_only"] is True
    assert cats["structural"] is False
    assert cats["has_any"] is True
