"""High gaps are covered or demoted before the compose barrier (ISSUES 134, exec_002)."""

from __future__ import annotations

from pathlib import Path

from tests.run_fixtures import isolated_run_ctx


def _evals(*high: str) -> dict:
    return {
        "evaluations": [
            {
                "segment_id": sid,
                "self_explanatory": False,
                "gap_type": "missing_question",
                "secondary_gap_type": "missing_callback",
                "listener_confusion": "An isolated reply with no question.",
                "severity": "high",
                "recommended_framing": "question",
                "candidate_for_summary": False,
                "supports_ranking_exclude": False,
                "duplicate_claim_cluster": "",
            }
            for sid in high
        ]
    }


def test_seed_replaces_inactive_row_with_same_id(tmp_path: Path) -> None:
    from interview_mux.high_gap_vo import (
        seed_uncovered_high_gaps_deterministic,
        targeted_segment_ids,
    )

    ctx = isolated_run_ctx(tmp_path, "exec_seed_same_id")
    ctx.write_json("understanding/gap_evaluations.json", _evals("seg_021"), skip_handoff=True)
    report = {
        "interviewer_lines": [
            {
                "line_id": "vo_seed_seg_021",
                "text": "What changes if we stay with this idea a beat longer?",
                "targets_segment_id": "seg_021",
                "skipped_optional": True,
                "air_script_omit": True,
            }
        ]
    }
    applied: list[dict] = []
    added = seed_uncovered_high_gaps_deterministic(ctx, report, applied=applied)
    rows = [r for r in report["interviewer_lines"] if r.get("line_id") == "vo_seed_seg_021"]
    assert added == 1
    assert len(rows) == 1, "a second row under the same id lets dedupe keep the inactive one"
    assert not rows[0].get("skipped_optional") and not rows[0].get("air_script_omit")
    assert "seg_021" in targeted_segment_ids(report["interviewer_lines"], ctx)


def test_uncovered_high_gap_is_demoted_before_the_barrier(tmp_path: Path, monkeypatch) -> None:
    """Seeding that does not land must not leave a gap neither covered nor demoted."""
    from interview_mux.stage_completion import _high_gap_unframed_incompleteness
    from interview_mux.stages import gaps
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    ctx = isolated_run_ctx(tmp_path, "exec_seed_settle")
    ctx.write_json("understanding/gap_evaluations.json", _evals("seg_021"), skip_handoff=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "gaps": []},
        skip_handoff=True,
    )
    # Stand-in for the repairs that take a fresh seed back off air.
    monkeypatch.setattr(
        "interview_mux.recovery_controller.playbook_high_gap_unframed", lambda _ctx: []
    )
    assert _high_gap_unframed_incompleteness(ctx, "gap_framing_compose")
    enter_stage_staging("gap_framing_compose")
    try:
        gaps._seed_uncovered_high_gaps_before_heal(ctx)
        assert not _high_gap_unframed_incompleteness(ctx, "gap_framing_compose")
        evals = ctx.read_json("understanding/gap_evaluations.json")
        row = evals["evaluations"][0]
        assert row["severity"] == "medium"
        assert str(row.get("severity_demotion_reason", "")).startswith("high_gap_seat:repair")
    finally:
        exit_stage_staging()
