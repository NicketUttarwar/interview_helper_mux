"""A repeated line_id keeps the live row, not the skipped or omitted one (ISSUES 134 class).

exec_002: the high-gap seeder appended a live ``vo_seed_seg_021`` beside an
omitted row with the same id; both gap-report dedupes kept the first (omitted)
copy, the gap was neither covered nor demoted, and the class cap halted the run.
The seeder was fixed; these are the two dedupes every writer goes through.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx


def _line(lid: str, *, omitted: bool, text: str) -> dict:
    row = {
        "line_id": lid,
        "delivery": "synthesize",
        "gap_type": "framing",
        "targets_segment_id": "seg_021",
        "placement": "before",
        "text": text,
    }
    if omitted:
        row.update({"skipped_optional": True, "air_script_omit": True})
    return row


LINES = [
    _line("vo_seed_seg_021", omitted=True, text="An older framing."),
    _line("vo_seed_seg_021", omitted=False, text="Here is what that means for patients."),
]


def test_repairs_dedupe_keeps_the_live_copy() -> None:
    from interview_mux.artifact_repairs import _dedupe_interviewer_lines

    out = {"interviewer_lines": [dict(r) for r in LINES]}
    _dedupe_interviewer_lines(out, applied=[])
    assert len(out["interviewer_lines"]) == 1
    assert not out["interviewer_lines"][0].get("skipped_optional")


def test_repairs_dedupe_still_keeps_the_first_when_both_alike() -> None:
    from interview_mux.artifact_repairs import _dedupe_interviewer_lines

    rows = [_line("vo_a", omitted=False, text="First."), _line("vo_a", omitted=False, text="Second.")]
    out = {"interviewer_lines": rows}
    _dedupe_interviewer_lines(out, applied=[])
    assert [r["text"] for r in out["interviewer_lines"]] == ["First."]


def test_sanitizer_dedupe_keeps_the_live_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.artifact_sanitize.gap_report import sanitize_gap_report

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_dedupe_live")
    result = sanitize_gap_report(ctx, {"interviewer_lines": [dict(r) for r in LINES]})
    doc = getattr(result, "doc", None) or getattr(result, "data", None) or result[0]
    rows = [r for r in doc["interviewer_lines"] if r.get("line_id") == "vo_seed_seg_021"]
    assert len(rows) == 1 and not rows[0].get("skipped_optional")
