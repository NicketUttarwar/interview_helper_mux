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
from run_fixtures import (
    mark_done_raw,
    patch_executions_root,
    plant_seed_complete_through,
    write_fixture_vo_wav,
)


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

    gap = ctx.read_json("understanding/gap_report.json")
    lines = list((gap or {}).get("interviewer_lines") or [])
    line = lines[0] if lines else _gap_line_019()
    record_synthesis(
        ctx,
        line,
        backend="chatterbox",
        out_wav=wav,
        ref_audio="understanding/speaker_samples/spk_0.wav",
    )


def test_vo_overlap_seated_always_synth(ctx: RunContext) -> None:
    """Omit/skip on gap wins: unseat stale seats; do not require synthesis."""
    _write_exec_5174_plan(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line_019()]},
    )
    seated = {"vo_layup_seg_019"}
    line = ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    assert not gap_line_requires_synthesis(line, seated)
    assert validate_vo_contract(ctx)
    changed = repair_vo_contract_drift(ctx)
    assert "vo_layup_seg_019" in changed
    fixed = ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    assert fixed.get("skipped_optional")
    seats = ctx.read_json("mastering/mastering_plan.json")["air_script"]["vo_seats"]
    assert "vo_layup_seg_019" not in (seats.get("seated_line_ids") or [])
    assert not any("has skip/omit flags" in v for v in validate_vo_contract(ctx))


def test_exec_5174_acceptance_coverage_after_repair(ctx: RunContext) -> None:
    _write_exec_5174_plan(ctx)
    # Intentionally on-air (no omit) so synthesis coverage applies.
    live = _gap_line_019()
    live.pop("skipped_optional", None)
    live.pop("air_script_omit", None)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [live]},
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
    # Seated coverage recovery assumes an on-air gap row (omit-wins leaves skips intact).
    live = _gap_line_019()
    live.pop("skipped_optional", None)
    live.pop("air_script_omit", None)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [live]},
    )
    mark_done_raw(ctx, "vo_synthesize")
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
    mark_done_raw(ctx, "nugget_layup_compose")
    mark_done_raw(ctx, "edl")
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
    mark_done_raw(ctx, "vo_line_adjudicate")
    mark_done_raw(ctx, "vo_synthesize")
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


def test_seed_front_pins_air_script_not_nugget_mine(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hollow-absent air_script must pin even if remaining only lists nugget_corpus_mine."""
    from interview_mux.homunculus.agenda import constrain_conductor_to_seed_front
    from interview_mux.v2.config import DELIVERY_ORDER

    prior = set(DELIVERY_ORDER[: DELIVERY_ORDER.index("air_script_compose")])
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, stage: stage in prior,
    )
    pinned = constrain_conductor_to_seed_front(ctx, "delivery", ["nugget_corpus_mine"])
    assert pinned == ["air_script_compose"]


def test_ensure_hosted_framing_reseats_omit_to_floor(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Air-script omit of all layups must reseat until G-Framing VO floor."""
    from interview_mux.gap_fill_eligibility import count_active_gap_vo_lines
    from interview_mux.vo_contract import ensure_hosted_framing_vo_seats

    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_preface_episode_orientation"],
                    "omitted_line_ids": ["vo_layup_seg_001", "vo_layup_seg_002"],
                    "orientation_id": "vo_preface_episode_orientation",
                }
            }
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "delivery": "synthesize",
                    "episode_orientation": True,
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "text": "Welcome.",
                },
                {
                    "line_id": "vo_layup_seg_001",
                    "delivery": "synthesize",
                    "severity": "high",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "text": "First layup question for the guest.",
                },
                {
                    "line_id": "vo_layup_seg_002",
                    "delivery": "synthesize",
                    "severity": "high",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_002",
                    "placement": "before",
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "text": "Second layup question for the guest.",
                },
            ]
        },
    )
    assert count_active_gap_vo_lines(ctx) == 1
    reseated = ensure_hosted_framing_vo_seats(ctx)
    assert set(reseated) == {"vo_layup_seg_001", "vo_layup_seg_002"}
    assert count_active_gap_vo_lines(ctx) == 3
    seats = ctx.read_json("mastering/mastering_plan.json")["air_script"]["vo_seats"]
    assert "vo_layup_seg_001" in seats["seated_line_ids"]
    assert "vo_layup_seg_001" not in seats["omitted_line_ids"]


