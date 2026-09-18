"""0G: hollow present≠sanitary for shared-path sanitize / air_script producers."""

from __future__ import annotations

import pytest

from interview_mux.homunculus.agenda import stage_outputs_present
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED", "1")
    return isolated_run_ctx(tmp_path, "hollow_seed")


def test_selection_order_sanitize_hollow_file_not_present(ctx) -> None:
    # Bare empty selection must not seed-complete sanitize.
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(
        ctx.path("master/selection.json"),
        {"ordered_segment_ids": [], "_meta": {"producer_stage": "full_master_ranking"}},
    )
    assert stage_outputs_present(ctx, "selection_order_sanitize") is False


def test_gap_report_sanitize_hollow_file_not_present(ctx) -> None:
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(
        ctx.path("understanding/gap_report.json"),
        {"interviewer_lines": []},
    )
    # Empty gap may or may not be sanitary; presence must track incompleteness/False on error.
    present = stage_outputs_present(ctx, "gap_report_sanitize")
    try:
        from interview_mux.stage_completion import stage_artifact_incompleteness

        incomplete = stage_artifact_incompleteness(ctx, "gap_report_sanitize")
        assert present == (incomplete is None)
    except Exception:
        assert present is False


def test_air_script_compose_uses_pass_a_incompleteness(ctx) -> None:
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(
        ctx.path("mastering/mastering_plan.json"),
        {"version": 1, "_meta": {"producer_stage": "mastering_plan_confirm"}},
    )
    present = stage_outputs_present(ctx, "air_script_compose")
    try:
        from interview_mux.stage_completion import stage_artifact_incompleteness

        incomplete = stage_artifact_incompleteness(ctx, "air_script_compose")
        assert present == (incomplete is None)
    except Exception:
        assert present is False


def test_edl_hollow_file_not_present(ctx) -> None:
    """Bare hollow EDL must not seed-complete edl (present≠sanitary)."""
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(
        ctx.path("master/edl.json"),
        {
            "version": 1,
            "ordered_segment_ids": [],
            "clips": [],
            "timeline_duration_ms": 0,
        },
    )
    assert stage_outputs_present(ctx, "edl") is False


def test_grs_b2_empty_stub_incomplete_when_framing_yes(ctx, monkeypatch) -> None:
    """GRS-B2: sanitize empty seed must not complete while framing Yes."""
    from interview_mux.artifact_sanitize.gap_report import run_gap_report_sanitize
    from interview_mux.stage_completion import stage_artifact_incompleteness

    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda _ctx: True,
    )
    # No gap_report on disk → sanitize seeds empty stub then refuses done.
    with pytest.raises(RuntimeError, match="empty stub|framing"):
        run_gap_report_sanitize(ctx)
    assert not ctx.is_done("gap_report_sanitize")
    assert ctx.artifact_exists("understanding/gap_report.json")
    reason = stage_artifact_incompleteness(ctx, "gap_report_sanitize")
    assert reason is not None
    assert "empty stub" in reason or "framing" in reason


def test_grs_b2_empty_stub_ok_when_framing_no(ctx, monkeypatch) -> None:
    """Framing No / skip: empty sanitary stub may complete."""
    from interview_mux.artifact_sanitize.gap_report import run_gap_report_sanitize

    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda _ctx: False,
    )
    run_gap_report_sanitize(ctx)
    assert ctx.is_done("gap_report_sanitize")
