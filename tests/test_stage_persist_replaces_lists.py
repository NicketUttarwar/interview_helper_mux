"""A stage's persisted output replaces lists on disk instead of unioning them (ISSUES 162).

exec_016: (1) a re-audit that cleared its blocking issue kept the previous
pass's issue through the merge, so the verdict stayed "fail", the commit
barrier refused every pass, and edl_narrative_audit hit the thrash cap;
(2) a failed narrative_arc_plan attempt and its retry were unioned into one
plan with ch_05 twice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_completeness import (
    FULL_REPLACE_STAGE_ARTIFACTS,
    UNION_LIST_STAGE_ARTIFACTS,
    _deep_merge,
    merge_artifact,
)


def test_replace_lists_takes_the_new_list_even_when_empty() -> None:
    base = {"rows": [1, 2], "keep": "x", "_meta": {"a": 1}}
    out = _deep_merge(base, {"rows": [], "_meta": {"b": 2}}, replace_lists=True)
    assert out["rows"] == []
    assert out["keep"] == "x"
    assert out["_meta"] == {"a": 1, "b": 2}


def test_default_merge_still_unions_for_direct_callers() -> None:
    out = _deep_merge({"rows": [1]}, {"rows": [2]})
    assert out["rows"] == [1, 2]
    assert _deep_merge({"rows": [1]}, {"rows": []})["rows"] == [1]


def test_reaudit_that_clears_its_complaint_lands_clean() -> None:
    first = {
        "verdict": "fail",
        "blocking_issues": [{"code": "selected_continuity_broken", "issue": "old seam"}],
        "warnings": [],
        "repair_attempted": True,
        "repair_notes": [{"action": "x"}],
        "_meta": {"repairs": [{"action": "demote_restore_excluded_blocking"}]},
    }
    second = {
        "verdict": "warn",
        "blocking_issues": [],
        "warnings": [{"code": "selected_continuity_broken", "issue": "demoted"}],
        "_meta": {"producer_stage": "edl_narrative_audit"},
    }
    assert ("master/edl_narrative_audit.json", "edl_narrative_audit") in FULL_REPLACE_STAGE_ARTIFACTS
    out = merge_artifact("master/edl_narrative_audit.json", first, second, full_replace=True)
    assert out["verdict"] == "warn"
    assert out["blocking_issues"] == []
    assert "repair_notes" not in out and "repair_attempted" not in out
    assert out["_meta"]["repairs"] and out["_meta"]["producer_stage"] == "edl_narrative_audit"


def test_narrative_retry_does_not_keep_the_failed_attempts_chapters() -> None:
    failed = {"chapters": [{"chapter_id": "ch_05", "title": "A"}, {"chapter_id": "ch_06", "title": "B"}]}
    retry = {"chapters": [{"chapter_id": "ch_05", "title": "C"}]}
    out = merge_artifact("master/narrative_plan.json", failed, retry, replace_lists=True)
    assert out["chapters"] == [{"chapter_id": "ch_05", "title": "C"}]


def test_resplit_keeps_the_union_until_it_has_a_row_floor() -> None:
    assert ("segments/boundaries.json", "boundary_topic_resplit") in UNION_LIST_STAGE_ARTIFACTS


def test_make_stage_persist_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.artifact_completeness import make_stage_persist
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_persist_replace")
    seen: list[dict] = []

    def _fake_write(c, rel, data, **kw):
        from interview_mux.artifact_completeness import merge_artifact as _m

        existing = {"chapters": [{"chapter_id": "ch_01"}, {"chapter_id": "ch_02"}]}
        seen.append(_m(rel, existing, data, replace_lists=kw["replace_lists"], full_replace=kw["full_replace"]))

    monkeypatch.setattr("interview_mux.artifact_writes.write_validated_artifact", _fake_write)
    make_stage_persist("master/narrative_plan.json", "narrative_arc_plan")(ctx, {"chapters": [{"chapter_id": "ch_09"}]})
    assert seen[-1]["chapters"] == [{"chapter_id": "ch_09"}]
