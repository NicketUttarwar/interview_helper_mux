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
            "edl",
            RuntimeError(
                'clips[0]: vo_pickup line_id "vo_preface_episode_orientation" '
                'targets_segment_id "seg_002" does not match gap_report "seg_013"'
            ),
        )
        == "orientation_target_mismatch"
    )
    assert classify_error_class("edl", RuntimeError("naked seam: seg_033→seg_034")) == "naked_seam"
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
    second = handle_stage_failure(
        ctx,
        "mix",
        RuntimeError("Mix gate: missing WAV for asset_id show_theme_v1_motif"),
    )
    assert second.status == "escalate"
    assert second.resume_stage == "music_palette_compose"
