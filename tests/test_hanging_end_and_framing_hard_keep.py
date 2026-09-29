"""Hanging ends extend to a complete thought; framing coverage excludes hard keeps (ISSUES 57)."""

from __future__ import annotations

import pytest

from interview_mux.stages.assembly import extend_hanging_end_to_thought


def _w(text: str, start: int, end: int) -> dict:
    return {"text": text, "start_ms": start, "end_ms": end}


# exec_052 seg_060 ended "...this is going to be" at 3162250; the tape goes on.
WORDS = [
    _w("this", 3161670, 3161810),
    _w("is", 3161810, 3161950),
    _w("going", 3161950, 3162030),
    _w("to", 3162030, 3162100),
    _w("be", 3162100, 3162250),
    _w("really", 3162300, 3162600),
    _w("important.", 3162650, 3163200),
    _w("So", 3164400, 3164600),
    _w("next", 3164650, 3164900),
    _w("question.", 3164950, 3165400),
]


def test_extends_to_the_first_complete_thought() -> None:
    assert extend_hanging_end_to_thought(WORDS, 3162250) == 3163200


def test_never_reaches_into_the_next_on_air_segment() -> None:
    assert extend_hanging_end_to_thought(WORDS, 3162250, next_keeper_start_ms=3162500) is None


def test_tape_adjacent_next_segment_blocks_any_extension() -> None:
    # exec_052: seg_059 ended at 3148170 and seg_060 started at 3148170.
    assert extend_hanging_end_to_thought(WORDS, 3162250, next_keeper_start_ms=3162250) is None


def test_no_completion_in_window_returns_none() -> None:
    assert extend_hanging_end_to_thought(WORDS[:5], 3162250) is None


def test_framing_coverage_drops_hard_keeps(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from interview_mux import gap_framing as gf
    from interview_mux.run_context import RunContext

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_framing_cov", create=True)
    monkeypatch.setattr(gf, "load_gap_framing_plan", lambda c: None)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {"line_id": "vo_1", "replaces_source_segments": ["seg_059", "seg_070"]}
            ],
            "gaps": [],
        },
    )
    monkeypatch.setattr("interview_mux.hard_keep.hard_keep_segment_ids", lambda c: {"seg_059"})
    assert gf.ranking_exclude_segment_ids(ctx) == {"seg_070"}
