"""HF-1: Pass-2 stages must not hollow force-done.

Freeze/skip write a stub then mark. Missing selection refuses.
Skip-copy is enough for recompose. Freeze+EDL does not raw-mark.
Do not start a run. Do not reopen HF-2 / HF-3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.refinement_flow_integrity import SKIP_COPY_REL
from interview_mux.refinement_passes import APPLY_REL, RECOMPOSE_REL
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    stage_artifact_incompleteness,
)
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "hf1_pass2")


def test_hf1_raw_done_without_sidecar_incomplete(ctx: RunContext) -> None:
    for sid, rel in (
        ("refinement_agenda", "understanding/refinement_agenda.json"),
        ("gap_framing_recompose", RECOMPOSE_REL),
        ("selection_framing_apply", APPLY_REL),
    ):
        mark_done_raw(ctx, sid)
        reason = stage_artifact_incompleteness(ctx, sid)
        assert reason is not None, sid
        assert rel in reason or "pending" in reason
        assert seed_stage_complete(ctx, sid) is False
        out = heal_or_refuse_mark(ctx, sid)
        assert out.get("unmarked") is True or not ctx.is_done(sid)


def test_hf1_apply_missing_selection_refuses_done(ctx: RunContext) -> None:
    from interview_mux.refinement_passes import run_selection_framing_apply

    run_selection_framing_apply(ctx)
    assert not ctx.is_done("selection_framing_apply")
    doc = ctx.read_json(APPLY_REL)
    assert doc.get("refused") is True
    assert doc.get("reason") == "missing_selection"
    assert seed_stage_complete(ctx, "selection_framing_apply") is False


def test_sfa_b2_invalid_selection_refuses_seed_complete(ctx: RunContext) -> None:
    """SFA-B2: invalid selection refuse stub never seed-completes."""
    import json

    from interview_mux.refinement_passes import run_selection_framing_apply

    path = ctx.path("master", "selection.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(["not-a-dict"]), encoding="utf-8")
    run_selection_framing_apply(ctx)
    doc = ctx.read_json(APPLY_REL)
    assert doc.get("refused") is True
    assert doc.get("reason") == "invalid_selection"
    assert not ctx.is_done("selection_framing_apply")
    assert seed_stage_complete(ctx, "selection_framing_apply") is False
    reason = stage_artifact_incompleteness(ctx, "selection_framing_apply")
    assert reason is not None
    assert "refused" in reason


def test_sfa_b1_contract_execute_lifecycle_honest_outputs() -> None:
    """SFA-B1: no llm_execute; no draft/plan/skip_copy outputs."""
    from interview_mux.stage_contract import load_contract

    contract = load_contract("selection_framing_apply")
    assert contract is not None
    assert contract.tier == "deterministic"
    assert "llm_execute" not in contract.lifecycle_phases
    assert "execute" in contract.lifecycle_phases
    out_paths = {o.path for o in contract.outputs}
    assert "understanding/selection_framing_apply.json" in out_paths
    assert "understanding/gap_report.json" in out_paths
    assert "understanding/gap_report.draft.json" not in out_paths
    assert "understanding/refinement_plan.json" not in out_paths
    assert "understanding/refinement_skip_copy.json" not in out_paths


def test_hf1_apply_freeze_writes_stub_and_marks(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import seat_authority as sa
    from interview_mux.refinement_passes import run_selection_framing_apply

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda _ctx: ["vo_layup_seg_001"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda _ctx: [],
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_001",
                    "delivery": "synthesize",
                    "text": "Hello.",
                    "required": True,
                }
            ]
        },
        skip_handoff=True,
    )
    sa.stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    run_selection_framing_apply(ctx)
    doc = ctx.read_json(APPLY_REL)
    assert doc.get("skipped") is True
    assert doc.get("skip_reason") == "seat_freeze"
    assert doc.get("refused") is not True
    assert ctx.is_done("selection_framing_apply")
    assert seed_stage_complete(ctx, "selection_framing_apply") is True


def test_hf1_recompose_skip_copy_completes_without_primary(ctx: RunContext) -> None:
    ctx.write_json(
        SKIP_COPY_REL,
        {"reason": "pass2_skipped", "line_count": 0},
        skip_handoff=True,
    )
    mark_done_raw(ctx, "gap_framing_recompose")
    assert stage_artifact_incompleteness(ctx, "gap_framing_recompose") is None
    assert seed_stage_complete(ctx, "gap_framing_recompose") is True


def test_hf1_freeze_edl_writes_stub_not_raw(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import seed_policy
    from interview_mux import seat_authority as sa

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda _ctx: ["vo_layup_seg_001"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda _ctx: [],
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_001",
                    "delivery": "synthesize",
                    "text": "Hello.",
                    "required": True,
                }
            ]
        },
        skip_handoff=True,
    )
    mark_done_raw(ctx, "edl")
    sa.stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    sealed = seed_policy.seal_freeze_sticky_stages(ctx)
    assert "selection_framing_apply" in sealed
    assert "gap_framing_recompose" in sealed
    apply_doc = ctx.read_json(APPLY_REL)
    assert apply_doc.get("skip_reason") == "hard_freeze_edl"
    rec_doc = ctx.read_json(RECOMPOSE_REL)
    assert rec_doc.get("skip_reason") == "hard_freeze_edl"
    assert ctx.is_done("selection_framing_apply")
    assert ctx.is_done("gap_framing_recompose")


def test_hf1_refuse_sidecar_stays_incomplete_after_raw_done(ctx: RunContext) -> None:
    ctx.write_json(
        APPLY_REL,
        {"skipped": False, "refused": True, "reason": "missing_selection"},
        skip_handoff=True,
    )
    mark_done_raw(ctx, "selection_framing_apply")
    assert seed_stage_complete(ctx, "selection_framing_apply") is False
    out = heal_or_refuse_mark(ctx, "selection_framing_apply")
    assert out.get("unmarked") is True or not ctx.is_done("selection_framing_apply")
