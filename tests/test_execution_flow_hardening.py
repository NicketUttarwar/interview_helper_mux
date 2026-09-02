"""Execution flow hardening — exec_5174 VO contract and homunculus recovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.recovery_controller import (
    classify_error_class,
    playbook_vo_contract_repair,
    playbook_vo_seated_coverage,
)
from interview_mux.run_context import RunContext
from interview_mux.stages.edl_narrative_audit import compact_vo_coverage
from interview_mux.vo_contract import (
    ensure_gap_line_on_air,
    gap_line_requires_synthesis,
    repair_vo_contract_drift,
    validate_vo_contract,
)
from run_fixtures import patch_executions_root, write_fixture_vo_wav


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("exec_flow_hardening", create=True)


def _write_exec_5174_plan(ctx: RunContext) -> None:
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_019"],
                    "omitted_line_ids": [],
                    "orientation_id": "vo_layup_seg_019",
                }
            }
        },
    )


def _gap_line_019() -> dict:
    return {
        "line_id": "vo_layup_seg_019",
        "delivery": "synthesize",
        "required": True,
        "skipped_optional": True,
        "gap_type": "layup",
        "placement": "before",
        "text": "Before we dive in, one quick setup.",
        "targets_segment_id": "seg_019",
    }


def _mark_homunculus(ctx: RunContext) -> None:
    def patch(meta: dict) -> None:
        meta["homunculus_version"] = "0.1.0"

    ctx.mutate_run_meta(patch)


def _synth_wav_for_019(ctx: RunContext) -> None:
    repair_vo_contract_drift(ctx)
    wav = ctx.final_path("vo_pickup", "synthesized", "vo_layup_seg_019.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    write_fixture_vo_wav(wav)
    from interview_mux.vo_synthesis_audit import record_synthesis

    record_synthesis(
        ctx,
        ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0],
        backend="chatterbox",
        out_wav=wav,
        ref_audio="understanding/speaker_samples/spk_0.wav",
    )


def test_vo_overlap_seated_always_synth(ctx: RunContext) -> None:
    _write_exec_5174_plan(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line_019()]},
    )
    seated = {"vo_layup_seg_019"}
    line = ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    assert gap_line_requires_synthesis(line, seated)
    assert validate_vo_contract(ctx)
    changed = repair_vo_contract_drift(ctx)
    assert "vo_layup_seg_019" in changed
    fixed = ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    assert not fixed.get("skipped_optional")
    assert not fixed.get("air_script_omit")


def test_exec_5174_acceptance_coverage_after_repair(ctx: RunContext) -> None:
    _write_exec_5174_plan(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line_019()]},
    )
    repair_vo_contract_drift(ctx)
    wav = ctx.final_path("vo_pickup", "synthesized", "vo_layup_seg_019.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    write_fixture_vo_wav(wav)
    from interview_mux.vo_synthesis_audit import record_synthesis

    record_synthesis(
        ctx,
        ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0],
        backend="chatterbox",
        out_wav=wav,
        ref_audio="understanding/speaker_samples/spk_0.wav",
    )
    rows = {r["line_id"]: r for r in compact_vo_coverage(ctx)}
    assert rows["vo_layup_seg_019"]["coverage"] in {"rendered", "wav_stale"}


def test_homunculus_recovery_vo_coverage_class(ctx: RunContext) -> None:
    error_class = classify_error_class(
        "edl_narrative_audit",
        RuntimeError("VO coverage not rendered: ['vo_layup_seg_019']"),
    )
    assert error_class == "vo_seated_coverage"
    _write_exec_5174_plan(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line_019()]},
    )
    ctx.mark_done("vo_synthesize", force=True)
    artifacts = playbook_vo_seated_coverage(ctx)
    assert artifacts
    assert not ctx.is_done("vo_synthesize")
    fixed = ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    assert not fixed.get("skipped_optional")


def test_ensure_gap_line_on_air_clears_skip_flags() -> None:
    row = ensure_gap_line_on_air(
        {
            "line_id": "vo_layup_seg_019",
            "skipped_optional": True,
            "air_script_omit": True,
            "required": True,
        }
    )
    assert "skipped_optional" not in row
    assert "air_script_omit" not in row


def test_delivery_epoch_locked_blocks_structural_invalidate(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import stamp_delivery_epoch

    stamp_delivery_epoch(ctx, phase_a_sealed_at="2026-09-02T00:00:00+00:00")
    ctx.mark_done("nugget_layup_compose", force=True)
    ctx.mark_done("edl", force=True)
    ctx.write_json("master/assembly.wav", {"placeholder": True})
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.fingerprints_match_checkpoint",
        lambda _ctx: False,
    )
    from interview_mux.homunculus.agenda import invalidate_downstream

    with pytest.raises(RuntimeError, match="delivery epoch locked"):
        invalidate_downstream(ctx, "nugget_layup_compose")


def test_playbook_vo_contract_repair_unmarks_stages(ctx: RunContext) -> None:
    _write_exec_5174_plan(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line_019()]},
    )
    ctx.mark_done("vo_line_adjudicate", force=True)
    ctx.mark_done("vo_synthesize", force=True)
    playbook_vo_contract_repair(ctx)
    assert not ctx.is_done("vo_line_adjudicate")
    assert not ctx.is_done("vo_synthesize")


def test_seed_front_pin_rejects_jump(ctx: RunContext) -> None:
    from interview_mux.delivery_guardrails import filter_delivery_candidates
    from interview_mux.homunculus.agenda import constrain_conductor_to_seed_front

    remaining = ["mix", "mmaudio_sfx", "vo_synthesize"]
    legal = filter_delivery_candidates(ctx, remaining)
    assert "mix" not in legal
    assert "mmaudio_sfx" not in legal
    pinned = constrain_conductor_to_seed_front(ctx, "delivery", remaining)
    assert pinned
    assert pinned[0] != "mix"


def test_chapter_contiguity_at_ranking() -> None:
    from interview_mux.narrative_qc import _validate_chapters

    selection = {
        "ordered_segment_ids": ["s1", "s2", "s3", "s4"],
        "chapters": [{"title": "Act I", "segment_ids": ["s3", "s1"]}],
    }
    errors = _validate_chapters(selection)
    assert any("contiguous" in err for err in errors)


def test_dispatch_preflight_blocks_expensive(ctx: RunContext) -> None:
    from interview_mux.homunculus.runtime import dispatch_stage
    from interview_mux.stage_input_checks import StageInputError

    ctx.mark_done("vo_line_adjudicate", force=True)
    with pytest.raises(StageInputError):
        dispatch_stage(ctx, "edl_narrative_audit", lambda: None)


def test_dispatch_preflight_blocks_mix_without_assembly(ctx: RunContext) -> None:
    from interview_mux.homunculus.runtime import dispatch_stage
    from interview_mux.stage_input_checks import StageInputError

    with pytest.raises(StageInputError):
        dispatch_stage(ctx, "mix", lambda: None)


def test_validate_vo_contract_post_layup(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.vo_contract import sync_vo_contract_after_layup

    monkeypatch.setattr(
        "interview_mux.air_script.air_script_enabled",
        lambda: False,
    )
    _write_exec_5174_plan(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line_019()]},
    )
    remaining = sync_vo_contract_after_layup(ctx)
    fixed = ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    assert not fixed.get("skipped_optional")
    assert not any("skip/omit" in issue for issue in remaining)


def test_recovery_transient_retry_budget(ctx: RunContext) -> None:
    from datetime import datetime, timezone

    from interview_mux.recovery_controller import (
        _append_action,
        budget_exhausted,
        handle_stage_failure,
        recovery_attempt_budget,
        signature_key,
    )

    sig = signature_key("edl_narrative_audit", "vo_seated_coverage")
    assert recovery_attempt_budget("vo_seated_coverage") == 3
    for _ in range(2):
        _append_action(
            ctx,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "signature": sig,
                "playbook_id": "vo_seated_coverage",
                "status": "recovered",
            },
        )
    assert not budget_exhausted(ctx, sig, "vo_seated_coverage")
    result = handle_stage_failure(
        ctx,
        "edl_narrative_audit",
        RuntimeError("VO coverage not rendered: ['vo_layup_seg_019']"),
    )
    assert result.status in {"recovered", "escalate"}
    _append_action(
        ctx,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signature": sig,
            "playbook_id": "vo_seated_coverage",
            "status": "recovered",
        },
    )
    assert budget_exhausted(ctx, sig, "vo_seated_coverage")


def test_stage_done_coherence_after_invalidate(ctx: RunContext) -> None:
    from interview_mux.homunculus.agenda import invalidate_downstream

    ctx.mark_done("vo_synthesize", force=True)
    ctx.mark_done("edl", force=True)
    invalidate_downstream(ctx, "nugget_layup_compose")
    assert not ctx.is_done("vo_synthesize")
    assert not ctx.is_done("edl")
    assert ctx.path("operator/invalidation_log.jsonl").is_file()


def test_gui_runner_preflight_blocks_expensive(ctx: RunContext) -> None:
    from interview_mux.web.runner import JobRunner

    ctx.mark_done("vo_line_adjudicate", force=True)
    runner = JobRunner()
    with pytest.raises(RuntimeError, match="vo_synthesize"):
        runner._preflight_delivery_dispatch(
            ctx,
            stage="edl_narrative_audit",
            from_stage=None,
            stage_ids=["edl_narrative_audit"],
        )


def test_exec_5174_recovery_unblocks_audit(ctx: RunContext) -> None:
    """Exec_5174 class bug: seated layup skipped → audit blocks → recovery clears path."""
    from interview_mux.recovery_controller import handle_stage_failure
    from interview_mux.stage_input_checks import collect_stage_input_issues

    _mark_homunculus(ctx)
    _write_exec_5174_plan(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line_019()]},
    )
    ctx.mark_done("vo_synthesize", force=True)
    ctx.mark_done("edl_narrative_audit", force=True)

    result = handle_stage_failure(
        ctx,
        "edl_narrative_audit",
        RuntimeError("VO coverage not rendered: ['vo_layup_seg_019']"),
    )
    assert result.status in {"recovered", "escalate"}
    assert result.resume_stage in {"vo_synthesize", "edl_narrative_audit", "edl"}
    assert not ctx.is_done("vo_synthesize")

    gap = ctx.read_json("understanding/gap_report.json")
    if not (gap.get("interviewer_lines") or []):
        ctx.write_json(
            "understanding/gap_report.json",
            {"interviewer_lines": [_gap_line_019()]},
        )
    _synth_wav_for_019(ctx)
    ctx.mark_done("vo_synthesize", force=True)
    issues = collect_stage_input_issues(ctx, "edl_narrative_audit")
    assert not issues


def test_exec_5174_driver_continues_past_vo_coverage(ctx: RunContext) -> None:
    from interview_mux.operator_gates import should_stamp_needs_operator

    reason = "VO coverage not rendered: ['vo_layup_seg_019']"
    meta = {"partial_auto": True, "homunculus_version": "0.1.0"}
    assert not should_stamp_needs_operator("edl_narrative_audit", reason, meta=meta)


def test_stage_input_preflight_recovery_h0c(ctx: RunContext) -> None:
    from interview_mux.recovery_controller import handle_stage_failure
    from interview_mux.stage_input_checks import collect_stage_input_issues, require_stage_inputs

    _mark_homunculus(ctx)
    _write_exec_5174_plan(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line_019()]},
    )
    ctx.mark_done("vo_synthesize", force=True)

    handle_stage_failure(
        ctx,
        "edl_narrative_audit",
        RuntimeError("VO coverage not rendered: ['vo_layup_seg_019']"),
    )
    _synth_wav_for_019(ctx)
    ctx.mark_done("vo_synthesize", force=True)
    require_stage_inputs(ctx, "edl_narrative_audit")
    assert not collect_stage_input_issues(ctx, "edl_narrative_audit")


def test_unified_recovery_counters_r12c(ctx: RunContext) -> None:
    from datetime import datetime, timezone

    from interview_mux.identical_failures import failure_signature_by_class, read_identical_failures
    from interview_mux.recovery_controller import (
        _append_action,
        attempt_count,
        signature_key,
    )

    sig = signature_key("edl_narrative_audit", "vo_seated_coverage")
    _append_action(
        ctx,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signature": sig,
            "playbook_id": "vo_seated_coverage",
            "status": "recovered",
        },
    )
    assert attempt_count(ctx, sig) == 1
    halt_sig = failure_signature_by_class(
        failed_stage="edl_narrative_audit",
        error_class="vo_seated_coverage",
    )
    row = (read_identical_failures(ctx).get("signatures") or {}).get(halt_sig) or {}
    assert int(row.get("count") or 0) == 1


def test_delivery_filter_rejects_blocked_stages(ctx: RunContext) -> None:
    from interview_mux.delivery_guardrails import filter_delivery_candidates

    for sid in ("mix", "mmaudio_sfx", "junction_snip_qa", "master_finalize"):
        legal_one = filter_delivery_candidates(ctx, [sid])
        assert sid not in legal_one, f"{sid} should be blocked without prerequisites"
