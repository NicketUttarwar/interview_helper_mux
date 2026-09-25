"""HF-5: Pass-2 must not force-mark after re-dirtying W1 gap.

Pin the Pass-2 writer, never gap_report_sanitize while W3 freeze is stamped.
Courtesy rewrite is skipped when it would dirty (3A).
Do not start a run. HF-1 hollow, HF-3 seams, HF-4 W3 mute, F3 skip/omit, HR-4 stay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta
from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.heal_routing import classify_heal_error
from interview_mux.refinement_passes import (
    APPLY_REL,
    RECOMPOSE_REL,
    courtesy_rewrite_lines_if_sanitary,
    run_selection_framing_apply,
)
from interview_mux.run_context import RunContext
from interview_mux.seat_authority import stamp_soft_seat_freeze
from interview_mux.stage_completion import (
    incompleteness_resume_stage,
    parse_resume_stage_from_reason,
    pass2_gap_heal_resume_stage,
    producer_pin_for_token,
    stage_artifact_incompleteness,
)
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx, mark_done_raw, minimal_gap_line, minimal_gap_report

_GAP_KEYS = ["interviewer_lines", "gaps", "opening_orientation"]


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hf5_pass2_gap")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _stamp_gap(lines: list[dict]) -> dict:
    return stamp_sanitize_meta(
        minimal_gap_report(*lines),
        ok=True,
        source="gap_report_sanitize",
        content_keys=_GAP_KEYS,
    )


def _plant_selection(ctx: RunContext) -> None:
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001"], "excluded_segment_ids": []},
        skip_handoff=True,
    )


def _plant_unsanitary_gap(ctx: RunContext) -> None:
    """Bypass one-writer admit so W1 errors stay on disk."""
    prev = getattr(ctx, "_one_writer_raw", False)
    ctx._one_writer_raw = True
    try:
        ctx.write_json(
            "understanding/gap_report.json",
            {
                "interviewer_lines": [minimal_gap_line(line_id="vo_a")],
                "gaps": "unsanitary",
            },
            skip_handoff=True,
        )
    finally:
        ctx._one_writer_raw = prev


def _plant_vo_synth_sidecar(ctx: RunContext) -> None:
    ctx.write_json("mastering/vo_synthesize.json", {"ok": True}, skip_handoff=True)


def test_hf5_apply_unsanitary_gap_refuses_mark_and_pins_writer(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HF-5: activate path that finishes on dirty gap refuses done and pins apply."""
    _plant_selection(ctx)
    _plant_unsanitary_gap(ctx)
    monkeypatch.setattr(
        "interview_mux.seat_authority.gate_seat_mutation",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "interview_mux.refinement_passes.decide_pass",
        lambda *a, **k: {"status": "activate", "reason_code": "hf5"},
    )
    monkeypatch.setattr(
        "interview_mux.gap_framing.ranking_exclude_segment_ids",
        lambda _ctx: set(),
    )

    with pytest.raises(RuntimeError, match="resume selection_framing_apply"):
        run_selection_framing_apply(ctx)

    assert not ctx.is_done("selection_framing_apply")
    doc = ctx.read_json(APPLY_REL)
    assert doc.get("refused") is True
    assert doc.get("reason") == "gap_unsanitary"
    reason = stage_artifact_incompleteness(ctx, "selection_framing_apply")
    assert reason is not None
    assert "gap_unsanitary" in reason
    assert parse_resume_stage_from_reason(reason) == "selection_framing_apply"
    assert parse_resume_stage_from_reason(reason) != "gap_report_sanitize"
    assert seed_stage_complete(ctx, "selection_framing_apply") is False
    nav = heal_navigate(ctx, error=reason, stage="selection_framing_apply")
    assert nav["from_stage"] == "selection_framing_apply"
    assert nav["from_stage"] != "gap_report_sanitize"


def test_hf5_raw_done_unmarked_while_gap_dirty(ctx: RunContext) -> None:
    ctx.write_json(
        APPLY_REL,
        {"skipped": False, "refused": False, "reason": "applied"},
        skip_handoff=True,
    )
    _plant_unsanitary_gap(ctx)
    mark_done_raw(ctx, "selection_framing_apply")
    reason = stage_artifact_incompleteness(ctx, "selection_framing_apply")
    assert reason is not None
    assert "gap_unsanitary" in reason
    assert "resume selection_framing_apply" in reason
    assert seed_stage_complete(ctx, "selection_framing_apply") is False
    assert incompleteness_resume_stage(ctx, "selection_framing_apply") == (
        "selection_framing_apply"
    )


