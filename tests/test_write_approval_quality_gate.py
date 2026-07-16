"""Write approval must not clobber / outrank quality gates (fix D)."""

from __future__ import annotations

from interview_mux.gui_job_reconcile import pause_job_for_write_approval
from interview_mux.run_context import RunContext
from interview_mux.write_staging import (
    WriteApprovalPending,
    after_stage_write_check,
    enter_stage_staging,
    set_llm_gate,
    write_pending_content,
)


def test_after_stage_write_check_skips_when_llm_gate_open(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: True,
    )
    ctx = RunContext(create=True)
    enter_stage_staging("content_context")
    write_pending_content(
        ctx,
        "content_context",
        "understanding/content_brief.json",
        data={"thesis": "x", "topics": [{"name": "t", "summary": "s"}]},
    )
    set_llm_gate(ctx, "content_context", message="LLM stage gate (content_context): failed")
    # Must not raise WriteApprovalPending when gate is open.
    after_stage_write_check(ctx, "content_context")
    job = ctx.read_json("gui_job.json")
    assert job.get("status") == "gate"


def test_after_stage_write_check_skips_incomplete_critical(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: True,
    )
    ctx = RunContext(create=True)
    enter_stage_staging("boundary_detection")
    write_pending_content(
        ctx,
        "boundary_detection",
        "segments/boundaries.json",
        data={"boundaries": []},
    )
    assert not ctx.is_done("boundary_detection")
    after_stage_write_check(ctx, "boundary_detection")  # no WriteApprovalPending


def test_after_stage_write_check_offers_save_for_acceptable_critical(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "interview_mux.first_try.write_approval_deferred",
        lambda: False,
    )
    ctx = RunContext(create=True)
    enter_stage_staging("content_context")
    write_pending_content(
        ctx,
        "content_context",
        "understanding/content_brief.json",
        data={
            "thesis": "A long enough thesis for the content brief stage.",
            "topics": [
                {
                    "name": "Topic one",
                    "summary": "Summary with enough detail for validation.",
                    "segment_ids": [],
                    "confidence": 0.9,
                }
            ],
            "key_claims": [],
        },
    )
    assert not ctx.is_done("content_context")
    with __import__("pytest").raises(WriteApprovalPending) as exc:
        after_stage_write_check(ctx, "content_context")
    assert exc.value.stage_id == "content_context"


def test_pause_job_preserves_clarification_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.write_json(
        "gui_job.json",
        {
            "status": "needs_clarification",
            "stage": "content_context",
            "message": "fix issues first",
        },
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.is_stage_gate_blocked",
        lambda _ctx, _sid: True,
    )
    pause_job_for_write_approval(
        ctx, WriteApprovalPending("content_context", ["understanding/content_brief.json"])
    )
    job = ctx.read_json("gui_job.json")
    assert job.get("status") == "needs_clarification"
