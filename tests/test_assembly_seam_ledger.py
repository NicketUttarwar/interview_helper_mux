"""Regression tests for naked-seam glue + assembly ledger."""

from __future__ import annotations

import pytest

from interview_mux.assembly_ledger import assert_ledger_no_naked_seams, build_assembly_ledger
from interview_mux.bridge_completeness import missing_reorder_bridges
from interview_mux.order_hash import order_hashes_match, ordered_segment_ids_hash, stamp_order_hash
from interview_mux.reorder_bridges import build_reorder_bridges
from interview_mux.seam_glue import default_bridge_text, mint_missing_transitions
from interview_mux.stages.assembly import build_flow1_edl
from interview_mux.spoken_meta_lint import assert_speakable_or_raise


class _FakeCtx:
    def __init__(self, root):
        self.run_dir = root
        self._files: dict[str, dict] = {}
        self.logs: list[str] = []

    def artifact_exists(self, rel: str) -> bool:
        return rel in self._files or (self.run_dir / rel).is_file()

    def read_json(self, rel: str):
        if rel in self._files:
            return self._files[rel]
        import json

        return json.loads((self.run_dir / rel).read_text())

    def write_json(self, rel: str, doc: dict) -> None:
        self._files[rel] = doc
        path = self.run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        path.write_text(json.dumps(doc))

    def path(self, *parts: str):
        return self.run_dir.joinpath(*parts)

    def log(self, msg: str, **_kwargs) -> None:
        self.logs.append(msg)


def _seg_map():
    # Mirrors the exec_1129 hard cut: seg_010 (215–240s) → seg_002 (60–94s)
    return {
        "seg_010": {
            "segment_id": "seg_010",
            "start_ms": 215_020,
            "end_ms": 240_000,
            "text": "protein shake and then idli for breakfast",
        },
        "seg_002": {
            "segment_id": "seg_002",
            "start_ms": 60_000,
            "end_ms": 94_140,
            "text": "cash in the bank was thin",
        },
        "seg_003": {
            "segment_id": "seg_003",
            "start_ms": 94_140,
            "end_ms": 95_000,
            "text": "next contiguous beat",
        },
    }


def test_detects_seg_010_to_seg_002_source_jump():
    segs = _seg_map()
    doc = build_reorder_bridges(["seg_010", "seg_002", "seg_003"], segs)
    pairs = {(p["after_id"], p["before_id"]): p for p in doc["pairs"]}
    assert ("seg_010", "seg_002") in pairs
    assert pairs[("seg_010", "seg_002")]["source_gap_ms"] == -180_000
    # contiguous 002→003 skipped
    assert ("seg_002", "seg_003") not in pairs


def test_wildcard_vo_covers_reorder_pair_when_before_vo_exists():
    """Any placement:before gap VO on the destination covers the seam (one host turn)."""
    bridges = {
        "pairs": [
            {
                "after_id": "seg_010",
                "before_id": "seg_002",
                "kind": "reorder",
                "source_gap_ms": -180_000,
            }
        ]
    }
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_x",
                "targets_segment_id": "seg_002",
                "placement": "before",
                "delivery": "synthesize",
                "text": "What changed as we get to that beat?",
            }
        ]
    }
    missing = missing_reorder_bridges(bridges, gap_report=gap, transitions=None)
    assert missing == []


def test_pair_transition_covers_and_mints(monkeypatch):
    bridges = {
        "pairs": [
            {
                "after_id": "seg_010",
                "before_id": "seg_002",
                "after_segment_id": "seg_010",
                "before_segment_id": "seg_002",
                "kind": "reorder",
                "source_gap_ms": -180_000,
            }
        ]
    }
    missing = missing_reorder_bridges(bridges, transitions=None)
    assert missing

    text = default_bridge_text(missing[0])
    assert_speakable_or_raise(text, context="transition")
    assert "cash in the bank" not in text.lower()
    assert "protein shake" not in text.lower()

    import tempfile
    from pathlib import Path

    from interview_mux.synthetic_framing import synthetic_framing_cfg

    monkeypatch.setattr(
        "interview_mux.synthetic_framing.synthetic_framing_cfg",
        lambda cfg=None: {**synthetic_framing_cfg(), "allow_canned_bridge_fallback": True},
    )

    with tempfile.TemporaryDirectory() as td:
        ctx = _FakeCtx(Path(td))
        with pytest.raises(ValueError, match="spoken_copy_guard"):
            mint_missing_transitions(ctx, missing, transitions={"transitions": []})