def test_hf5_w3_freeze_pins_pass2_not_w1(ctx: RunContext) -> None:
    ctx.write_json(
        APPLY_REL,
        {
            "skipped": False,
            "refused": True,
            "reason": "gap_unsanitary",
            "errors": ["gap_needs_sanitize:dedupe_line_id"],
        },
        skip_handoff=True,
    )
    _plant_unsanitary_gap(ctx)
    _plant_vo_synth_sidecar(ctx)
    stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    reason = stage_artifact_incompleteness(ctx, "vo_synthesize")
    assert reason is not None
    assert "gap_unsanitary" in reason
    assert parse_resume_stage_from_reason(reason) == "selection_framing_apply"
    assert parse_resume_stage_from_reason(reason) != "gap_report_sanitize"
    assert pass2_gap_heal_resume_stage(
        ctx, error=reason, stage="vo_synthesize"
    ) == "selection_framing_apply"
    assert producer_pin_for_token("gap_unsanitary", ctx=ctx) == "selection_framing_apply"
    assert incompleteness_resume_stage(ctx, "vo_synthesize") == "selection_framing_apply"
    nav = heal_navigate(ctx, error=reason, stage="vo_synthesize")
    assert nav["from_stage"] == "selection_framing_apply"
    assert nav["from_stage"] != "gap_report_sanitize"
    route = classify_heal_error(reason, ctx, stage="vo_synthesize")
    assert route is not None
    assert route.from_stage == "selection_framing_apply"


def test_hf5_no_pass2_without_freeze_still_pins_w1(ctx: RunContext) -> None:
    _plant_unsanitary_gap(ctx)
    _plant_vo_synth_sidecar(ctx)
    assert pass2_gap_heal_resume_stage(ctx, error="gap_unsanitary") is None
    assert producer_pin_for_token("gap_unsanitary", ctx=ctx) == "gap_report_sanitize"
    reason = stage_artifact_incompleteness(ctx, "vo_synthesize")
    assert reason is not None
    assert parse_resume_stage_from_reason(reason) == "gap_report_sanitize"
    nav = heal_navigate(ctx, error=reason, stage="vo_synthesize")
    assert nav["from_stage"] == "gap_report_sanitize"


def test_hf5_courtesy_skips_rewrite_that_dirties_w1(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    interrupt = minimal_gap_line(
        line_id="vo_open",
        text="Wait a second — what happened next?",
        targets_segment_id="seg_001",
    )
    interrupt["prior_impact_beat"] = True
    interrupt["line_category"] = "framing_question"
    other = minimal_gap_line(
        line_id="vo_b",
        text="Keep that beat in mind — what claim follows?",
        targets_segment_id="seg_001",
    )
    candidate = _stamp_gap([interrupt, other])
    monkeypatch.setattr(
        "interview_mux.gap_vo_prior_context.courtesy_seed_text",
        lambda *a, **k: str(other["text"]),
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_prior_context.build_prior_native_context",
        lambda **k: {"prior_impact_beat": True},
    )
    out = courtesy_rewrite_lines_if_sanitary(
        ctx,
        candidate,
        list(candidate["interviewer_lines"]),
        ordered=["seg_001"],
        by_id={},
        chapters=None,
        settings={},
    )
    assert out[0]["text"] == interrupt["text"]
    assert out[0]["text"] != other["text"]


def test_hf5_courtesy_keeps_rewrite_when_sanitary(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    interrupt = minimal_gap_line(
        line_id="vo_open",
        text="Wait a second — what happened next?",
        targets_segment_id="seg_001",
    )
    interrupt["prior_impact_beat"] = True
    interrupt["line_category"] = "framing_question"
    candidate = _stamp_gap([interrupt])
    rewritten = "What changed next in that stretch?"
    monkeypatch.setattr(
        "interview_mux.gap_vo_prior_context.courtesy_seed_text",
        lambda *a, **k: rewritten,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_prior_context.build_prior_native_context",
        lambda **k: {"prior_impact_beat": True},
    )
    out = courtesy_rewrite_lines_if_sanitary(
        ctx,
        candidate,
        list(candidate["interviewer_lines"]),
        ordered=[],
        by_id={},
        chapters=None,
        settings={},
    )
    assert out[0]["text"] == rewritten


def test_hf5_recompose_refuse_sidecar_pins_recompose(ctx: RunContext) -> None:
    ctx.write_json(
        RECOMPOSE_REL,
        {
            "skipped": False,
            "refused": True,
            "reason": "gap_unsanitary",
            "errors": ["gap_needs_sanitize:dedupe_line_id"],
        },
        skip_handoff=True,
    )
    _plant_unsanitary_gap(ctx)
    reason = stage_artifact_incompleteness(ctx, "gap_framing_recompose")
    assert reason is not None
    assert parse_resume_stage_from_reason(reason) == "gap_framing_recompose"
    nav = heal_navigate(ctx, error=reason, stage="gap_framing_recompose")
    assert nav["from_stage"] == "gap_framing_recompose"
    assert nav["from_stage"] != "gap_report_sanitize"