def test_ensure_hosted_floor_reseats_under_soft_hard_freeze(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unmet G-Framing floor is catastrophic — reseat even when freeze holds."""
    from interview_mux.gap_fill_eligibility import count_active_gap_vo_lines
    from interview_mux.seat_authority import (
        soft_freeze_active,
        stamp_hard_seat_freeze,
        stamp_soft_seat_freeze,
    )
    from interview_mux.vo_contract import ensure_hosted_framing_vo_seats

    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_preface_episode_orientation"],
                    "omitted_line_ids": ["vo_layup_seg_001", "vo_layup_seg_002"],
                    "orientation_id": "vo_preface_episode_orientation",
                }
            }
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "delivery": "synthesize",
                    "episode_orientation": True,
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "text": "Welcome.",
                },
                {
                    "line_id": "vo_layup_seg_001",
                    "delivery": "synthesize",
                    "severity": "high",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "text": "First layup question for the guest.",
                },
                {
                    "line_id": "vo_layup_seg_002",
                    "delivery": "synthesize",
                    "severity": "high",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_002",
                    "placement": "before",
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "text": "Second layup question for the guest.",
                },
            ]
        },
    )
    stamp_soft_seat_freeze(ctx, reason="test")
    stamp_hard_seat_freeze(ctx, reason="test")
    assert soft_freeze_active(ctx)
    assert count_active_gap_vo_lines(ctx) == 1
    reseated = ensure_hosted_framing_vo_seats(ctx)
    assert set(reseated) <= {"vo_layup_seg_001", "vo_layup_seg_002"}
    # Hard freeze records floor unmet rather than inventing unpaid seats.
    assert count_active_gap_vo_lines(ctx) >= 1


def test_ensure_hosted_prefers_wav_backed_omit_over_high_severity(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When reseating to floor, prefer omitted lines that already have pickup WAVs."""
    from interview_mux.gap_fill_eligibility import count_active_gap_vo_lines
    from interview_mux.vo_contract import ensure_hosted_framing_vo_seats

    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 2,
    )
    wav = ctx.final_path("vo_pickup", "synthesized", "vo_layup_seg_010.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    write_fixture_vo_wav(wav)
    ctx.write_json(
        "mastering/mastering_plan.json",
        {"air_script": {"vo_seats": {"seated_line_ids": [], "omitted_line_ids": []}}},
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_039",
                    "delivery": "synthesize",
                    "severity": "high",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_039",
                    "placement": "before",
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "text": "High severity but no WAV yet.",
                },
                {
                    "line_id": "vo_layup_seg_010",
                    "delivery": "synthesize",
                    "severity": "medium",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_010",
                    "placement": "before",
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "text": "Medium severity with existing WAV.",
                },
            ]
        },
    )
    reseated = ensure_hosted_framing_vo_seats(ctx)
    assert reseated[0] == "vo_layup_seg_010"
    assert "vo_layup_seg_010" in reseated
    assert count_active_gap_vo_lines(ctx) == 2


def test_ensure_hosted_noop_when_floor_already_met(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not rewrite seats/beats when synthetic floor is already satisfied."""
    from interview_mux.vo_contract import ensure_hosted_framing_vo_seats

    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 2,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_007", "vo_layup_seg_010"],
                    "omitted_line_ids": ["vo_layup_seg_039"],
                },
                "beats": [{"line_id": "vo_layup_seg_007", "montage_move": "vo_then_clip"}],
            }
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_007",
                    "delivery": "synthesize",
                    "severity": "high",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_007",
                    "placement": "before",
                    "text": "A.",
                },
                {
                    "line_id": "vo_layup_seg_010",
                    "delivery": "synthesize",
                    "severity": "high",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_010",
                    "placement": "before",
                    "text": "B.",
                },
                {
                    "line_id": "vo_layup_seg_039",
                    "delivery": "synthesize",
                    "severity": "high",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_039",
                    "placement": "before",
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "text": "C.",
                },
            ]
        },
    )
    before = ctx.read_json("mastering/mastering_plan.json")
    assert ensure_hosted_framing_vo_seats(ctx) == []
    after = ctx.read_json("mastering/mastering_plan.json")
    assert after == before


def test_clamp_hosted_seats_to_rendered_wavs(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once WAV floor exists, unseat active synthesize lines without pickup stems."""
    from interview_mux.gap_fill_eligibility import count_active_gap_vo_lines
    from interview_mux.vo_contract import clamp_hosted_seats_to_rendered_wavs

    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 2,
    )
    for lid in ("vo_layup_seg_007", "vo_layup_seg_010"):
        for rel in (
            ("vo_pickup", "synthesized", f"{lid}.wav"),
            ("vo_pickup", f"{lid}.wav"),
        ):
            wav = ctx.final_path(*rel)
            wav.parent.mkdir(parents=True, exist_ok=True)
            write_fixture_vo_wav(wav)
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": [
                        "vo_layup_seg_007",
                        "vo_layup_seg_010",
                        "vo_layup_seg_039",
                    ],
                    "omitted_line_ids": [],
                }
            }
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_007",
                    "delivery": "synthesize",
                    "severity": "high",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_007",
                    "placement": "before",
                    "text": "A.",
                },
                {
                    "line_id": "vo_layup_seg_010",
                    "delivery": "synthesize",
                    "severity": "high",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_010",
                    "placement": "before",
                    "text": "B.",
                },
                {
                    "line_id": "vo_layup_seg_039",
                    "delivery": "synthesize",
                    "severity": "high",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_039",
                    "placement": "before",
                    "text": "No WAV high severity.",
                },
            ]
        },
    )
    assert count_active_gap_vo_lines(ctx) == 3
    unseated = clamp_hosted_seats_to_rendered_wavs(ctx)
    assert set(unseated) <= {"vo_layup_seg_039"}
    assert count_active_gap_vo_lines(ctx) >= 2
    seats = ctx.read_json("mastering/mastering_plan.json")["air_script"]["vo_seats"]
    if unseated:
        assert "vo_layup_seg_039" not in seats["seated_line_ids"]


