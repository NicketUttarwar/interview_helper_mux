"""S9: nugget_layup_compose is sole post-authority gap_report body (text) writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_ownership import (
    AuthorityDenied,
    GAP_REPORT_SOLE_BODY_WRITER,
    assert_gap_report_body_sole_writer,
    row_for_path,
    write_permitted,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, minimal_gap_line, minimal_gap_report


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "layup_s9_sole")


def test_gap_report_catalog_body_writers_only(ctx: RunContext) -> None:
    row = row_for_path("understanding/gap_report.json")
    assert row is not None
    assert row.producers == ("gap_framing_compose", "nugget_layup_compose")
    assert row.authoritative == GAP_REPORT_SOLE_BODY_WRITER
    for foreign in (
        "selection_framing_apply",
        "vo_line_adjudicate",
        "gap_report_sanitize",
        "vo_synthesize",
    ):
        assert foreign not in row.producers


def test_stamp_stages_may_write_omit_delivery(ctx: RunContext) -> None:
    ok, reason = write_permitted(
        ctx,
        "understanding/gap_report.json",
        "vo_synthesize",
        fields=("interviewer_lines[].delivery",),
    )
    assert ok is True, reason


def test_post_authority_foreign_text_mutate_refused(ctx: RunContext) -> None:
    prior = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_layup_seg_001",
            text="Prior layup unlock about the guest stakes.",
            targets_segment_id="seg_001",
        )
    )
    prior["nugget_layup_authority"] = True
    new = {
        **prior,
        "interviewer_lines": [
            {
                **(prior["interviewer_lines"][0]),
                "text": "Foreign rewrite of the layup body copy.",
            }
        ],
    }
    with pytest.raises(AuthorityDenied) as caught:
        assert_gap_report_body_sole_writer(
            ctx,
            stage_key="vo_line_adjudicate",
            prior=prior,
            new=new,
        )
    assert caught.value.suggested_owner == "nugget_layup_compose"
    assert "gap_body_sole_writer" in str(caught.value)


def test_layup_may_rewrite_body_after_authority(ctx: RunContext) -> None:
    prior = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_layup_seg_001",
            text="Prior layup unlock about the guest stakes.",
            targets_segment_id="seg_001",
        )
    )
    prior["nugget_layup_authority"] = True
    new = {
        **prior,
        "interviewer_lines": [
            {
                **(prior["interviewer_lines"][0]),
                "text": "Layup republish of the unlock line.",
            }
        ],
    }
    assert_gap_report_body_sole_writer(
        ctx,
        stage_key="nugget_layup_compose",
        prior=prior,
        new=new,
    )


def test_empty_stage_key_refuses_existing_body_rewrite(ctx: RunContext) -> None:
    prior = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_layup_seg_001",
            text="Prior layup unlock about the guest stakes.",
            targets_segment_id="seg_001",
        )
    )
    new = {
        **prior,
        "interviewer_lines": [
            {
                **(prior["interviewer_lines"][0]),
                "text": "Nameless rewrite of existing body copy.",
            }
        ],
    }
    with pytest.raises(AuthorityDenied) as caught:
        assert_gap_report_body_sole_writer(
            ctx, stage_key="", prior=prior, new=new
        )
    assert "empty_stage_key" in str(caught.value)


def test_empty_stage_key_explicit_ops_role_may_rewrite(ctx: RunContext) -> None:
    prior = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_layup_seg_001",
            text="Prior layup unlock about the guest stakes.",
            targets_segment_id="seg_001",
        )
    )
    new = {
        **prior,
        "interviewer_lines": [
            {
                **(prior["interviewer_lines"][0]),
                "text": "Ops fixture rewrite of body copy.",
            }
        ],
    }
    assert_gap_report_body_sole_writer(
        ctx, stage_key="", prior=prior, new=new, role="ops"
    )


def test_empty_stage_key_initial_persist_allowed(ctx: RunContext) -> None:
    new = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_1",
            text="First persist of a host line.",
            targets_segment_id="seg_001",
        )
    )
    assert_gap_report_body_sole_writer(ctx, stage_key="", prior=None, new=new)
