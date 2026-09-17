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


def test_sanitize_transitions_framing_dedupe_drops_frozen_redundant() -> None:
    """Frozen pair still covered by layup VO must leave kept + freeze (exec_11630)."""
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_018", "seg_020", "seg_021"])
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_020",
                    "targets_segment_id": "seg_020",
                    "placement": "before",
                    "delivery": "synthesize",
                    "line_category": "segment_summary",
                    "text": "What changed for the assay?",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        FREEZE_REL,
        {
            "version": 1,
            "pairs": ["seg_018->seg_020", "seg_020->seg_021"],
            "count": 2,
            "source": "prior_authority",
        },
        skip_handoff=True,
    )
    doc = {
        "transitions": [
            {
                "after_segment_id": "seg_018",
                "before_segment_id": "seg_020",
                "text": "Moving on — what about the assay?",
            },
            {
                "after_segment_id": "seg_020",
                "before_segment_id": "seg_021",
                "text": "And then?",
            },
        ]
    }
    result = sanitize_transitions(ctx, doc)
    assert result.ok
    kept = [
        (r.get("after_segment_id"), r.get("before_segment_id"))
        for r in result.doc["transitions"]
    ]
    assert ("seg_018", "seg_020") not in kept
    assert ("seg_020", "seg_021") in kept
    assert any(a.get("action") == "framing_dedupe" for a in result.actions)
    on_disk = ctx.read_json(FREEZE_REL)
    assert "seg_018->seg_020" not in (on_disk.get("pairs") or [])
    assert "seg_020->seg_021" in (on_disk.get("pairs") or [])


def test_sanitize_transitions_prunes_reverse_jump() -> None:
    """Reverse tape jumps are pruned via artifact_repairs.prune_reverse_jump_transitions."""
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001", "seg_002"])
    ctx.path("segments").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 500_000,
                    "end_ms": 510_000,
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "Late tape.",
                },
                {
                    "segment_id": "seg_002",
                    "start_ms": 1_000,
                    "end_ms": 5_000,
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "Early tape.",
                },
            ]
        },
        skip_handoff=True,
    )
    doc = {
        "transitions": [
            {
                "after_segment_id": "seg_001",
                "before_segment_id": "seg_002",
                "text": "Jumping backward on tape.",
            }
        ]
    }
    result = sanitize_transitions(ctx, doc)
    kept = [
        (r.get("after_segment_id"), r.get("before_segment_id"))
        for r in result.doc.get("transitions") or []
        if isinstance(r, dict)
    ]
    assert ("seg_001", "seg_002") not in kept
    assert any(a.get("action") == "prune_reverse_jump" for a in result.actions)


def test_sanitize_transitions_missing_prune_import_fails_loud(monkeypatch) -> None:
    """Missing prune_reverse_jump_transitions must surface in errors (no silent pass)."""
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001", "seg_002"])
    monkeypatch.delattr(
        "interview_mux.artifact_repairs.prune_reverse_jump_transitions",
        raising=True,
    )
    doc = {
        "transitions": [
            {
                "after_segment_id": "seg_001",
                "before_segment_id": "seg_002",
                "text": "Adjacent bridge.",
            }
        ]
    }
    result = sanitize_transitions(ctx, doc)
    assert any(
        str(e).startswith("prune_reverse_jump_failed") for e in (result.errors or [])
    )
    assert any(a.get("action") == "prune_reverse_jump_failed" for a in result.actions)


def test_sanitize_transitions_framing_dedupe_import_fails_loud(monkeypatch) -> None:
    """Missing dedupe_transitions_for_framing must surface (exec_11630 #9 residual)."""
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001", "seg_002"])
    monkeypatch.delattr(
        "interview_mux.gap_framing.dedupe_transitions_for_framing",
        raising=True,
    )
    doc = {
        "transitions": [
            {
                "after_segment_id": "seg_001",
                "before_segment_id": "seg_002",
                "text": "Adjacent bridge.",
            }
        ]
    }
    result = sanitize_transitions(ctx, doc)
    assert any(
        str(e).startswith("framing_dedupe_failed") for e in (result.errors or [])
    )
    assert any(a.get("action") == "framing_dedupe_failed" for a in result.actions)


def test_heal_redundant_framing_transitions_strips_pair_freeze() -> None:
    from interview_mux.gap_framing import heal_redundant_framing_transitions

    ctx = RunContext(create=True)
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_020",
                    "targets_segment_id": "seg_020",
                    "placement": "before",
                    "delivery": "synthesize",
                    "line_category": "segment_summary",
                    "text": "What changed for the assay?",
                }
            ]
        },
        skip_handoff=True,
    )
    import json

    # Bypass hot-write sanitize so heal sees the redundant row on disk.
    tr_path = ctx.path("master", "transitions.json")
    tr_path.write_text(
        json.dumps(
            {
                "transitions": [
                    {
                        "after_segment_id": "seg_018",
                        "before_segment_id": "seg_020",
                        "text": "Moving on?",
                        "type": "chapter",
                    },
                    {
                        "after_segment_id": "seg_020",
                        "before_segment_id": "seg_021",
                        "text": "Next?",
                        "type": "chapter",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    fr_path = ctx.path("master", "transitions_pair_freeze.json")
    fr_path.write_text(
        json.dumps(
            {
                "version": 1,
                "pairs": ["seg_018->seg_020", "seg_020->seg_021"],
                "count": 2,
            }
        ),
        encoding="utf-8",
    )
    out = heal_redundant_framing_transitions(ctx)
    assert out.get("ok")
    assert "seg_018->seg_020" in (out.get("dropped") or [])
    disk = ctx.read_json("master/transitions.json")
    pairs = [
        (r.get("after_segment_id"), r.get("before_segment_id"))
        for r in (disk.get("transitions") or [])
        if isinstance(r, dict)
    ]
    assert ("seg_018", "seg_020") not in pairs
    freeze = ctx.read_json(FREEZE_REL)
    assert "seg_018->seg_020" not in (freeze.get("pairs") or [])
