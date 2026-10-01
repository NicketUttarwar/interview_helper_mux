"""The acceptance record counts standing errors; recovered ones stay listed (ISSUES 114)."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.orchestrator import _standing_error_lines


def _log(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def test_an_error_whose_stage_finishes_later_is_recovered(tmp_path: Path) -> None:
    log = _log(
        tmp_path / "gui_log.jsonl",
        [
            {"level": "error", "stage": "vo_line_adjudicate", "message": "Prerequisite stage not complete"},
            {"level": "info", "stage": "vo_line_adjudicate", "message": "Stage start: vo_line_adjudicate"},
            {"level": "success", "stage": "vo_line_adjudicate", "message": "Stage finished: vo_line_adjudicate"},
            {"level": "error", "stage": "mix", "message": "boom"},
            {"level": "error", "stage": "", "message": "no stage"},
        ],
    )
    standing, recovered = _standing_error_lines(log)
    assert recovered == ["[vo_line_adjudicate] Prerequisite stage not complete"]
    assert standing == ["[mix] boom", "[] no stage"]


def test_a_finish_before_the_error_does_not_count(tmp_path: Path) -> None:
    log = _log(
        tmp_path / "gui_log.jsonl",
        [
            {"level": "success", "stage": "mix", "message": "Stage finished: mix"},
            {"level": "error", "stage": "mix", "message": "later failure"},
        ],
    )
    standing, recovered = _standing_error_lines(log)
    assert standing == ["[mix] later failure"] and recovered == []


def test_fail_open_commit_logs_a_warning_not_an_error() -> None:
    import interview_mux.llm_simple as m

    src = Path(m.__file__).read_text(encoding="utf-8")
    block = src[src.find("committed = _try_fail_open_partial(") :]
    block = block[: block.find("last_schema_errors = [msg]")]
    assert "committed fail-open" in block
    assert block.find('level="warning"') < block.find('level="error"')