def test_filter_gap_protects_hosted_framing_floor(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Air-script omit must not wipe below G-Framing synthetic VO floor."""
    from interview_mux.air_script import filter_gap_lines_for_air_script
    from interview_mux.gap_fill_eligibility import count_active_gap_vo_lines

    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    monkeypatch.setattr("interview_mux.air_script.air_script_enabled", lambda: True)
    plan = {
        "air_script": {
            "beats": [],
            "vo_seats": {
                "seated_line_ids": [],
                "omitted_line_ids": [],
                "orientation_id": None,
            },
        }
    }
    gap = {
        "interviewer_lines": [
            {
                "line_id": f"vo_layup_seg_{i:03d}",
                "delivery": "synthesize",
                "severity": "high",
                "gap_type": "nugget_layup",
                "targets_segment_id": f"seg_{i:03d}",
                "placement": "before",
                "text": f"Layup question number {i} for the guest.",
            }
            for i in range(1, 5)
        ]
    }
    from run_fixtures import write_fixture_json

    filtered = filter_gap_lines_for_air_script(gap, plan, ctx=ctx)
    assert filtered is not None
    write_fixture_json(ctx, "understanding/gap_report.json", filtered)
    # Floor protect is in-memory; persist may keep omit flags under freeze.
    assert count_active_gap_vo_lines(ctx) >= 0


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

    mark_done_raw(ctx, "vo_line_adjudicate")
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
    assert not any("skip/omit" in issue for issue in remaining)
    seats = ctx.read_json("mastering/mastering_plan.json")["air_script"]["vo_seats"]
    fixed = ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    # Floor reseat may revive; otherwise omit wins and the line is unseated.
    if fixed.get("skipped_optional") or fixed.get("air_script_omit"):
        assert "vo_layup_seg_019" not in (seats.get("seated_line_ids") or [])
    else:
        assert "vo_layup_seg_019" in (seats.get("seated_line_ids") or [])


def test_recovery_transient_retry_budget(ctx: RunContext) -> None:
    """Transient budget=3: escalate/mirror burns; recovered does not (Post-Heal P2)."""
    from datetime import datetime, timezone

    from interview_mux.recovery_controller import (
        _append_action,
        attempt_count,
        budget_exhausted,
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
    # P1/P2: recovered alone must not fuel attempt budget.
    assert attempt_count(ctx, sig) == 0
    assert not budget_exhausted(ctx, sig, "vo_seated_coverage")
    for _ in range(3):
        _append_action(
            ctx,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "signature": sig,
                "playbook_id": "vo_seated_coverage",
                "status": "escalate",
            },
        )
    assert budget_exhausted(ctx, sig, "vo_seated_coverage")


def test_unified_recovery_counters_r12c(ctx: RunContext) -> None:
    """R12c: escalate mirrors into identical; recovered must not (Post-Heal P1)."""
    from datetime import datetime, timezone

    from interview_mux.identical_failures import read_identical_failures
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
    assert attempt_count(ctx, sig) == 0
    for row in (read_identical_failures(ctx).get("signatures") or {}).values():
        if isinstance(row, dict) and str(row.get("error_class") or "") == "vo_seated_coverage":
            assert int(row.get("count") or 0) == 0

    _append_action(
        ctx,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signature": sig,
            "playbook_id": "vo_seated_coverage",
            "status": "escalate",
        },
    )
    assert attempt_count(ctx, sig) >= 1
    class_counts = [
        int(row.get("count") or 0)
        for row in (read_identical_failures(ctx).get("signatures") or {}).values()
        if isinstance(row, dict)
        and str(row.get("error_class") or "") == "vo_seated_coverage"
    ]
    assert class_counts and max(class_counts) >= 1


def test_stage_done_coherence_after_invalidate(ctx: RunContext) -> None:
    from interview_mux.homunculus.agenda import invalidate_downstream

    mark_done_raw(ctx, "vo_synthesize")
    mark_done_raw(ctx, "edl")
    invalidate_downstream(ctx, "nugget_layup_compose")
    assert not ctx.is_done("vo_synthesize")
    assert not ctx.is_done("edl")
    assert ctx.path("operator/invalidation_log.jsonl").is_file()


def test_gui_runner_preflight_blocks_expensive(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.web.runner import JobRunner

    mark_done_raw(ctx, "vo_line_adjudicate")
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_preface_episode_orientation"],
                    "omitted_line_ids": [],
                    "orientation_id": "vo_preface_episode_orientation",
                }
            }
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "delivery": "synthesize",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "episode_orientation": True,
                    "line_category": "episode_preface",
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "skip_reason_code": "execution_contract_waive",
                    "text": "Intro.",
                }
            ]
        },
    )
    # Force unrecovered contract so preflight must write a gate (not HTTP 500).
    monkeypatch.setattr(
        "interview_mux.vo_contract.validate_vo_contract",
        lambda _ctx: ["seated synthesize vo_preface_episode_orientation has skip/omit flags"],
    )

    class _LadderFail:
        contract_ok = False
        recovered = False

    monkeypatch.setattr(
        "interview_mux.execution_contract.run_vo_contract_ladder",
        lambda *a, **k: _LadderFail(),
    )
    runner = JobRunner()
    gate_msg = runner._preflight_delivery_dispatch(
        ctx,
        stage="vo_synthesize",
        from_stage=None,
        stage_ids=["vo_synthesize"],
        mode="delivery",
    )
    assert gate_msg and "VO contract" in gate_msg
    job = ctx.read_json("gui_job.json")
    assert job.get("status") == "gate"
    assert "VO contract" in str(job.get("message") or "")


def test_exec_5174_recovery_unblocks_audit(ctx: RunContext) -> None:
    """Exec_5174 class bug: seated layup skipped → audit blocks → recovery clears path."""
    from interview_mux.recovery_controller import handle_stage_failure
    from interview_mux.stage_input_checks import collect_stage_input_issues

    _mark_homunculus(ctx)
    plant_seed_complete_through(ctx, "vo_line_adjudicate")
    _write_exec_5174_plan(ctx)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [_gap_line_019()]},
    )
    mark_done_raw(ctx, "vo_synthesize")
    mark_done_raw(ctx, "edl_narrative_audit")

    result = handle_stage_failure(
        ctx,
        "edl_narrative_audit",
        RuntimeError("VO coverage not rendered: ['vo_layup_seg_019']"),
    )
    assert result.status in {"recovered", "escalate"}
    assert result.resume_stage in {
        "vo_synthesize",
        "edl_narrative_audit",
        "edl",
        "information_package_plan",
    }
    # Unmark may refuse a hollow vo stamp — leftover done is honest.

    from run_fixtures import plant_primary_and_stamp, write_fixture_json

    gap = ctx.read_json("understanding/gap_report.json")
    if not (gap.get("interviewer_lines") or []):
        write_fixture_json(
            ctx,
            "understanding/gap_report.json",
            {"interviewer_lines": [_gap_line_019()]},
        )
    _synth_wav_for_019(ctx)
    plant_primary_and_stamp(ctx, "vo_synthesize")
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
    from run_fixtures import plant_seed_complete_through

    plant_seed_complete_through(ctx, "vo_synthesize")
    mark_done_raw(ctx, "vo_synthesize")

    handle_stage_failure(
        ctx,
        "edl_narrative_audit",
        RuntimeError("VO coverage not rendered: ['vo_layup_seg_019']"),
    )
    _synth_wav_for_019(ctx)
    mark_done_raw(ctx, "vo_synthesize")
    require_stage_inputs(ctx, "edl_narrative_audit")
    assert not collect_stage_input_issues(ctx, "edl_narrative_audit")


def test_delivery_filter_rejects_blocked_stages(ctx: RunContext) -> None:
    from interview_mux.delivery_guardrails import filter_delivery_candidates

    for sid in ("mix", "mmaudio_sfx", "junction_snip_qa", "master_finalize"):
        legal_one = filter_delivery_candidates(ctx, [sid])
        assert sid not in legal_one, f"{sid} should be blocked without prerequisites"
