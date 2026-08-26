"""Downstream delivery blockers after the transitions skip/persist deadlock.

These tests reconstruct the exec_087 full-auto shape (G1 chatterbox, palettes SDP,
missing theme WAVs, hollow skip rules) and prove which remaining stages still
stop progress. They do not touch the live execution.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from interview_mux.artifact_lifecycle import LifecyclePhase, run_phase_checks
from interview_mux.homunculus.agenda import (
    remaining_stages,
    skip_stage,
    stage_outputs_present,
    unskip_hollow_stages,
)
from interview_mux.homunculus.budget import LimitExhausted
from interview_mux.llm_flow_hardening import FLOW_CRITICAL_LLM_STAGES
from interview_mux.opening_orientation import is_episode_orientation, validate_opening_orientation
from interview_mux.run_context import RunContext
from interview_mux.stage_input_checks import collect_stage_input_issues
from interview_mux.v2.config import DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, sound_design_plan_with, write_fixture_vo_wav


@pytest.fixture(autouse=True)
def _isolate_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))


def _ctx(tmp_path: Path, run_id: str = "exec_blockers") -> RunContext:
    ctx = isolated_run_ctx(tmp_path, run_id)
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "run_mode": "full-auto",
            "gap_fill_mode": "active",
            "gap_vo_delivery": "chatterbox",
        },
        skip_handoff=True,
    )
    return ctx


def _tiny_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * 4800)


def _theme_sdp() -> dict:
    return sound_design_plan_with(
        assets=[
            {
                "asset_id": "show_theme_v1_motif",
                "role": "theme_cold_open",
                "description": "Show motif for the cold open.",
                "duration_seconds": 12,
            },
            {
                "asset_id": "show_theme_v1_underscore_loop",
                "role": "theme_underscore",
                "description": "Looping underscore bed.",
                "duration_seconds": 20,
            },
        ]
    )


def _g1_gap_report() -> dict:
    return {
        "opening_orientation": {
            "line_id": "vo_preface_precision_oncology",
            "sequence": "intro_music_body",
            "required": True,
        },
        "interviewer_lines": [
            {
                "line_id": "vo_preface_precision_oncology",
                "delivery": "synthesize",
                "gap_type": "opening_orientation",
                "severity": "critical",
                "placement": "before",
                "targets_segment_id": "seg_004",
                "orientation_missions": [
                    "guest_identity",
                    "conversation_topic",
                    "listener_stakes",
                ],
                "opening_sequence": "intro_music_body",
                "text": "This conversation with Mohan Utawar examines blood-based tests.",
            },
            {
                "line_id": "vo_layup_seg_009",
                "delivery": "synthesize",
                "gap_type": "context",
                "severity": "high",
                "placement": "before",
                "targets_segment_id": "seg_009",
                "text": "OneCell claims that its capture method improves purity.",
            },
            {
                "line_id": "vo_layup_seg_037",
                "delivery": "synthesize",
                "gap_type": "context",
                "severity": "high",
                "placement": "before",
                "targets_segment_id": "seg_037",
                "text": "OneCell describes an LDT route through a certified laboratory.",
            },
            {
                "line_id": "vo_layup_seg_070",
                "delivery": "synthesize",
                "gap_type": "context",
                "severity": "high",
                "placement": "before",
                "targets_segment_id": "seg_070",
                "text": "OneCell.ai says it plans to build from biopharma use.",
            },
        ],
    }


def test_vo_synthesize_skip_refused_before_spoken_pairs_exist(tmp_path: Path) -> None:
    """Skip without transitions is a hole — later pairs must still be synthesizable."""
    from interview_mux.transition_vo import current_transition_pairs_missing

    ctx = _ctx(tmp_path, "vo_premature")
    with pytest.raises(RuntimeError, match="cannot skip vo_synthesize"):
        skip_stage(ctx, "vo_synthesize", reason="no pairs yet")
    assert not ctx.is_done("vo_synthesize")
    assert not ctx.artifact_exists("mastering/vo_synthesize.json")

    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_055",
                    "before_segment_id": "seg_058",
                    "text": "Meanwhile the trial enrolled.",
                    "type": "bridge",
                }
            ]
        },
        skip_handoff=True,
    )
    dropped = unskip_hollow_stages(ctx, ["vo_synthesize"])
    assert dropped == []
    assert "vo_synthesize" in remaining_stages(ctx, "delivery")
    assert current_transition_pairs_missing(ctx)


def test_sound_design_plan_skip_refused_when_palettes_wrote_same_path(
    tmp_path: Path,
) -> None:
    """Palettes SDP is not the delivery producer — skip stays refused until both exist."""
    ctx = _ctx(tmp_path, "sdp_shared")
    palettes = _theme_sdp()
    ctx.write_json("understanding/sound_design_plan.json", palettes, skip_handoff=True)
    with pytest.raises(RuntimeError, match="cannot skip transitions"):
        skip_stage(ctx, "transitions", reason="not written")
    with pytest.raises(RuntimeError, match="cannot skip sound_design_plan"):
        skip_stage(ctx, "sound_design_plan", reason="file already there")
    assert not ctx.is_done("sound_design_plan")
    assert "sound_design_plan" in remaining_stages(ctx, "delivery")
    issues = collect_stage_input_issues(ctx, "sound_design_plan")
    assert any("transitions.json" in i.message for i in issues)


def test_edl_blocked_on_g1_and_transitions(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "g1_edl")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_004"]}, skip_handoff=True)
    ctx.write_json("understanding/gap_report.json", _g1_gap_report(), skip_handoff=True)
    issues = collect_stage_input_issues(ctx, "edl")
    msgs = " | ".join(i.message for i in issues)
    assert "transitions.json" in msgs
    assert "vo_preface_precision_oncology" in msgs
    assert "vo_layup_seg_009" in msgs
    assert "vo_layup_seg_037" in msgs
    assert "vo_layup_seg_070" in msgs


def test_opening_orientation_requires_preface_wav_on_edl(tmp_path: Path) -> None:
    gap = _g1_gap_report()
    preface = next(x for x in gap["interviewer_lines"] if is_episode_orientation(x))
    assert preface["line_id"] == "vo_preface_precision_oncology"
    errors = validate_opening_orientation(gap_report=gap, edl={"clips": []})
    assert any("opening_orientation_audible_count" in e for e in errors)


def test_edl_narrative_audit_skip_refused_without_artifact(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path, "ena_skip")
    assert "edl_narrative_audit" in FLOW_CRITICAL_LLM_STAGES
    from interview_mux.homunculus.agenda import PROTECTED_DELIVERY_OUTPUTS

    assert "edl_narrative_audit" in PROTECTED_DELIVERY_OUTPUTS
    with pytest.raises(RuntimeError, match="cannot skip edl_narrative_audit"):
        skip_stage(ctx, "edl_narrative_audit", reason="conductor whim")
    assert not ctx.is_done("edl_narrative_audit")
    assert not stage_outputs_present(ctx, "edl_narrative_audit")


def test_music_and_mix_skip_refused_until_theme_wavs_exist(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "theme_skip")
    ctx.write_json("understanding/sound_design_plan.json", _theme_sdp(), skip_handoff=True)
    for stage in ("music_palette_compose", "sfx_prompt_craft", "mmaudio_sfx", "mix"):
        with pytest.raises(RuntimeError, match="cannot skip"):
            skip_stage(ctx, stage, reason="conductor whim")
    _tiny_wav(ctx.path("sound_design/assets/show_theme_v1_motif.wav"))
    _tiny_wav(ctx.path("sound_design/assets/show_theme_v1_underscore_loop.wav"))
    with pytest.raises(RuntimeError, match="cannot skip mix"):
        skip_stage(ctx, "mix", reason="wavs on disk")


def test_mmaudio_requires_sfx_prompts_and_assembly_preview(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "mmaudio_inputs")
    ctx.write_json("understanding/sound_design_plan.json", _theme_sdp(), skip_handoff=True)
    issues = collect_stage_input_issues(ctx, "mmaudio_sfx")
    msgs = " | ".join(i.message for i in issues)
    assert "sfx_prompts.json" in msgs
    assert "assembly preview" in msgs.lower() or "assembly_preview" in msgs


def test_master_finalize_requires_autopsy_and_render_ledger(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "finalize_inputs")
    issues = collect_stage_input_issues(ctx, "master_finalize")
    msgs = " | ".join(i.message for i in issues)
    assert "assembly.wav" in msgs
    assert "seam_autopsy.json" in msgs
    assert "render_ledger.json" in msgs


def test_master_transcript_hard_requires_edl_and_master(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "transcript_inputs")
    with pytest.raises(RuntimeError, match="cannot skip edl"):
        skip_stage(ctx, "edl", reason="skip without edl.json")
    assert not ctx.is_done("edl")
    issues = collect_stage_input_issues(ctx, "master_transcript_build")
    msgs = " | ".join(i.message for i in issues)
    assert "master.wav" in msgs
    assert "edl.json" in msgs


def test_cover_prompt_hard_requires_episode_meta(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "cover_prompt")
    with pytest.raises(RuntimeError, match="cannot skip episode_meta_build"):
        skip_stage(ctx, "episode_meta_build", reason="skip meta")
    pre = run_phase_checks(ctx, "episode_cover_prompt_craft", LifecyclePhase.PRESTAGE)
    assert any("episode_meta.json" in msg for msg in pre)


def test_listen_delight_fail_early_default_is_false() -> None:
    from interview_mux.listen_delight import listen_delight_cfg
    from interview_mux.junction_snip_qa import junction_snip_cfg

    delight = listen_delight_cfg()
    assert str(delight.get("mode") or "") == "authoritative"
    assert delight.get("fail_early_at_audit_stage") is False
    assert str(junction_snip_cfg().get("mode") or "") == "authoritative"


def test_g1_wavs_clear_edl_vo_gate_but_not_transitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.vo_speech_qa.vo_passes_speech_qa",
        lambda *_a, **_k: True,
    )
    ctx = _ctx(tmp_path, "g1_wavs")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_004"]}, skip_handoff=True)
    ctx.write_json("understanding/gap_report.json", _g1_gap_report(), skip_handoff=True)
    for lid in (
        "vo_preface_precision_oncology",
        "vo_layup_seg_009",
        "vo_layup_seg_037",
        "vo_layup_seg_070",
    ):
        write_fixture_vo_wav(ctx.path(f"vo_pickup/{lid}.wav"))
    issues = collect_stage_input_issues(ctx, "edl")
    msgs = " | ".join(i.message for i in issues)
    assert "G1 VO" not in msgs
    assert "transitions.json" in msgs


def test_catalog_skip_without_output_on_empty_delivery_ctx(tmp_path: Path) -> None:
    """Every delivery producer is refuse-skip or skip-without-done — never premature done."""
    from interview_mux.homunculus.agenda import PROTECTED_DELIVERY_OUTPUTS

    premature_done: list[str] = []
    hollow_skip: list[str] = []
    refused: list[str] = []
    skipped_without_done: list[str] = []
    for stage in DELIVERY_ORDER:
        fresh = _ctx(tmp_path / stage, f"cat_{stage}")
        try:
            skip_stage(fresh, stage, reason="catalog probe")
        except RuntimeError:
            refused.append(stage)
            continue
        present = stage_outputs_present(fresh, stage)
        if fresh.is_done(stage) and not present:
            premature_done.append(stage)
        elif not present:
            hollow_skip.append(stage)
            if not fresh.is_done(stage):
                skipped_without_done.append(stage)
    assert premature_done == []
    assert "transitions" in refused
    assert "sound_design_plan" in refused
    assert "vo_synthesize" in refused
    assert "edl" in refused
    assert "edl_narrative_audit" in refused
    assert "listen_delight_audit" in refused
    assert "assembly_preview" in refused
    assert "junction_snip_qa" in refused
    assert "master_finalize" in refused
    assert "episode_meta_build" in refused
    assert "episode_cover_prompt_craft" in refused
    assert "podcast_encode_mp3" in refused
    assert "podcast_publish" in refused
    for stage in PROTECTED_DELIVERY_OUTPUTS:
        assert stage in refused or stage in skipped_without_done
    for stage in skipped_without_done:
        assert stage not in premature_done


def test_conductor_budget_exhausted_walks_remaining_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.homunculus.agenda import run_homunculus_phase, write_agenda
    from interview_mux.homunculus.budget import LimitExhausted

    ctx = _ctx(tmp_path, "walk_cap")
    for rel in (
        "understanding/source_topology.json",
        "segments/boundaries.json",
        "segments/manifest.json",
        "understanding/content_brief.json",
        "understanding/gap_evaluations.json",
        "understanding/gap_report.json",
        "understanding/delivery_brief.json",
    ):
        dest = ctx.path(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("{}", encoding="utf-8")
        producer = {
            "understanding/source_topology.json": "source_topology_build",
            "segments/boundaries.json": "boundary_detection",
            "segments/manifest.json": "segment_classification",
            "understanding/content_brief.json": "content_brief_reanchor",
            "understanding/gap_evaluations.json": "missing_framing",
            "understanding/gap_report.json": "gap_framing_compose",
            "understanding/delivery_brief.json": "delivery_brief_build",
        }[rel]
        ctx.mark_done(producer, force=True)
    write_agenda(ctx, "delivery", ["transitions"], source="test")
    ran: list[str] = []

    def _boom(*_a: object, **_k: object) -> None:
        raise LimitExhausted("conductor_turn", "cap", {"conductor_turn": 198})

    monkeypatch.setattr("interview_mux.homunculus.loop.run_conductor", _boom)
    monkeypatch.setattr(
        "interview_mux.pipeline.run_single_stage",
        lambda _c, stage: ran.append(stage),
    )
    run_homunculus_phase(ctx, "delivery", ["transitions"])
    assert "transitions" in ran
    assert not ctx.artifact_exists("master/master.wav")


def test_skip_with_artifact_never_marks_done(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "skip_no_done")
    ctx.write_json("master/transitions.json", {"transitions": []}, skip_handoff=True)
    doc = skip_stage(ctx, "transitions", reason="empty bridges ok")
    assert "transitions" in doc["skipped"]
    assert not ctx.is_done("transitions")
    assert "transitions" not in remaining_stages(ctx, "delivery")


def test_pre_ranking_fuse_not_satisfied_by_first_pass_audit(tmp_path: Path) -> None:
    """exec_1071 loop: first-pass audit must not drop pre_ranking from remaining_stages."""
    from interview_mux.homunculus.agenda import remaining_stages, skip_stage, stage_outputs_present
    from interview_mux.llm_flow_hardening import maybe_require_upstream_llm_progress

    ctx = _ctx(tmp_path, "pre_rank_fuse")
    ctx.write_json(
        "analysis/connector_fuse_audit.json",
        {"version": 1, "pass_id": "post_sanitize", "stay_independent": []},
        skip_handoff=True,
    )
    ctx.write_json(
        "analysis/low_conf_islands.json",
        {"island_count": 1, "islands": []},
        skip_handoff=True,
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001"]}, skip_handoff=True)
    ctx.mark_done("topic_coverage_audit", force=True)
    ctx.mark_done("narrative_arc_plan", force=True)
    ctx.mark_done("chapter_close_hitch", force=True)
    ctx.mark_done("full_master_ranking", force=True)
    ctx.mark_done("connector_fuse_pass", force=True)

    assert stage_outputs_present(ctx, "connector_fuse_pass") is True
    assert stage_outputs_present(ctx, "connector_fuse_pass_pre_ranking") is False
    remaining = remaining_stages(ctx, "delivery")
    assert "connector_fuse_pass_pre_ranking" in remaining
    with pytest.raises(RuntimeError, match="language-island artifacts missing"):
        skip_stage(ctx, "connector_fuse_pass_pre_ranking", reason="first-pass audit")

    maybe_require_upstream_llm_progress(ctx, "connector_fuse_pass_pre_ranking")
    with pytest.raises(SystemExit, match="connector_fuse_pass_pre_ranking"):
        maybe_require_upstream_llm_progress(ctx, "full_master_ranking")

    ctx.write_json(
        "analysis/connector_fuse_rounds.json",
        {"version": 1, "pass_id": "pre_ranking", "rounds": [], "total_applied": 0},
        skip_handoff=True,
    )
    assert stage_outputs_present(ctx, "connector_fuse_pass_pre_ranking") is True
    assert "connector_fuse_pass_pre_ranking" not in remaining_stages(ctx, "delivery")


def test_incomplete_layup_plan_stays_in_remaining(tmp_path: Path) -> None:
    """Partial/restart layup plan must not skip to selection_framing_apply."""
    ctx = _ctx(tmp_path, "layup_partial")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001a"]}, skip_handoff=True)
    ctx.write_json(
        "understanding/nugget_layup_plan.json",
        {
            "ordered_segment_ids": ["seg_001a"],
            "layups": [],
            "warnings": ["compose_restart"],
        },
        skip_handoff=True,
    )
    for sid in (
        "topic_coverage_audit",
        "narrative_arc_plan",
        "chapter_close_hitch",
        "connector_fuse_pass_pre_ranking",
        "full_master_ranking",
        "air_script_compose",
        "nugget_corpus_mine",
        "information_package_plan",
    ):
        ctx.mark_done(sid, force=True)
        if sid == "connector_fuse_pass_pre_ranking":
            ctx.write_json(
                "analysis/connector_fuse_rounds.json",
                {"version": 1, "pass_id": "pre_ranking", "rounds": [], "total_applied": 0},
                skip_handoff=True,
            )

    assert stage_outputs_present(ctx, "nugget_layup_compose") is False
    remaining = remaining_stages(ctx, "delivery")
    assert "nugget_layup_compose" in remaining
    assert remaining.index("nugget_layup_compose") < remaining.index("selection_framing_apply")

    ctx.mark_done("nugget_layup_compose", force=True)
    assert stage_outputs_present(ctx, "nugget_layup_compose") is True
    assert "nugget_layup_compose" not in remaining_stages(ctx, "delivery")


def test_stale_extra_ids_keep_layup_in_remaining(tmp_path: Path) -> None:
    """CTA-pruned selection with leftover outro children must re-run compose."""
    ctx = _ctx(tmp_path, "layup_extras")
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_002", "seg_005", "seg_065"]},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/nugget_layup_plan.json",
        {
            "ordered_segment_ids": [
                "seg_002",
                "seg_005",
                "seg_065",
                "seg_068b",
                "seg_068l",
            ],
            "layups": [{"target_segment_id": "seg_005", "text": "Then the assay."}],
        },
        skip_handoff=True,
    )
    for sid in (
        "topic_coverage_audit",
        "narrative_arc_plan",
        "chapter_close_hitch",
        "connector_fuse_pass_pre_ranking",
        "full_master_ranking",
        "air_script_compose",
        "nugget_corpus_mine",
        "information_package_plan",
        "nugget_layup_compose",
    ):
        ctx.mark_done(sid, force=True)
        if sid == "connector_fuse_pass_pre_ranking":
            ctx.write_json(
                "analysis/connector_fuse_rounds.json",
                {"version": 1, "pass_id": "pre_ranking", "rounds": [], "total_applied": 0},
                skip_handoff=True,
            )

    assert stage_outputs_present(ctx, "nugget_layup_compose") is False
    remaining = remaining_stages(ctx, "delivery")
    assert "nugget_layup_compose" in remaining
    from interview_mux.stage_completion import stage_artifact_incompleteness

    reason = stage_artifact_incompleteness(ctx, "nugget_layup_compose")
    assert reason and "stale=" in reason


def test_conductor_budget_exhausted_when_turn_cap_hit(tmp_path: Path) -> None:
    from interview_mux.homunculus.budget import (
        check_dispatch,
        max_conductor_turns,
        remaining_conductor_turns,
    )
    from interview_mux.homunculus.ledger import append_ledger

    ctx = _ctx(tmp_path, "budget")
    cap = max_conductor_turns()
    for _ in range(cap):
        append_ledger(ctx, {"kind": "conductor_turn", "identity": "conductor_turn"})
    assert remaining_conductor_turns(ctx) == 0
    with pytest.raises(LimitExhausted, match="conductor_turn"):
        check_dispatch(ctx, identity="conductor_turn", kind="conductor_turn")


def test_delivery_sdp_fingerprint_survives_schema(tmp_path: Path) -> None:
    """Palettes-shaped SDP without _meta is hollow; restamp must be schema-valid."""
    from interview_mux.analysis_memory import default_sound_design_plan
    from interview_mux.artifact_lifecycle import fingerprint_artifact, restamp_committed_artifact
    from interview_mux.homunculus.agenda import delivery_sdp_present
    from interview_mux.prompt_validation import validate_artifact_write

    ctx = _ctx(tmp_path, "sdp_fp")
    ctx.write_json("master/transitions.json", {"transitions": []}, skip_handoff=True)
    plan = default_sound_design_plan()
    ctx.write_json("understanding/sound_design_plan.json", plan, skip_handoff=True)
    assert delivery_sdp_present(ctx) is False

    fp = fingerprint_artifact(plan, "sound_design_plan")
    assert fp["_meta"]["producer_stage"] == "sound_design_plan"
    assert validate_artifact_write("understanding/sound_design_plan.json", fp) == []

    restamp_committed_artifact(
        ctx,
        "understanding/sound_design_plan.json",
        producer_stage="sound_design_plan",
        doc=plan,
    )
    assert delivery_sdp_present(ctx) is True


def test_host_repair_counts_orientation_omit_as_progress() -> None:
    from interview_mux.edl_narrative_remutate import HOST_REPAIR_PROGRESS_NOTES

    assert "retarget_orientation" in HOST_REPAIR_PROGRESS_NOTES
    assert "omit_episode_orientation" in HOST_REPAIR_PROGRESS_NOTES
    assert "suppress_opening_layup" in HOST_REPAIR_PROGRESS_NOTES
    assert "drop_late_intro_reset" in HOST_REPAIR_PROGRESS_NOTES
    assert "drop_post_coda_reverse_jump" in HOST_REPAIR_PROGRESS_NOTES
    assert "prune_stale_transitions" in HOST_REPAIR_PROGRESS_NOTES
    assert "align_selection_chapters" in HOST_REPAIR_PROGRESS_NOTES
    assert "repair_coverage_for_selection" in HOST_REPAIR_PROGRESS_NOTES
    assert "align_narrative_plan" in HOST_REPAIR_PROGRESS_NOTES
