"""selection_framing_apply S1–S5 simplify pins (high-risk audit MODE=fix)."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from interview_mux.artifact_ownership import gap_report_body_text_changed, row_for_path
from interview_mux.gap_framing import stamp_gap_seats_to_selection
from interview_mux.refinement_passes import APPLY_REL, run_selection_framing_apply
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, minimal_gap_line, minimal_gap_report


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "sfa_s1_s5")


def test_s1_apply_source_has_no_body_heal_chain() -> None:
    from interview_mux import refinement_passes as mod

    src = inspect.getsource(mod.run_selection_framing_apply)
    assert "stamp_gap_seats_to_selection" in src
    assert "restore_layup_lines" not in src
    assert "ensure_episode_orientation" not in src
    assert "avoid_clone_voice_adjacency" not in src
    assert "drop_contiguous_light_bridge_lines" not in src
    assert "rebase_gap_lines_to_selection" not in src


def test_s1_stamp_gap_retarget_or_omit_never_rewrites_text() -> None:
    prior = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_a",
            text="Keep this spoken copy intact.",
            targets_segment_id="seg_gone",
            supports_segment_ids=["seg_001"],
        ),
        minimal_gap_line(
            line_id="vo_b",
            text="Omit seat only — same text.",
            targets_segment_id="seg_also_gone",
        ),
    )
    stamped, notes = stamp_gap_seats_to_selection(prior, ["seg_001"])
    assert notes
    assert gap_report_body_text_changed(prior, stamped) is False
    by_id = {
        str(ln.get("line_id")): ln
        for ln in (stamped.get("interviewer_lines") or [])
        if isinstance(ln, dict)
    }
    assert by_id["vo_a"]["targets_segment_id"] == "seg_001"
    assert by_id["vo_b"].get("skipped_optional") is True
    assert by_id["vo_b"].get("air_script_omit") is True
    assert by_id["vo_b"]["text"] == "Omit seat only — same text."


def test_s2_selection_producer_allow_and_commit_only() -> None:
    from interview_mux import refinement_passes as mod

    row = row_for_path("master/selection.json")
    assert row is not None
    assert "selection_framing_apply" in row.producers
    src = inspect.getsource(mod.run_selection_framing_apply)
    assert "commit_selection_mutation" in src
    assert 'producer="selection_framing_apply"' in src
    assert 'mode="post_framing"' not in src
    assert "write_sanitize_audit" not in src
    assert "sanitize_master_selection" not in src


def test_s3_decide_pass_skip_no_mutate(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "excluded_segment_ids": [],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(
            minimal_gap_line(
                line_id="vo_a",
                text="Hello.",
                targets_segment_id="seg_001",
            )
        ),
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.gate_seat_mutation",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "interview_mux.refinement_passes.decide_pass",
        lambda *a, **k: {"status": "skip", "reason_code": "agenda"},
    )
    monkeypatch.setattr(
        "interview_mux.gap_framing.ranking_exclude_segment_ids",
        lambda _ctx: {"seg_002"},
    )
    run_selection_framing_apply(ctx)
    doc = ctx.read_json(APPLY_REL)
    assert doc.get("skipped") is True
    assert doc.get("skip_reason") == "agenda"
    assert ctx.is_done("selection_framing_apply")
    sel = ctx.read_json("master/selection.json")
    assert sel["ordered_segment_ids"] == ["seg_001", "seg_002"]
    gap = ctx.read_json("understanding/gap_report.json")
    assert (gap.get("interviewer_lines") or [])[0]["targets_segment_id"] == "seg_001"


def test_s4_no_hosted_floor_persist_in_apply() -> None:
    from interview_mux import refinement_passes as mod

    src = inspect.getsource(mod.run_selection_framing_apply)
    assert "identify_hosted_vo_floor" not in src


def test_s5_keeps_framing_exclude_in_apply_not_deleted() -> None:
    """Safest S5: leave lattice #6 excludes here — do not delete_path / peel to ranking."""
    from interview_mux import refinement_passes as mod

    src = inspect.getsource(mod.run_selection_framing_apply)
    assert "covered_by_framing_vo" in src
    assert "ranking_exclude_segment_ids" in src
