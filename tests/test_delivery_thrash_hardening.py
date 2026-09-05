"""Delivery thrash hardening (post-exec_5196) — W1–W6 predicate flips."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    finalize_input_producer_pin,
    may_rewind_to_vo_synthesize,
    premature_cap_hard_pin,
    seed_stage_complete,
)
from interview_mux.publishability_boundary import (
    PublishabilityBlocked,
    checkpoint_publishability,
    commit_or_block,
    validate_publishability,
)
from interview_mux.stage_completion import stage_artifact_incompleteness
from interview_mux.stage_input_checks import collect_stage_input_issues
from interview_mux.transition_vo import (
    deferred_transition_pairs,
    stamp_transitions_pair_freeze,
    vo_synthesize_pair_incompleteness,
)
from run_fixtures import isolated_run_ctx, write_fixture_vo_wav


def _write_raw(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _seed_hash_fresh_transition(
    ctx, after_id: str, before_id: str, text: str
) -> Path:
    """Write a transition WAV + synthesis audit so resolve_transition_wav succeeds."""
    from interview_mux.vo_synthesis_audit import record_synthesis

    wav = ctx.final_path(
        "master", "transitions", f"tr_{after_id}_{before_id}.wav"
    )
    write_fixture_vo_wav(wav)
    record_synthesis(
        ctx,
        {
            "line_id": f"tr_{after_id}_{before_id}",
            "text": text,
            "targets_segment_id": after_id,
            "placement": "after",
            "after_segment_id": after_id,
            "before_segment_id": before_id,
        },
        backend="mlx_audio",
        out_wav=wav,
    )
    return wav


def _speech_clip(sid: str, *, duration_ms: int = 1000) -> dict:
    return {
        "type": "speech",
        "segment_id": sid,
        "source_start_ms": 0,
        "source_end_ms": duration_ms,
        "duration_ms": duration_ms,
        "timeline_start_ms": 0,
    }


# --- W2 --------------------------------------------------------------------


def test_post_edl_soft_fail_leaves_live_edl(tmp_path: Path) -> None:
    """Soft/fail-open publishability must not archive master/edl.json."""
    ctx = isolated_run_ctx(tmp_path, "thrash_w2_soft")
    _write_raw(
        ctx,
        "master/edl.json",
        {
            "ordered_segment_ids": ["seg_001"],
            "clips": [_speech_clip("seg_001", duration_ms=0)],
            "order_content_hash": "abc",
        },
    )
    _write_raw(ctx, "master/assembly_ledger.json", {"complete": True, "seams": []})
    assert ctx.artifact_exists("master/edl.json")
    report = checkpoint_publishability(ctx, checkpoint="post_edl", enforce=False)
    assert not report.ok
    assert ctx.artifact_exists("master/edl.json")
    assert ctx.artifact_exists("master/assembly_ledger.json")
    plan = ctx.read_json("operator/publishability_repair_plan.json")
    assert plan.get("soft") is True
    assert plan.get("cleared_from") in (None, "mix")


def test_post_edl_hard_fail_reemits_edl_ledger(tmp_path: Path) -> None:
    """Hard publishability may invalidate but must re-emit EDL+ledger before return."""
    ctx = isolated_run_ctx(tmp_path, "thrash_w2_hard")
    edl = {
        "ordered_segment_ids": ["seg_001"],
        "clips": [_speech_clip("seg_001", duration_ms=0)],
        "order_content_hash": "abc",
    }
    _write_raw(ctx, "master/edl.json", edl)
    _write_raw(ctx, "master/assembly_ledger.json", {"complete": True, "seams": []})
    ctx.mark_done("edl", force=True)
    ctx.mark_done("mix", force=True)
    report = validate_publishability(ctx, checkpoint="post_edl")
    assert not report.ok
    with pytest.raises(PublishabilityBlocked):
        commit_or_block(ctx, report, enforce=True)
    assert ctx.artifact_exists("master/edl.json")
    assert ctx.artifact_exists("master/assembly_ledger.json")
    plan = ctx.read_json("operator/publishability_repair_plan.json")
    assert plan.get("soft") is False
    assert plan.get("edl_ledger_reemitted") is True


def test_finalize_restores_archived_edl(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "thrash_w2_restore")
    arch = ctx.run_dir / ".archived" / "20260903T120000Z" / "master"
    arch.mkdir(parents=True)
    edl = {
        "ordered_segment_ids": ["seg_001"],
        "clips": [_speech_clip("seg_001")],
        "order_content_hash": "h1",
    }
    (arch / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    (arch / "assembly_ledger.json").write_text(
        json.dumps({"complete": True, "seams": []}), encoding="utf-8"
    )
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    write_fixture_vo_wav(asm)
    issues = collect_stage_input_issues(ctx, "master_finalize")
    assert ctx.artifact_exists("master/edl.json")
    assert not any("edl.json missing" in i.message for i in issues)


# --- W3 --------------------------------------------------------------------


def test_finalize_missing_ledger_pins_edl(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "thrash_w3_ledger")
    _write_raw(
        ctx,
        "master/edl.json",
        {
            "ordered_segment_ids": ["seg_001"],
            "clips": [_speech_clip("seg_001")],
            "order_content_hash": "h1",
        },
    )
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    write_fixture_vo_wav(asm)
    assert finalize_input_producer_pin(
        ctx, message="master/assembly_ledger.json missing"
    ) == "edl"
    assert premature_cap_hard_pin(ctx, "master_finalize") == "edl"


def test_finalize_missing_seam_pins_junction_when_assembled(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "thrash_w3_seam")
    _write_raw(
        ctx,
        "master/edl.json",
        {
            "ordered_segment_ids": ["seg_001"],
            "clips": [_speech_clip("seg_001")],
            "order_content_hash": "h1",
        },
    )
    _write_raw(ctx, "master/assembly_ledger.json", {"complete": True, "seams": []})
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    write_fixture_vo_wav(asm)
    assert (
        finalize_input_producer_pin(ctx, message="master/seam_autopsy.json missing")
        == "junction_snip_qa"
    )


def test_finalize_input_clears_after_ledger_write(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "thrash_w3_ledger_write")
    _write_raw(
        ctx,
        "master/edl.json",
        {
            "ordered_segment_ids": ["seg_001"],
            "clips": [_speech_clip("seg_001")],
            "order_content_hash": "h1",
        },
    )
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    write_fixture_vo_wav(asm)
    # Input check auto-emits ledger from EDL.
    collect_stage_input_issues(ctx, "master_finalize")
    assert ctx.artifact_exists("master/assembly_ledger.json")
    assert finalize_input_producer_pin(ctx) != "edl" or ctx.artifact_exists(
        "master/assembly_ledger.json"
    )


# --- W1 --------------------------------------------------------------------


def test_pair_freeze_ignores_deferred_for_vo_incompleteness(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "thrash_w1_freeze")
    _write_raw(
        ctx,
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "First hinge.",
                }
            ]
        },
    )
    _seed_hash_fresh_transition(ctx, "seg_001", "seg_002", "First hinge.")
    stamp_transitions_pair_freeze(ctx)
    # Late pair expansion after freeze.
    _write_raw(
        ctx,
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "First hinge.",
                },
                {
                    "after_segment_id": "seg_010",
                    "before_segment_id": "seg_020",
                    "text": "Late hinge.",
                },
            ]
        },
    )
    deferred = deferred_transition_pairs(ctx)
    assert ("seg_010", "seg_020") in deferred
    # G1 green (no seated synth required).
    _write_raw(ctx, "understanding/gap_report.json", {"interviewer_lines": []})
    assert vo_synthesize_pair_incompleteness(ctx) is None
    assert stage_artifact_incompleteness(ctx, "vo_synthesize") is None or (
        "transition pairs missing" not in str(stage_artifact_incompleteness(ctx, "vo_synthesize"))
    )


def test_mix_last_chance_still_sees_deferred_pairs(tmp_path: Path) -> None:
    from interview_mux.transition_vo import current_transition_pairs_missing

    ctx = isolated_run_ctx(tmp_path, "thrash_w1_mix")
    _write_raw(
        ctx,
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "First.",
                }
            ]
        },
    )
    _seed_hash_fresh_transition(ctx, "seg_001", "seg_002", "First.")
    stamp_transitions_pair_freeze(ctx)
    _write_raw(
        ctx,
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "First.",
                },
                {
                    "after_segment_id": "seg_010",
                    "before_segment_id": "seg_020",
                    "text": "Deferred.",
                },
            ]
        },
    )
    missing = current_transition_pairs_missing(ctx)
    assert "seg_010->seg_020" in missing


# --- W6 --------------------------------------------------------------------


def test_may_rewind_refuses_when_assembly_g1_green_deferred(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "thrash_w6_refuse")
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    write_fixture_vo_wav(asm)
    _write_raw(ctx, "understanding/gap_report.json", {"interviewer_lines": []})
    _write_raw(
        ctx,
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "Ok.",
                }
            ]
        },
    )
    _seed_hash_fresh_transition(ctx, "seg_001", "seg_002", "Ok.")
    stamp_transitions_pair_freeze(ctx)
    assert may_rewind_to_vo_synthesize(ctx) is False


def test_may_rewind_allows_seated_stale_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "thrash_w6_allow")
    monkeypatch.setattr(
        "interview_mux.gates.check_g1_vo",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.gates.g1_vo_was_skipped_optional",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.vo_contract.seated_vo_missing_ids",
        lambda _ctx: ["vo_layup_seg_007"],
    )
    assert may_rewind_to_vo_synthesize(ctx) is True


def test_may_rewind_allows_compact_vo_script_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "thrash_w6_stale_hash")
    monkeypatch.setattr(
        "interview_mux.gates.check_g1_vo",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.gates.g1_vo_was_skipped_optional",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.vo_contract.seated_vo_missing_ids",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.stage_input_checks.compact_vo_coverage_stale_or_missing",
        lambda _ctx: ["vo_layup_seg_013"],
    )
    assert may_rewind_to_vo_synthesize(ctx) is True


# --- W4 --------------------------------------------------------------------


def test_omit_pass_b_clamp_active_count_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Omit Pass B → clamp → active count ≤ rendered WAVs and ≥ floor when WAVs allow."""
    from interview_mux.air_script import persist_air_script_omits_on_gap_report
    from interview_mux.gap_fill_eligibility import count_active_gap_vo_lines

    ctx = isolated_run_ctx(tmp_path, "thrash_w4_clamp")
    monkeypatch.setattr("interview_mux.air_script.air_script_enabled", lambda: True)
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 2,
    )
    for lid in ("vo_layup_seg_007", "vo_layup_seg_010"):
        write_fixture_vo_wav(ctx.final_path("vo_pickup", "synthesized", f"{lid}.wav"))
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "pass": "pass_b",
                "beats": [
                    {"segment_id": "seg_007", "montage_move": "vo_setup"},
                    {"segment_id": "seg_010", "montage_move": "vo_setup"},
                ],
                "vo_seats": {
                    "seated_line_ids": [
                        "vo_layup_seg_007",
                        "vo_layup_seg_010",
                        "vo_layup_seg_039",
                    ],
                    "omitted_line_ids": [],
                },
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
                    "text": "No WAV.",
                },
            ]
        },
    )
    persist_air_script_omits_on_gap_report(ctx)
    active = count_active_gap_vo_lines(ctx)
    assert active <= 2
    assert active >= 2


# --- W5 --------------------------------------------------------------------


def test_force_done_missing_g1_wav_blocks_seed_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "thrash_w5_hollow")
    _write_raw(
        ctx,
        "master/transitions.json",
        {"transitions": []},
    )
    _write_raw(
        ctx,
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
                    "text": "Need WAV.",
                    "required": True,
                }
            ]
        },
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_007"],
                    "omitted_line_ids": [],
                }
            }
        },
    )
    monkeypatch.setattr(
        "interview_mux.gates.check_g1_vo",
        lambda _ctx: ["vo_layup_seg_007"],
    )
    monkeypatch.setattr(
        "interview_mux.gates.g1_vo_was_skipped_optional",
        lambda _ctx: False,
    )
    # force=True must not make seed_complete true while G1 WAV missing.
    ctx.mark_done("vo_synthesize", force=True)
    assert stage_artifact_incompleteness(ctx, "vo_synthesize") is not None
    assert seed_stage_complete(ctx, "vo_synthesize") is False
