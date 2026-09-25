"""Tests for gap_report_api CRUD."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.gap_report_api import add_line, delete_line, list_lines
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, write_fixture_json


@pytest.fixture
def gap_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, "gap_api")
    write_fixture_json(
        ctx,
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        stage_key="gap_framing_compose",
    )
    write_fixture_json(
        ctx,
        "understanding/source_topology.json",
        {
            "topology_class": "one_on_one_balanced",
            "speakers": [
                {"speaker_id": "spk_a", "word_count": 100},
                {"speaker_id": "spk_b", "word_count": 500},
            ],
            "pickup_eligible_speaker_id": "spk_a",
        },
    )

    from interview_mux.gap_report_api import write_validated_artifact as orig

    def _compose_gap(ctx_w, rel, data, **kwargs):
        if rel == "understanding/gap_report.json":
            kwargs["stage_key"] = "gap_framing_compose"
        return orig(ctx_w, rel, data, **kwargs)

    monkeypatch.setattr(
        "interview_mux.gap_report_api.write_validated_artifact",
        _compose_gap,
    )
    return ctx


def test_add_and_delete_line(gap_ctx: RunContext) -> None:
    line = add_line(gap_ctx, {"text": "That's wild.", "gap_type": "reaction_line"})
    assert line["line_id"]
    assert line["voice_speaker_id"] == "spk_a"
    lines = list_lines(gap_ctx)
    assert len(lines) == 1
    delete_line(gap_ctx, line["line_id"])
    assert list_lines(gap_ctx) == []
