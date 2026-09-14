"""HV-5: unattended Chatterbox G1 stays automation_pending.

vo_unsanitary / coverage exhaust must not stamp needs_operator or flip G1
to hard_block. Do not start a run. HV-2 / HV-4 / F2 stay closed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.operator_gate_view import g1_journey_clear, resolve_g1_vo_gate
from interview_mux.operator_gates import should_stamp_needs_operator
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


def _gap_line(**overrides: object) -> dict:
    base = {
        "line_id": "vo_line_1",
        "delivery": "synthesize",
        "severity": "medium",
        "targets_segment_id": "seg_1",
        "gap_type": "missing_framing",
        "text": "Can you expand on that?",
        "placement": "after",
    }
    base.update(overrides)
    return base


def _chatterbox_meta(**extra: object) -> dict:
    meta = {
        "homunculus_version": "0.1.0",
        "partial_auto": True,
        "partial_auto_driver_active": True,
        "gap_framing_enabled": True,
        "gap_vo_delivery": "chatterbox",
        "voice_reference_approved_at": "2026-01-01T00:00:00Z",
    }
    meta.update(extra)
    return meta


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr("interview_mux.v2.config.v2_g1_optional", lambda: True)
    return isolated_run_ctx(tmp_path, "hv5_g1")


def test_hv5_vo_unsanitary_does_not_stamp_unattended_010() -> None:
    meta = {"partial_auto": True, "homunculus_version": "0.1.0"}
    assert (
        should_stamp_needs_operator(
            "vo_synthesize",
            "vo_unsanitary — resume vo_synthesize: seated_bind_stale:vo_line_1",
            meta=meta,
        )
        is False
    )
    assert (
        should_stamp_needs_operator(
            "g1_vo_pickup",
            "vo_unsanitary — resume vo_synthesize: seated_bind_stale:vo_line_1",
            meta=meta,
        )
        is False
    )
    assert should_stamp_needs_operator(
        "sound_design_plan",
        "sdp_unsanitary — resume sound_design_plan: theme missing",
        meta=meta,
    )


def test_hv5_vo_unsanitary_still_stamps_manual() -> None:
    assert should_stamp_needs_operator(
        "vo_synthesize",
        "vo_unsanitary — resume vo_synthesize: seated_bind_stale:vo_line_1",
        meta={},
    )


def test_hv5_coverage_exhaust_does_not_stamp() -> None:
    meta = {"partial_auto": True, "homunculus_version": "0.1.0"}
    assert (
        should_stamp_needs_operator(
            "edl_narrative_audit",
            "still_missing: ['vo_line_1']",
            meta=meta,
        )
        is False
    )
    assert (
        should_stamp_needs_operator(
            "vo_synthesize",
            "VO coverage not rendered",
            meta=meta,
        )
        is False
    )


def test_hv5_stale_g1_stamp_loses_to_chatterbox(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line()]},
        skip_handoff=True,
    )
    meta = _chatterbox_meta(
        needs_operator=True,
        needs_operator_stage="g1_vo_pickup",
        needs_operator_reason="vo_unsanitary — resume vo_synthesize: seated_bind_stale",
    )
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    view = resolve_g1_vo_gate(ctx, None, meta)
    assert view.severity == "automation_pending"
    assert view.operator_must_act is False
    assert g1_journey_clear(ctx, meta) is True


def test_hv5_record_line_keeps_hard_block(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line(delivery="record", severity="high")]},
        skip_handoff=True,
    )
    meta = _chatterbox_meta(
        needs_operator=True,
        needs_operator_stage="g1_vo_pickup",
        needs_operator_reason="G1 VO pickup needs operator action",
    )
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    view = resolve_g1_vo_gate(ctx, None, meta)
    assert view.severity == "hard_block"
    assert view.operator_must_act is True
    assert g1_journey_clear(ctx, meta) is False


def test_hv5_vo_unsanitary_fresh_mtime_still_halts(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.identical_failures import is_fail_key_halted, upsert_fail_key

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda _ctx: (False, ""),
    )
    dest = ctx.run_dir / "mastering" / "vo_synthesize.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text('{"lines":[]}\n', encoding="utf-8")
    row = upsert_fail_key(
        ctx,
        "vo_synthesize:vo_unsanitary",
        3,
        failed_stage="vo_synthesize",
        producer="mastering/vo_synthesize.json",
        reason="vo_unsanitary — resume vo_synthesize: seated_bind_stale:vo_line_1",
        resume_attempted="vo_synthesize",
    )
    assert row["halt"] is True
    assert row.get("esr_softened") is not True
    assert is_fail_key_halted(ctx, "vo_synthesize:vo_unsanitary") is True


def test_hv5_coverage_exhaust_fresh_mtime_still_halts(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.identical_failures import is_fail_key_halted, upsert_fail_key

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda _ctx: (False, ""),
    )
    dest = ctx.run_dir / "mastering" / "vo_synthesize.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text('{"lines":[]}\n', encoding="utf-8")
    row = upsert_fail_key(
        ctx,
        "vo_synthesize:coverage_exhaust",
        3,
        failed_stage="vo_synthesize",
        producer="mastering/vo_synthesize.json",
        reason="VO coverage not rendered — still_missing: ['vo_line_1']",
        resume_attempted="vo_synthesize",
    )
    assert row["halt"] is True
    assert row.get("esr_softened") is not True
    assert is_fail_key_halted(ctx, "vo_synthesize:coverage_exhaust") is True
