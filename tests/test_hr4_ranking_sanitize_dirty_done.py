"""HR-4: W1 sanitize must not mute-mark when heal refuses.

Selection-order and gap-report sanitize re-raise and self-pin.
Do not start a run. HF-4 air-contract, HF-5 Pass-2 pin, F1 restamp stay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_sanitize.gap_report import run_gap_report_sanitize
from interview_mux.artifact_sanitize.selection import run_selection_order_sanitize
from interview_mux.artifact_sanitize.types import SanitizeResult
from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    incompleteness_resume_stage,
    parse_resume_stage_from_reason,
    producer_pin_for_token,
    stage_artifact_incompleteness,
)
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx, mark_done_raw, minimal_gap_line, minimal_gap_report

_SEL_REASON = (
    "selection still unsanitary — resume selection_order_sanitize: fragment_depth"
)
_GAP_REASON = "gap still unsanitary — resume gap_report_sanitize: dup_line"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hr4_w1_sanitize")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _plant_selection(ctx: RunContext) -> dict:
    sel = {"ordered_segment_ids": ["seg_001"], "excluded_segment_ids": []}
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    return sel


def _plant_gap(ctx: RunContext) -> None:
    _plant_selection(ctx)
    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_a",
            text="Line A",
            targets_segment_id="seg_001",
            delivery="synthesize",
        )
    )
    meta = dict(gap.get("_meta") or {}) if isinstance(gap.get("_meta"), dict) else {}
    meta["producer_stage"] = "gap_report_sanitize"
    gap["_meta"] = meta
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)


def _refuse(reason: str):
    def _fn(_ctx, stage, *, force=False):
        return {
            "stage": stage,
            "marked": False,
            "unmarked": False,
            "refused": True,
            "reason": reason,
        }

    return _fn


def test_hr4_selection_heal_refuse_does_not_mark(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    sel = _plant_selection(ctx)
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.selection.sanitize_master_selection",
        lambda _ctx, doc: SanitizeResult(
            doc=dict(doc or sel), ok=True, artifact_rel="master/selection.json"
        ),
    )
    monkeypatch.setattr(
        "interview_mux.air_order_boundary.commit_selection_mutation",
        lambda _ctx, doc, **_k: dict(doc),
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.heal_or_refuse_mark",
        _refuse(_SEL_REASON),
    )
    with pytest.raises(RuntimeError, match="selection_order_sanitize"):
        run_selection_order_sanitize(ctx)
    assert not ctx.is_done("selection_order_sanitize")


def test_hr4_gap_heal_refuse_does_not_mark(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_gap(ctx)
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.gap_report.sanitize_gap_report",
        lambda _ctx, doc: SanitizeResult(
            doc=dict(doc or {}),
            ok=True,
            artifact_rel="understanding/gap_report.json",
        ),
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.heal_or_refuse_mark",
        _refuse(_GAP_REASON),
    )
    with pytest.raises(RuntimeError, match="gap_report_sanitize"):
        run_gap_report_sanitize(ctx)
    assert not ctx.is_done("gap_report_sanitize")


def test_hr4_selection_sanitary_run_marks(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    sel = _plant_selection(ctx)
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.selection.sanitize_master_selection",
        lambda _ctx, doc: SanitizeResult(
            doc=dict(doc or sel), ok=True, artifact_rel="master/selection.json"
        ),
    )
    monkeypatch.setattr(
        "interview_mux.air_order_boundary.commit_selection_mutation",
        lambda _ctx, doc, **_k: dict(doc),
    )
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.registry.selection_sanitary_errors",
        lambda _ctx: [],
    )
    run_selection_order_sanitize(ctx)
    assert ctx.is_done("selection_order_sanitize")


def test_hr4_gap_sanitary_run_marks(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_gap(ctx)
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.gap_report.sanitize_gap_report",
        lambda _ctx, doc: SanitizeResult(
            doc=dict(doc or {}),
            ok=True,
            artifact_rel="understanding/gap_report.json",
        ),
    )
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.registry.gap_sanitary_errors",
        lambda _ctx: [],
    )
    run_gap_report_sanitize(ctx)
    assert ctx.is_done("gap_report_sanitize")


def test_hr4_incompleteness_pins_selection_sanitize_not_edl(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_selection(ctx)
    mark_done_raw(ctx, "selection_order_sanitize")
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.registry.selection_sanitary_errors",
        lambda _ctx: ["fragment_depth"],
    )
    reason = stage_artifact_incompleteness(ctx, "selection_order_sanitize")
    assert reason is not None
    assert "selection still unsanitary" in reason
    assert parse_resume_stage_from_reason(reason) == "selection_order_sanitize"
    assert parse_resume_stage_from_reason(reason) != "edl"
    assert producer_pin_for_token(reason, ctx=ctx) == "selection_order_sanitize"
    assert incompleteness_resume_stage(ctx, "selection_order_sanitize") == (
        "selection_order_sanitize"
    )
    assert seed_stage_complete(ctx, "selection_order_sanitize") is False
    nav = heal_navigate(ctx, error=reason, stage="selection_order_sanitize")
    assert nav["from_stage"] == "selection_order_sanitize"
    assert nav["from_stage"] != "edl"


def test_hr4_incompleteness_pins_gap_sanitize_not_edl(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_gap(ctx)
    mark_done_raw(ctx, "gap_report_sanitize")
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.registry.gap_sanitary_errors",
        lambda _ctx: ["dup_line"],
    )
    reason = stage_artifact_incompleteness(ctx, "gap_report_sanitize")
    assert reason is not None
    assert "gap still unsanitary" in reason
    assert parse_resume_stage_from_reason(reason) == "gap_report_sanitize"
    assert parse_resume_stage_from_reason(reason) != "edl"
    assert parse_resume_stage_from_reason(reason) != "selection_framing_apply"
    assert producer_pin_for_token(reason, ctx=ctx) == "gap_report_sanitize"
    assert incompleteness_resume_stage(ctx, "gap_report_sanitize") == (
        "gap_report_sanitize"
    )
    assert seed_stage_complete(ctx, "gap_report_sanitize") is False
    nav = heal_navigate(ctx, error=reason, stage="gap_report_sanitize")
    assert nav["from_stage"] == "gap_report_sanitize"
    assert nav["from_stage"] != "edl"
    assert nav["from_stage"] != "selection_framing_apply"