def test_edl_inserts_transition_between_jump():
    segs = _seg_map()
    selection = {"ordered_segment_ids": ["seg_010", "seg_002"]}
    transitions = {
        "transitions": [
            {
                "after_segment_id": "seg_010",
                "before_segment_id": "seg_002",
                "text": "Stepping back—here's what led there.",
                "type": "chapter",
            }
        ]
    }

    def _resolve(_a, _b):
        return None  # no wav — clip still present with text

    edl = build_flow1_edl(
        selection=selection,
        segments_by_id=segs,
        transitions=transitions,
        resolve_transition_path=_resolve,
    )
    types = [c.get("type") for c in edl["clips"]]
    assert "transition" in types
    # speech → (optional silence) → transition → …
    speech_ids = [c["segment_id"] for c in edl["clips"] if c.get("type") == "speech"]
    assert speech_ids == ["seg_010", "seg_002"]
    tr = next(c for c in edl["clips"] if c.get("type") == "transition")
    assert tr["after_segment_id"] == "seg_010"
    assert tr["before_segment_id"] == "seg_002"


def test_assembly_ledger_marks_naked_then_glued(tmp_path):
    segs = _seg_map()
    ctx = _FakeCtx(tmp_path)
    ctx.write_json(
        "segments/manifest.json",
        {"segments": list(segs.values())},
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_010", "seg_002"],
            "chapters": [
                {
                    "chapter_id": "ch_01",
                    "title": "Founding Sparks",
                    "segment_ids": ["seg_010", "seg_002"],
                }
            ],
        },
    )
    ctx.write_json(
        "understanding/reorder_bridges.json",
        build_reorder_bridges(["seg_010", "seg_002"], segs),
    )

    naked_edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_010", "seg_002"]},
        segments_by_id=segs,
        transitions={"transitions": []},
    )
    # Simulate durations so glue detection works; inject a fake transition atom path
    ledger = build_assembly_ledger(ctx, edl=naked_edl)
    assert ledger["naked_seam_count"] >= 1
    with pytest.raises(SystemExit):
        assert_ledger_no_naked_seams(ledger)

    # With an audible transition clip between speech
    glued = {
        "version": 1,
        "ordered_segment_ids": ["seg_010", "seg_002"],
        "timeline_duration_ms": 60_000,
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_010",
                "source_start_ms": 215_020,
                "source_end_ms": 240_000,
                "timeline_start_ms": 0,
                "duration_ms": 24_980,
            },
            {
                "type": "transition",
                "after_segment_id": "seg_010",
                "before_segment_id": "seg_002",
                "text": "Stepping back—here's what led there.",
                "source_path": "master/transitions/tr_seg_010_seg_002.wav",
                "timeline_start_ms": 24_980,
                "duration_ms": 3500,
            },
            {
                "type": "speech",
                "segment_id": "seg_002",
                "source_start_ms": 60_000,
                "source_end_ms": 94_140,
                "timeline_start_ms": 28_480,
                "duration_ms": 34_140,
            },
        ],
    }
    ledger2 = build_assembly_ledger(ctx, edl=glued)
    assert ledger2["complete"] is True
    assert_ledger_no_naked_seams(ledger2)
    assert any(a["type"] == "transition" for a in ledger2["atoms"])
    assert ledger2["chapters"]


def test_order_hash_lock():
    sel = stamp_order_hash({"ordered_segment_ids": ["seg_010", "seg_002"]})
    edl = stamp_order_hash({"ordered_segment_ids": ["seg_010", "seg_002"]})
    assert order_hashes_match(sel, edl)
    assert sel["order_content_hash"] == ordered_segment_ids_hash(["seg_010", "seg_002"])
    drifted = stamp_order_hash({"ordered_segment_ids": ["seg_002", "seg_010"]})
    assert not order_hashes_match(sel, drifted)
