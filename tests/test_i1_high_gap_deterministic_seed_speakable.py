"""Cascade: deterministic high-gap seeds must not paste QC scaffolding on air.

MUX_FORENSICS=0 — predicate flip for gap_framing_compose pre-flush barrier
(spoken_edit_structure_ref on vo_seed_* from listener_confusion paste).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from interview_mux.high_gap_vo import (
    _deterministic_high_gap_line,
    seed_uncovered_high_gaps_deterministic,
)
from interview_mux.spoken_meta_lint import lint_spoken_text, spoken_structure_hits


def test_deterministic_seed_never_pastes_clip_scaffolding() -> None:
    ctx = MagicMock()
    row = {
        "segment_id": "seg_049",
        "gap_type": "missing_setup",
        "listener_confusion": (
            "The listener hears the problem of waiting months for imaging but "
            "the clip cuts off before the proposed weeks-based alternative is explained"
        ),
        "mission": "the clip cuts off mid-thought",
    }
    text = _deterministic_high_gap_line(ctx, row)
    assert text.strip()
    assert "the clip" not in text.lower()
    assert "listener hears" not in text.lower()
    assert spoken_structure_hits(text) == []
    assert lint_spoken_text(text, label="gap_report[vo_seed_seg_049]") == []


def test_seed_uncovered_keeps_confusion_in_rationale_only() -> None:
    ctx = MagicMock()
    ctx.artifact_exists.return_value = True
    ctx.read_json.return_value = {
        "evaluations": [
            {
                "segment_id": "seg_049",
                "severity": "high",
                "gap_type": "missing_setup",
                "listener_confusion": (
                    "The listener hears waiting months but the clip cuts off "
                    "before the weeks-based alternative is explained"
                ),
            }
        ]
    }
    out: dict = {"interviewer_lines": []}
    applied: list = []
    n = seed_uncovered_high_gaps_deterministic(
        ctx, out, applied=applied, origin="high_gap_vo_fill_no_key"
    )
    assert n == 1
    line = out["interviewer_lines"][0]
    assert line["line_id"] == "vo_seed_seg_049"
    assert "the clip" not in str(line.get("text") or "").lower()
    assert spoken_structure_hits(str(line.get("text") or "")) == []
    assert "the clip" in str(line.get("rationale") or "").lower()
