"""Tests for gap_report_api CRUD."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.gap_report_api import add_line, delete_line, list_lines
from interview_mux.run_context import RunContext


@pytest.fixture
def gap_ctx(tmp_path: Path) -> RunContext:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "understanding").mkdir()
    (run_dir / "understanding" / "gap_report.json").write_text(
        json.dumps({"interviewer_lines": []}), encoding="utf-8"
    )
    (run_dir / "understanding" / "source_topology.json").write_text(
        json.dumps(
            {
                "topology_class": "one_on_one_balanced",
                "speakers": [{"speaker_id": "spk_a", "word_count": 100}, {"speaker_id": "spk_b", "word_count": 500}],
                "pickup_eligible_speaker_id": "spk_a",
            }
        ),
        encoding="utf-8",
    )
    return RunContext(str(run_dir))


def test_add_and_delete_line(gap_ctx: RunContext) -> None:
    line = add_line(gap_ctx, {"text": "That's wild.", "gap_type": "reaction_line"})
    assert line["line_id"]
    assert line["voice_speaker_id"] == "spk_a"
    lines = list_lines(gap_ctx)
    assert len(lines) == 1
    delete_line(gap_ctx, line["line_id"])
    assert list_lines(gap_ctx) == []
