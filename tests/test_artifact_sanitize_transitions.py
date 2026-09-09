"""Tests for artifact_sanitize transitions (W4)."""

from __future__ import annotations

from copy import deepcopy

from interview_mux.artifact_sanitize.transitions import FREEZE_REL, sanitize_transitions
from interview_mux.run_context import RunContext


def _write_selection(ctx: RunContext, ids: list[str]) -> None:
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ids,
            "excluded_segment_ids": [],
            "chapters": [],
        },
        skip_handoff=True,
    )


def test_sanitize_transitions_drops_self_loop_and_non_adjacent() -> None:
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001", "seg_002", "seg_003"])
    doc = {
        "transitions": [
            {"after_segment_id": "seg_001", "before_segment_id": "seg_001"},
            {"after_segment_id": "seg_001", "before_segment_id": "seg_003"},
            {"after_segment_id": "seg_001", "before_segment_id": "seg_002"},
            {"after_segment_id": "seg_001", "before_segment_id": "seg_002"},
            {"after_segment_id": "seg_002", "before_segment_id": "seg_003"},
        ]
    }
    result = sanitize_transitions(ctx, doc)
    assert result.ok
    pairs = [
        (r.get("after_segment_id"), r.get("before_segment_id"))
        for r in result.doc["transitions"]
    ]
    assert ("seg_001", "seg_001") not in pairs
    assert ("seg_001", "seg_003") not in pairs
    assert pairs.count(("seg_001", "seg_002")) == 1
    assert ("seg_002", "seg_003") in pairs
    assert any(a.get("action") == "drop_self_loop" for a in result.actions)
    assert any(a.get("action") == "drop_non_adjacent" for a in result.actions)
    assert any(a.get("action") == "dedupe_adjacency" for a in result.actions)


def test_sanitize_transitions_does_not_overwrite_existing_freeze() -> None:
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001", "seg_002", "seg_003"])
    freeze = {
        "version": 1,
        "pairs": ["seg_001->seg_002"],
        "count": 1,
        "source": "prior_authority",
    }
    ctx.write_json(FREEZE_REL, deepcopy(freeze), skip_handoff=True)
    doc = {
        "transitions": [
            {"after_segment_id": "seg_001", "before_segment_id": "seg_002"},
            {"after_segment_id": "seg_002", "before_segment_id": "seg_003"},
        ]
    }
    result = sanitize_transitions(ctx, doc)
    assert result.ok
    # Beyond-freeze pair deferred, not kept as active
    kept = [
        (r.get("after_segment_id"), r.get("before_segment_id"))
        for r in result.doc["transitions"]
    ]
    assert kept == [("seg_001", "seg_002")]
    assert any(a.get("action") == "defer_beyond_freeze" for a in result.actions)
    assert not any(a.get("action") == "stamp_pair_freeze" for a in result.actions)
    on_disk = ctx.read_json(FREEZE_REL)
    assert on_disk["pairs"] == freeze["pairs"]
    assert on_disk["source"] == "prior_authority"
