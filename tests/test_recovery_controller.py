"""Source-adaptive recovery: one typed playbook per signature, then escalate."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.edl_qc import validate_flow1_edl
from interview_mux.listen_quality import music_hinge_issues, place_episode_close_cue
from interview_mux.opening_orientation import retarget_orientation_to_open
from interview_mux.recovery_controller import (
    classify_error_class,
    handle_stage_failure,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_resilience import escalate_stage_failure, resolve_escalation
from interview_mux.vo_synthesis_audit import qc_failed
from run_fixtures import mark_done_raw


def test_classify_exec_1822_signatures():
    assert (
        classify_error_class(
            "ideal_cuts_materialize",
            RuntimeError("bind_mode requires boundaries but no valid cuts after snap"),
        )
        == "empty_snap"
    )
    assert (
        classify_error_class(
            "nugget_layup_compose",
            RuntimeError("Nugget layup QC failed: layup_coverage=0.562 below min_layup_coverage=0.4"),
        )
        == "layup_coverage"
    )
    assert (
        classify_error_class(
            "nugget_layup_compose",
            RuntimeError(
                "Nugget layup QC failed: never_touch_cta[seg_009]: lay-up reuses dropped CTA wording"
            ),
        )
        == "never_touch_cta"
    )
    assert (
        classify_error_class(
            "edl",
            RuntimeError(
                'clips[0]: vo_pickup line_id "vo_preface_episode_orientation" '
                'targets_segment_id "seg_002" does not match gap_report "seg_013"'
            ),
        )
        == "orientation_target_mismatch"
    )
    assert classify_error_class("edl", RuntimeError("naked seam: seg_033→seg_034")) == "naked_seam"
    assert (
        classify_error_class(
            "edl",
            RuntimeError("edl_qc strict: 8 issue(s) before edl. Fix master/edl.json or re-run edl."),
        )
        is None
    )
    assert (
        classify_error_class(
            "edl",
            RuntimeError(
                "edl_qc strict: 1 issue(s) before edl. "
                "Overlapping source range: seg_003c [62900,74760ms) intersects "
                "seg_003d [71000,74810ms)"
            ),
        )
        == "overlapping_source_range"
    )
    assert (
        classify_error_class(
            "edl",
            RuntimeError('clips[2]: unknown segment_id "seg_003a"'),
        )
        == "unknown_nle_split_child"
    )
    assert classify_error_class("mix", RuntimeError("mmaudio_qa.json missing")) == "mmaudio_qa_missing"
    assert (
        classify_error_class(
            "mix",
            RuntimeError(
                "Mix gate: missing WAV for asset_id show_theme_v1_motif; "
                "missing WAV for asset_id show_theme_v1_underscore_loop"
            ),
        )
        == "sdp_theme_wavs_missing"
    )
    assert (
        classify_error_class(
            "master_finalize",
            RuntimeError("episode_close_outro_present"),
        )
        == "episode_close_outro"
    )
    assert (
        classify_error_class(
            "speaker_roles",
            RuntimeError(
                "LLM stage speaker_roles incomplete: status=partial "
                "needs=[{'type': 'rerun_stage', 'stage': 'diarization', "
                "'blocking': True}]"
            ),
        )
        == "mixed_diarization"
    )
    assert (
        classify_error_class(
            "nugget_layup_compose",
            RuntimeError(
                "LLM stage nugget_layup_compose incomplete: status=partial "
                "needs=[{'type': 'rerun_stage', 'stage': 'selection', "
                "'reason': 'Remove seg_001a sponsor bumper', 'blocking': True}]"
            ),
        )
        == "selection_cta_omit"
    )
    assert (
        classify_error_class(
            "nugget_layup_compose",
            RuntimeError(
                "LLM stage nugget_layup_compose incomplete: status=partial "
                "needs=[{'type': 'rerun_stage', 'stage': 'selection', "
                "'reason': 'Remove seg_068b through seg_068l outro credits', "
                "'blocking': True}]"
            ),
        )
        == "selection_cta_omit"
    )
    assert (
        classify_error_class(
            "nugget_layup_compose",
            RuntimeError(
                "LLM stage nugget_layup_compose incomplete: "
                "cta_omit_applied dropped seg_001a,seg_003h"
            ),
        )
        == "selection_cta_omit"
    )


def test_mixed_diarization_playbook_writes_speakers(tmp_path: Path) -> None:
    import json

    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "rec_mixed_diar")
    words = []
    t = 0
    for _ in range(40):
        words.append({"speaker": "spk_0", "word": "story", "start_ms": t, "end_ms": t + 400})
        t += 450
    for _ in range(8):
        words.append({"speaker": "spk_1", "word": "why?", "start_ms": t, "end_ms": t + 200})
        t += 250
    (ctx.run_dir / "transcript").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "transcript" / "full.json").write_text(
        json.dumps({"text": "dialogue", "words": words}),
        encoding="utf-8",
    )
    (ctx.run_dir / "transcript" / "speakers.json").write_text(
        json.dumps({"speakers": [{"speaker_id": "spk_0"}, {"speaker_id": "spk_1"}]}),
        encoding="utf-8",
    )
    result = handle_stage_failure(
        ctx,
        "speaker_roles",
        RuntimeError(
            "LLM stage speaker_roles incomplete: status=partial "
            "needs=[{'type': 'rerun_stage', 'stage': 'speaker_diarization'}]"
        ),
    )
    assert result.status == "recovered"
    assert result.playbook_id == "speaker_roles_dominant_fallback"
    assert result.resume_stage == "source_topology_build"
    assert ctx.is_done("speaker_roles")
    assert ctx.artifact_exists("understanding/speakers.json")


def test_homunculus_selection_cta_omit_runs_without_analysis(tmp_path: Path) -> None:
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "rec_cta_omit_h")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_002", "seg_074b"]},
        skip_handoff=True,
    )
    result = handle_stage_failure(
        ctx,
        "nugget_layup_compose",
        RuntimeError(
            "LLM stage nugget_layup_compose incomplete: "
            "cta_omit_applied dropped seg_074b,seg_074d,seg_074g,seg_002"
        ),
    )
    assert result.status == "recovered"
    assert result.playbook_id == "host_cta_omit"
    assert result.resume_stage == "nugget_layup_compose"


def test_never_touch_cta_playbook_skips_without_analysis(tmp_path: Path):
    from interview_mux.nugget_layup import PLAN_REL, evaluate_layup_qc

    ctx = RunContext(str(tmp_path / "rec_never_touch"), create=True)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
    )
    ctx.write_json(
        "mastering/media_ip_cta.json",
        {
            "version": 1,
            "locked": True,
            "dropped_segment_ids": ["seg_cta"],
            "never_touch_segment_ids": ["seg_cta"],
            "never_touch_texts": [
                "Go subscribe to my old show and buy the course at the link below"
            ],
        },
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_b"]})
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_b",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "the exit story",
                    "start_ms": 0,
                    "end_ms": 8000,
                }
            ]
        },
    )
    ctx.write_json(
        PLAN_REL,
        {
            "ordered_segment_ids": ["seg_b"],
            "layups": [
                {
                    "target_segment_id": "seg_b",
                    "text": (
                        "Go subscribe to my old show and buy the course at the link below. "
                        "Why did the exit change the market?"
                    ),
                    "target_beat": "The exit",
                    "listener_need_entering_T": "Need the exit beat",
                    "forward_unlock": "Why did the exit change the market?",
                    "skip": False,
                }
            ],
        },
    )
    result = handle_stage_failure(
        ctx,
        "nugget_layup_compose",
        RuntimeError(
            "Nugget layup QC failed: never_touch_cta[seg_b]: lay-up reuses dropped CTA wording"
        ),
    )
    assert result.status == "recovered"
    assert result.playbook_id == "skip_never_touch_cta_layups"
    plan = ctx.read_json(PLAN_REL)
    row = (plan.get("layups") or [])[0]
    assert row.get("skip") is True
    assert row.get("skip_reason_code") == "never_touch_cta"
    qc = evaluate_layup_qc(ctx, plan)
    assert not any("never_touch_cta" in str(e) for e in (qc.get("errors") or []))


def test_second_identical_signature_escalates(tmp_path: Path, monkeypatch):
    ctx = RunContext(str(tmp_path / "rec_budget"), create=True)
    monkeypatch.setattr(
        "interview_mux.recovery_controller.playbook_stamp_valueless_skips",
        lambda _ctx: ["understanding/nugget_layup_plan.json"],
    )
    exc = RuntimeError("Nugget layup QC failed: layup_coverage=0.2 below min_layup_coverage=0.4")
    first = handle_stage_failure(ctx, "nugget_layup_compose", exc)
    assert first.status == "recovered"
    second = handle_stage_failure(ctx, "nugget_layup_compose", exc)
    assert second.status == "escalate"
    assert second.playbook_id == "budget_exhausted"


def test_naked_seam_mints_once_then_escalates(tmp_path: Path, monkeypatch):
    ctx = RunContext(str(tmp_path / "rec_seam"), create=True)
    calls = {"n": 0}

    def _mint(_ctx):
        calls["n"] += 1
        return []

    monkeypatch.setattr(
        "interview_mux.recovery_controller.playbook_mint_reorder_glue", _mint
    )
    exc = RuntimeError("naked seam: seg_033→seg_034")
    first = handle_stage_failure(ctx, "edl", exc)
    assert first.status == "escalate"
    assert calls["n"] == 1
    second = handle_stage_failure(ctx, "edl", exc)
    assert second.status == "escalate"
    assert second.playbook_id == "budget_exhausted"
    assert calls["n"] == 1


def test_escalation_still_rejects_soft_ship(tmp_path: Path):
    ctx = RunContext(str(tmp_path / "rec_esc"), create=True)
    doc = escalate_stage_failure(
        ctx,
        "mix",
        failed_invariant="mmaudio_qa_missing",
        evidence={"path": "sound_design/mmaudio_qa.json"},
    )
    option_ids = {o["id"] for o in doc["options"]}
    assert "soft_ship" not in option_ids
    assert "waive_quality" not in option_ids
    with pytest.raises(ValueError, match="quality_first"):
        bad = dict(doc)
        bad["options"] = list(doc["options"]) + [{"id": "soft_ship", "label": "Soft ship"}]
        from interview_mux.file_store import write_json as fs_write_json

        fs_write_json(Path(ctx.run_dir) / "operator" / "escalations" / "mix.json", bad)
        resolve_escalation(ctx, "mix", chosen_option="soft_ship")


def test_orientation_retarget_makes_edl_validate(tmp_path: Path):
    ctx = RunContext(str(tmp_path / "rec_orient"), create=True)
    from interview_mux.gap_vo_gates import set_gap_framing_enabled

    set_gap_framing_enabled(ctx, True)
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_013", "seg_014"]})
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_013",
                    "text": "Tissue biopsy remains invasive for many patients.",
                    "start_ms": 0,
                    "end_ms": 4000,
                    "speaker_id": "spk_guest",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                },
                {
                    "segment_id": "seg_014",
                    "text": "Liquid biopsy uses a blood draw instead.",
                    "start_ms": 4000,
                    "end_ms": 8000,
                    "speaker_id": "spk_guest",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                },
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "gap_type": "missing_setup",
                    "line_category": "episode_preface",
                    "episode_orientation": True,
                    "orientation_missions": [
                        "guest_identity",
                        "conversation_topic",
                        "listener_stakes",
                    ],
                    "text": (
                        "Today we sit with Mohan Uttarwar to talk liquid biopsy "
                        "and what it means for patients."
                    ),
                    "targets_segment_id": "seg_002",
                    "delivery": "synthesize",
                    "placement": "before",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_013", "seg_014"],
            "timeline_duration_ms": 1200,
            "clips": [
                {
                    "type": "vo_pickup",
                    "line_id": "vo_preface_episode_orientation",
                    "targets_segment_id": "seg_002",
                    "placement": "before",
                    "timeline_start_ms": 0,
                    "duration_ms": 1200,
                }
            ],
        },
        skip_handoff=True,
    )
    written = retarget_orientation_to_open(ctx)
    assert written
    errors = validate_flow1_edl(ctx)
    assert not any("targets_segment_id" in e and "does not match gap_report" in e for e in errors)


def test_place_episode_close_cue_when_bed_present(tmp_path: Path):
    from run_fixtures import sound_design_plan_with

    ctx = RunContext(str(tmp_path / "rec_close"), create=True)
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001"]})
    sdp = sound_design_plan_with(
        assets=[
            {
                "asset_id": "show_theme_v1_full_bed_close",
                "role": "theme_outro",
                "description": "Episode close bed",
                "duration_seconds": 12,
            }
        ],
        flow_plans={"podcast": {"cues": []}},
    )
    ctx.write_json("understanding/sound_design_plan.json", sdp, skip_handoff=True)
    written = place_episode_close_cue(ctx)
    assert written
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    issues = music_hinge_issues(sdp)
    assert not any(
        str(i.get("code") or "").startswith("missing_episode_close") for i in issues
    )
    cues = list(
        ((sdp.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []
    )
    outro = next(c for c in cues if isinstance(c, dict) and c.get("role") == "theme_outro")
    assert int(outro.get("fade_out_ms") or 0) >= 180
    assert "e2e_softened" not in sdp


def test_place_episode_close_cue_rebinds_to_last_speech_clip(tmp_path: Path):
    from interview_mux.music_lane import pick_theme_outro_asset
    from run_fixtures import sound_design_plan_with

    ctx = RunContext(str(tmp_path / "rec_close_rebind"), create=True)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_060", "seg_062", "seg_055"]},
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_060", "seg_062"],
            "timeline_duration_ms": 2500,
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_060",
                    "source_start_ms": 0,
                    "source_end_ms": 1000,
                    "timeline_start_ms": 0,
                    "duration_ms": 1000,
                },
                {
                    "type": "speech",
                    "segment_id": "seg_062",
                    "source_start_ms": 2000,
                    "source_end_ms": 2500,
                    "timeline_start_ms": 1000,
                    "duration_ms": 500,
                },
                {
                    "type": "speech",
                    "segment_id": "seg_055",
                    "source_start_ms": 3000,
                    "source_end_ms": 4000,
                    "timeline_start_ms": 1500,
                    "duration_ms": 1000,
                },
            ],
        },
        skip_handoff=True,
    )
    sdp = sound_design_plan_with(
        assets=[
            {
                "asset_id": "onecell_documentary_close_bed_v17",
                "role": "theme_outro",
                "placement_hint": "open",
                "description": "Open-style bed",
                "duration_seconds": 18,
            },
            {
                "asset_id": "show_theme_v1_full_bed_close",
                "role": "theme_outro",
                "placement_hint": "close",
                "description": "Episode close bed",
                "duration_seconds": 18,
            },
        ],
        flow_plans={
            "podcast": {
                "cues": [
                    {
                        "cue_id": "theme_outro_seed",
                        "role": "theme_outro",
                        "asset_id": "onecell_documentary_close_bed_v17",
                        "placement": "after_segment",
                        "after_segment_id": "seg_060",
                        "segment_id": "seg_060",
                    }
                ]
            }
        },
    )
    ctx._one_writer_raw = True
    ctx.write_json("understanding/sound_design_plan.json", sdp, skip_handoff=True)
    picked = pick_theme_outro_asset(sdp["assets"])
    assert picked is not None
    assert picked["asset_id"] == "show_theme_v1_full_bed_close"
    written = place_episode_close_cue(ctx)
    assert written
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    cues = list(((sdp.get("flow_plans") or {}).get("podcast") or {}).get("cues") or [])
    outro = next(c for c in cues if isinstance(c, dict) and c.get("role") == "theme_outro")
    assert outro["after_segment_id"] == "seg_055"
    assert outro["asset_id"] == "show_theme_v1_full_bed_close"


def test_qc_failed_uses_topology_synth_ladder(tmp_path: Path, monkeypatch):
    ctx = RunContext(str(tmp_path / "rec_qc"), create=True)
    ctx.write_json(
        "understanding/flow_adaptation.json",
        {
            "topology_class": "one_on_one_balanced",
            "recovery_policy": {"synth_ladder": "chatterbox_then_mlx_qc"},
        },
    )
    entry = {"qc_pass": False}
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.gap_vo_cfg",
        lambda: {"auto_fallback_on_qc_fail": False},
    )
    assert qc_failed(entry) is False
    assert qc_failed(entry, ctx) is True


def test_framing_vo_unseated_stops_on_unchanged_vo_seats(tmp_path: Path, monkeypatch):
    ctx = RunContext(str(tmp_path / "rec_vo_seats"), create=True)
    calls = {"n": 0}

    def _stamp(_ctx):
        calls["n"] += 1
        return ["mastering/mastering_plan.json"]

    monkeypatch.setattr(
        "interview_mux.recovery_controller.playbook_stamp_air_script_omits",
        _stamp,
    )
    monkeypatch.setattr(
        "interview_mux.recovery_controller.vo_seats_fingerprint",
        lambda _ctx: "samehash",
    )
    exc = RuntimeError("seg_011 lacks preceding framing VO vo_layup_seg_011")
    assert classify_error_class("edl", exc) == "framing_vo_unseated"
    first = handle_stage_failure(ctx, "edl", exc)
    assert first.status == "recovered"
    assert first.playbook_id == "stamp_air_script_omits"
    second = handle_stage_failure(ctx, "edl", exc)
    assert second.status == "recovered"
    third = handle_stage_failure(ctx, "edl", exc)
    assert third.status == "escalate"
    assert third.playbook_id == "identical_vo_seats_x3"
    assert calls["n"] == 2


def test_mmaudio_qa_missing_resumes_producer(tmp_path: Path, monkeypatch):
    ctx = RunContext(str(tmp_path / "rec_qa_resume"), create=True)
    monkeypatch.setattr(
        "interview_mux.recovery_controller.playbook_ensure_mmaudio_qa",
        lambda _ctx: ["sound_design/mmaudio_qa.json"],
    )
    result = handle_stage_failure(ctx, "mix", RuntimeError("sound_design/mmaudio_qa.json missing"))
    assert result.status == "recovered"
    assert result.resume_stage == "mmaudio_sfx"


def test_mix_missing_theme_wav_resumes_palette(tmp_path: Path, monkeypatch):
    ctx = RunContext(str(tmp_path / "rec_theme_wav"), create=True)
    monkeypatch.setattr(
        "interview_mux.recovery_controller.playbook_generate_sdp_theme_wavs",
        lambda _ctx: ["missing:show_theme_v1_motif"],
    )
    result = handle_stage_failure(
        ctx,
        "mix",
        RuntimeError("Mix gate: missing WAV for asset_id show_theme_v1_motif"),
    )
    assert result.status == "recovered"
    assert result.playbook_id == "generate_sdp_theme_wavs"
    assert result.resume_stage == "music_palette_compose"
    for _ in range(2):
        again = handle_stage_failure(
            ctx,
            "mix",
            RuntimeError("Mix gate: missing WAV for asset_id show_theme_v1_motif"),
        )
        assert again.status == "recovered"
    exhausted = handle_stage_failure(
        ctx,
        "mix",
        RuntimeError("Mix gate: missing WAV for asset_id show_theme_v1_motif"),
    )
    assert exhausted.status == "escalate"
    assert exhausted.resume_stage in {"mix", "music_palette_compose"}


def test_overlapping_source_playbook_merges_and_resumes_edl(tmp_path: Path) -> None:
    from run_fixtures import isolated_run_ctx, minimal_gap_report, minimal_manifest, minimal_manifest_segment

    ctx = isolated_run_ctx(tmp_path, "rec_overlap_src")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_003c", start_ms=62_900, end_ms=74_760, speaker_id="spk_0"
            ),
            minimal_manifest_segment(
                "seg_003d", start_ms=71_000, end_ms=74_810, speaker_id="spk_0"
            ),
        ),
    )
    ctx.write_json("understanding/gap_report.json", minimal_gap_report())
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_003c", "seg_003d"]},
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_003c", "seg_003d"],
            "timeline_duration_ms": 15_670,
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_003c",
                    "source_start_ms": 62_900,
                    "source_end_ms": 74_760,
                    "timeline_start_ms": 0,
                    "duration_ms": 11_860,
                },
                {
                    "type": "speech",
                    "segment_id": "seg_003d",
                    "source_start_ms": 71_000,
                    "source_end_ms": 74_810,
                    "timeline_start_ms": 11_860,
                    "duration_ms": 3_810,
                },
            ],
        },
    )
    exc = RuntimeError(
        "edl_qc strict: 1 issue(s) before edl. "
        "Overlapping source range: seg_003c [62900,74760ms) intersects "
        "seg_003d [71000,74810ms)"
    )
    result = handle_stage_failure(ctx, "edl", exc)
    assert result.status == "recovered"
    assert result.playbook_id == "merge_overlapping_source_ranges"
    assert result.resume_stage == "edl"
    edl = ctx.read_json("master/edl.json")
    speech = [c["segment_id"] for c in edl["clips"] if c.get("type") == "speech"]
    assert speech == ["seg_003c"]
    assert validate_flow1_edl(ctx, edl) == []


def test_playbook_upstream_stale_rerun_edl_pins_transitions(tmp_path: Path) -> None:
    from run_fixtures import isolated_run_ctx
    from interview_mux.recovery_controller import playbook_upstream_stale_rerun

    ctx = isolated_run_ctx(tmp_path, "stale_tr_playbook")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "transitions.json").write_text(
        __import__("json").dumps(
            {
                "transitions": [],
                "_meta": {
                    "stale": True,
                    "stale_reason": "invalidated_by:nugget_layup_compose",
                },
            }
        ),
        encoding="utf-8",
    )
    mark_done_raw(ctx, "transitions")
    cleared = playbook_upstream_stale_rerun(ctx, consumer_stage="edl")
    assert "transitions" in cleared
    assert not ctx.is_done("transitions")
    doc = ctx.read_json("master/transitions.json")
    assert not (doc.get("_meta") or {}).get("stale")


def test_handle_stage_failure_edl_stale_transitions_resume(tmp_path: Path) -> None:
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "stale_tr_hsf")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus", "partial_auto": True},
        skip_handoff=True,
    )
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "transitions.json").write_text(
        __import__("json").dumps(
            {
                "transitions": [],
                "_meta": {
                    "stale": True,
                    "stale_reason": "invalidated_by:nugget_layup_compose",
                },
            }
        ),
        encoding="utf-8",
    )
    result = handle_stage_failure(
        ctx,
        "edl",
        RuntimeError(
            "master/transitions.json is marked stale "
            "(invalidated_by:nugget_layup_compose)"
        ),
    )
    assert result.status == "recovered"
    assert result.playbook_id == "upstream_stale_rerun"
    assert result.resume_stage == "transitions"


def test_should_not_stamp_needs_operator_for_stale_transitions() -> None:
    from interview_mux.operator_gates import should_stamp_needs_operator

    meta = {"partial_auto": True, "homunculus_version": "0.1.0"}
    reason = (
        "RuntimeError:seed order: complete air_script_seams before running transitions"
    )
    assert not should_stamp_needs_operator("transitions", reason, meta=meta)
    assert not should_stamp_needs_operator(
        "edl",
        "master/transitions.json is marked stale (invalidated_by:nugget_layup_compose)",
        meta=meta,
    )


def test_resolve_fingerprint_heal_resume_prefers_producer_not_gate() -> None:
    from interview_mux.recovery_controller import resolve_fingerprint_heal_resume

    # Named producer in message wins over later gate (edl).
    assert (
        resolve_fingerprint_heal_resume(
            message=(
                "master/selection.json fingerprint mismatch — "
                "re-run producer full_master_ranking"
            ),
            gate_stage="edl",
            body_from="topic_coverage_audit",
            mode="delivery",
        )
        == "full_master_ranking"
    )
    # Unnamed: consumer map pins producer, never the gate alone.
    assert (
        resolve_fingerprint_heal_resume(
            message="fingerprint mismatch on upstream artifact",
            gate_stage="edl",
            body_from="edl",
            mode="delivery",
        )
        == "full_master_ranking"
    )
    # Path without producer name → STAGE path / preferred fill.
    assert (
        resolve_fingerprint_heal_resume(
            message="master/transitions.json fingerprint mismatch",
            gate_stage="edl",
            body_from="edl",
            mode="delivery",
        )
        == "transitions"
    )


def test_classify_broad_vo_coverage() -> None:
    assert (
        classify_error_class(
            "edl_narrative_audit",
            RuntimeError("Synthetic VO does not match EDL/gap for line vo_x"),
        )
        == "vo_seated_coverage"
    )
    assert (
        classify_error_class(
            "edl",
            RuntimeError("seated synthesize vo_layup_seg_002 missing WAV"),
        )
        == "vo_seated_coverage"
    )
    assert (
        classify_error_class(
            "edl_narrative_audit",
            RuntimeError("stage input check blocked: VO coverage stale for seated lines"),
        )
        == "vo_seated_coverage"
    )
    # Contract skip/omit stays on contract ladder.
    assert (
        classify_error_class(
            "edl",
            RuntimeError("vo contract: seated synthesize vo_x has skip/omit flags"),
        )
        == "vo_contract_repair"
    )


def test_handle_vo_seated_coverage_always_pins_vo_synthesize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "vo_cov_pin")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus", "partial_auto": True},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.execution_contract.run_edl_vo_coverage_ladder",
        lambda ctx, consumer_stage="edl": __import__(
            "interview_mux.execution_contract", fromlist=["VoCoverageLadderResult"]
        ).VoCoverageLadderResult(
            tier="tier_d_operator",
            recovered=False,
            detail="still_missing: ['vo_x']",
            resume_stage=consumer_stage,
        ),
    )
    monkeypatch.setattr(
        "interview_mux.stage_input_checks.compact_vo_coverage_stale_or_missing",
        lambda _ctx: ["vo_x"],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.may_rewind_to_vo_synthesize",
        lambda _ctx: True,
    )
    mark_done_raw(ctx, "vo_synthesize")
    result = handle_stage_failure(
        ctx,
        "edl_narrative_audit",
        RuntimeError("VO coverage not rendered: ['vo_x']"),
    )
    assert result.status == "recovered"
    assert result.resume_stage == "vo_synthesize"
    assert not ctx.is_done("vo_synthesize")

    assert (
        classify_error_class(
            "transitions",
            RuntimeError("seed order: complete air_script_seams before running transitions"),
        )
        == "seed_order_prereq"
    )
    assert (
        classify_error_class(
            "master_finalize",
            RuntimeError("master/seam_autopsy.json missing"),
        )
        == "finalize_input_missing"
    )
    assert (
        classify_error_class(
            "mix",
            RuntimeError("cannot run mix: delivery epoch assembly_stale_versus_edl"),
        )
        == "assembly_not_rendered_from_current_edl"
    )
    # Multi-blocker stale upstream stays on the upstream playbook (clears all).
    assert (
        classify_error_class(
            "mix",
            RuntimeError("cannot run mix: stale upstream transitions, assembly_stale_versus_edl"),
        )
        == "upstream_stale_rerun"
    )


def test_resolve_assembly_stale_resume_edl_good_pins_mix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from run_fixtures import isolated_run_ctx
    from interview_mux.delivery_guardrails import resolve_assembly_stale_resume

    ctx = isolated_run_ctx(tmp_path, "asm_stale_mix")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "edl.json").write_text(
        __import__("json").dumps(
            {"ordered_segment_ids": ["seg_001"], "clips": [], "order_content_hash": "h1"}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "interview_mux.heal_routing.mix_assembly_seated",
        lambda _ctx: False,
    )
    assert resolve_assembly_stale_resume(ctx) == "mix"
    monkeypatch.setattr(
        "interview_mux.heal_routing.mix_assembly_seated",
        lambda _ctx: True,
    )
    assert resolve_assembly_stale_resume(ctx) == "junction_snip_qa"


def test_resolve_assembly_stale_resume_stale_edl_pins_edl(tmp_path: Path) -> None:
    from run_fixtures import isolated_run_ctx
    from interview_mux.delivery_guardrails import resolve_assembly_stale_resume

    ctx = isolated_run_ctx(tmp_path, "asm_stale_edl")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "edl.json").write_text(
        __import__("json").dumps(
            {
                "ordered_segment_ids": ["seg_001"],
                "clips": [],
                "_meta": {"stale": True, "stale_reason": "invalidated_by:nugget_layup_compose"},
            }
        ),
        encoding="utf-8",
    )
    assert resolve_assembly_stale_resume(ctx) == "edl"


def test_handle_delivery_epoch_assembly_stale_resumes_mix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "epoch_asm")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus", "partial_auto": True},
        skip_handoff=True,
    )
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "edl.json").write_text(
        __import__("json").dumps(
            {"ordered_segment_ids": ["seg_001"], "clips": [], "order_content_hash": "h1"}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "interview_mux.heal_routing.mix_assembly_seated",
        lambda _ctx: False,
    )
    result = handle_stage_failure(
        ctx,
        "mix",
        RuntimeError("cannot run mix: delivery epoch assembly_stale_versus_edl (wait for mmaudio_sfx)"),
    )
    assert result.status == "recovered"
    assert result.playbook_id == "assembly_not_rendered_from_current_edl"
    assert result.resume_stage == "mix"


def test_handle_seed_order_prereq_pins_named_stage(tmp_path: Path) -> None:
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "seed_order_hsf")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus", "partial_auto": True},
        skip_handoff=True,
    )
    mark_done_raw(ctx, "air_script_seams")
    result = handle_stage_failure(
        ctx,
        "transitions",
        RuntimeError("seed order: complete air_script_seams before running transitions"),
    )
    assert result.status == "recovered"
    assert result.playbook_id == "seed_order_prereq"
    assert result.resume_stage == "air_script_seams"
    assert not ctx.is_done("air_script_seams")


def test_handle_g1_vo_open_seed_order_does_not_unmark_adjudicate(tmp_path: Path) -> None:
    """g1_vo_open → resume vo_synthesize; leave adjudicate markers intact."""
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "seed_order_g1_open")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus", "partial_auto": True},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "gaps": [],
            "interviewer_lines": [
                {
                    "line_id": "vo_x",
                    "text": "x",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                }
            ],
        },
        skip_handoff=True,
    )
    mark_done_raw(ctx, "vo_line_adjudicate")
    result = handle_stage_failure(
        ctx,
        "vo_synthesize",
        RuntimeError("seed order: complete g1_vo_open before running vo_synthesize"),
    )
    assert result.status == "recovered"
    assert result.playbook_id == "seed_order_prereq"
    assert result.resume_stage == "vo_synthesize"
    assert ctx.is_done("vo_line_adjudicate")


def test_handle_finalize_input_missing_pins_junction(tmp_path: Path) -> None:
    from run_fixtures import isolated_run_ctx, write_fixture_vo_wav

    ctx = isolated_run_ctx(tmp_path, "fin_input_hsf")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus", "partial_auto": True},
        skip_handoff=True,
    )
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "edl.json").write_text(
        __import__("json").dumps(
            {"ordered_segment_ids": ["seg_001"], "clips": [], "order_content_hash": "h1"}
        ),
        encoding="utf-8",
    )
    (ctx.run_dir / "master" / "assembly_ledger.json").write_text(
        __import__("json").dumps({"complete": True, "seams": []}),
        encoding="utf-8",
    )
    write_fixture_vo_wav(ctx.final_path("master", "assembly.wav"))
    result = handle_stage_failure(
        ctx,
        "master_finalize",
        RuntimeError("master/seam_autopsy.json missing"),
    )
    assert result.status == "recovered"
    assert result.playbook_id == "finalize_input_missing"
    assert result.resume_stage == "junction_snip_qa"


def test_gap_report_stale_producer_by_invalidator(tmp_path: Path) -> None:
    from run_fixtures import isolated_run_ctx
    from interview_mux.delivery_guardrails import resolve_gap_report_stale_producer
    from interview_mux.recovery_controller import playbook_upstream_stale_rerun

    ctx = isolated_run_ctx(tmp_path, "gap_stale_prod")
    (ctx.run_dir / "understanding").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "understanding" / "gap_report.json").write_text(
        __import__("json").dumps(
            {
                "interviewer_lines": [],
                "_meta": {
                    "stale": True,
                    "stale_reason": "invalidated_by:gap_framing_recompose",
                },
            }
        ),
        encoding="utf-8",
    )
    assert resolve_gap_report_stale_producer(ctx) == "gap_framing_recompose"
    cleared = playbook_upstream_stale_rerun(ctx, consumer_stage="edl")
    assert "gap_framing_recompose" in cleared


def test_resolve_stage_plan_remaps_stale_upstream_assembly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from run_fixtures import isolated_run_ctx
    from interview_mux.homunculus import agenda as agenda_mod

    ctx = isolated_run_ctx(tmp_path, "agenda_stale_asm")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "edl.json").write_text(
        __import__("json").dumps(
            {"ordered_segment_ids": ["seg_001"], "clips": [], "order_content_hash": "h1"}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(agenda_mod, "DELIVERY_ANALYSIS_PREREQS", ())
    monkeypatch.setattr(
        "interview_mux.artifact_dependency_graph.upstream_closure",
        lambda _stage: [],
    )
    monkeypatch.setattr(
        "interview_mux.artifact_dependency_graph.transitive_invalidate",
        lambda _stage: set(),
    )
    monkeypatch.setattr(agenda_mod, "stage_outputs_present", lambda _ctx, _up: True)
    monkeypatch.setattr(agenda_mod, "skipped_stages", lambda _ctx: set())
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.upstream_stale_blockers",
        lambda _ctx, _stage: ["assembly_stale_versus_edl"],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.mix_epoch_block",
        lambda _ctx: None,
    )
    monkeypatch.setattr(
        "interview_mux.heal_routing.mix_assembly_seated",
        lambda _ctx: False,
    )
    plan = agenda_mod.resolve_stage_plan(ctx, "mix")
    assert "stale_upstream:assembly_stale_versus_edl" in plan["blockers"]
    assert plan["recommended_next"] == "mix"


def test_resolve_stage_plan_remaps_mix_epoch_music(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from run_fixtures import isolated_run_ctx
    from interview_mux.homunculus import agenda as agenda_mod

    ctx = isolated_run_ctx(tmp_path, "agenda_mix_epoch")
    monkeypatch.setattr(agenda_mod, "DELIVERY_ANALYSIS_PREREQS", ())
    monkeypatch.setattr(
        "interview_mux.artifact_dependency_graph.upstream_closure",
        lambda _stage: [],
    )
    monkeypatch.setattr(
        "interview_mux.artifact_dependency_graph.transitive_invalidate",
        lambda _stage: set(),
    )
    monkeypatch.setattr(agenda_mod, "stage_outputs_present", lambda _ctx, _up: True)
    monkeypatch.setattr(agenda_mod, "skipped_stages", lambda _ctx: set())
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.upstream_stale_blockers",
        lambda _ctx, _stage: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.mix_epoch_block",
        lambda _ctx: "music_incomplete",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid != "mmaudio_sfx",
    )
    plan = agenda_mod.resolve_stage_plan(ctx, "mix")
    assert "mix_epoch:music_incomplete" in plan["blockers"]
    assert plan["recommended_next"] == "mmaudio_sfx"
