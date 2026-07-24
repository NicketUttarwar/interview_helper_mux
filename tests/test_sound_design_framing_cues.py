"""Sound design payload includes framing VO category cues."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.gap_framing import framing_vo_for_sound_design, normalize_interviewer_line
from interview_mux.run_context import RunContext
from run_fixtures import minimal_gap_line, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_sd_framing", create=True)
    line = normalize_interviewer_line(
        {
            **minimal_gap_line(line_id="vo_sum_1", targets_segment_id="seg_002"),
            "line_category": "segment_summary",
            "text": "Host summarizes.",
            "estimated_duration_sec": 5.0,
        },
        eligible="spk_0",
        delivery="synthesize",
    )
    run.write_json("understanding/gap_report.json", {"interviewer_lines": [line]}, skip_handoff=True)
    return run


def test_framing_vo_for_sound_design(ctx: RunContext) -> None:
    rows = framing_vo_for_sound_design(ctx)
    assert len(rows) == 1
    assert rows[0]["cue_role"] == "vo_summary"
    assert rows[0]["estimated_duration_sec"] == 5.0
