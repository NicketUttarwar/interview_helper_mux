"""G1–G10 / C1–C3 / E1 / D1 / F1–F4 delivery guardrails (exec_3751)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    CHECKPOINT_REL,
    WASTED_WORK_REL,
    delivery_stable_for_music,
    ensure_listen_delight_waiver_unattended,
    filter_delivery_candidates,
    invalidation_is_structural,
    listen_delight_waived_unattended,
    maybe_restore_master_bundle,
    mix_epoch_block,
    music_epoch_complete,
    music_skip_allowed,
    premature_cap_hard_pin,
    reconcile_delivery_batch,
    record_wasted_work,
    resolve_assembly_stale_resume,
    resolve_gap_report_stale_producer,
    seal_phase_a_if_stable,
    seed_stage_complete,
    stamp_delivery_epoch,
    upstream_stale_blockers,
    vo_synthesize_stability_block,
)
from interview_mux.homunculus.agenda import remaining_stages
from interview_mux.journey_state import compute_milestones
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import seed_stage_complete as seed_complete_alias
from run_fixtures import isolated_run_ctx, mark_done_raw


def _write_raw(ctx: RunContext, rel: str, data: dict) -> None:
    path = ctx.path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _ctx(tmp_path: Path, name: str = "gdr") -> RunContext:
    return isolated_run_ctx(tmp_path, name)


def test_seed_complete_blocks_hollow_assembly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "hollow_asm")
    mark_done_raw(ctx, "assembly_preview")
    assert ctx.is_done("assembly_preview")
    assert seed_stage_complete(ctx, "assembly_preview") is False
    assert seed_complete_alias(ctx, "assembly_preview") is False
    remaining = remaining_stages(ctx, "delivery")
    assert "assembly_preview" in remaining
    filtered = filter_delivery_candidates(ctx, remaining)
    assert "mmaudio_sfx" not in filtered


def test_music_blocked_without_assembly_wav(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "music_block")
    assert music_skip_allowed(ctx, "mmaudio_sfx") is False
    from interview_mux.homunculus.agenda import _refuse_music_before_assembly

    with pytest.raises(RuntimeError, match="assembly audio missing"):
        _refuse_music_before_assembly(ctx, "mmaudio_sfx", action="run")
    filtered = filter_delivery_candidates(ctx, ["mmaudio_sfx", "nugget_layup_compose"])
    assert "mmaudio_sfx" not in filtered


def test_reconcile_clears_hollow_music_before_walk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "reconcile")
    mark_done_raw(ctx, "mmaudio_sfx")
    mark_done_raw(ctx, "mix")
    cleared = reconcile_delivery_batch(ctx)
    assert "mmaudio_sfx" in cleared or not ctx.is_done("mmaudio_sfx")
    assert not seed_stage_complete(ctx, "mmaudio_sfx")


def test_sdp_skip_still_requires_assembly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "sdp_skip")
    _write_raw(ctx, "understanding/sound_design_plan.json", {"assets": []})
    assert music_skip_allowed(ctx, "music_palette_compose") is False
    preview = ctx.path("master", "assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF" + b"\x00" * 64)
    # Still no seated outputs — skip refused.
    assert music_skip_allowed(ctx, "mmaudio_sfx") is False


def test_music_deferred_until_delivery_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g5")
    ok, reason = delivery_stable_for_music(ctx)
    assert ok is False
    assert reason
    filtered = filter_delivery_candidates(
        ctx, ["music_palette_compose", "mmaudio_sfx", "nugget_layup_compose"]
    )
    assert "mmaudio_sfx" not in filtered
    assert "music_palette_compose" not in filtered


def test_g1_milestone_tracks_check_g1_vo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g6")
    ctx.write_json(
        "run_meta.json",
        {"journey_milestones": {"g1_complete": True}, "homunculus_version": "0.1.0"},
    )
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_open",
                    "delivery": "synthesize",
                    "severity": "high",
                    "omit": False,
                    "text": "Welcome to the conversation.",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                }
            ]
        },
    )
    ms = compute_milestones(ctx)
    assert ms["g1_complete"] is False


def test_premature_cap_pins_not_advances(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g7")
    pinned = premature_cap_hard_pin(ctx, "assembly_preview")
    assert pinned == "assembly_preview" or pinned in {
        "topic_coverage_audit",
        "nugget_layup_compose",
        "assembly_preview",
        "vo_synthesize",
        "edl",
    }
    assert pinned != "master_transcript_build"
    assert pinned != "mmaudio_sfx"


def test_premature_cap_heal_exception_never_falls_to_consumer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-08 / XC-PREMATURE: heal_navigate throw → last safe pin, not master_finalize."""
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "d08_premature")
    _write_raw(ctx, "master/selection.json", {"ordered_segment_ids": ["a"]})

    def _boom(*_a, **_k):
        raise RuntimeError("heal_navigate fixture failure")

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.heal_navigate",
        _boom,
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.canonical_resume_pin",
        lambda *_a, **_k: "edl",
    )
    pinned = premature_cap_hard_pin(ctx, "master_finalize", message="fixture")
    assert pinned != "master_finalize"
    assert pinned == "edl"


def test_premature_cap_pins_ranking_producer_when_selection_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EDL thrash with no master/selection.json must pin topic_coverage_audit, not edl."""
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g7_no_sel")
    assert not ctx.artifact_exists("master/selection.json")
    pinned = premature_cap_hard_pin(ctx, "edl")
    assert pinned == "topic_coverage_audit"


def test_premature_cap_pins_before_edl_when_selection_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G1 WAV then from_stage=edl must still pin the incomplete producer (not EDL)."""
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g7_sel_no_trans")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    pinned = premature_cap_hard_pin(ctx, "edl")
    from interview_mux.v2.config import DELIVERY_ORDER

    assert pinned != "edl"
    assert DELIVERY_ORDER.index(pinned) < DELIVERY_ORDER.index("edl")


def test_premature_cap_keeps_music_palette_not_edl_narrative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_5402: music resume must not hard-pin back to edl_narrative_audit."""
    from interview_mux.llm_flow_hardening import _earliest_incomplete_seed_stage

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g7_music_vs_narrative")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    preview = ctx.final_path("master", "assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF....WAVEfmt ")

    def _seed(_ctx: RunContext, sid: str) -> bool:
        # Skewed Phase A: narrative/edl unmarked, assembly+listen complete, music open.
        return sid not in {
            "edl_narrative_audit",
            "edl",
            "music_palette_compose",
            "sfx_prompt_craft",
            "mmaudio_sfx",
        }

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        _seed,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (False, "phase_a_unsealed"),
    )
    # Predicate that caused the thrash: earliest incomplete before music is narrative.
    assert (
        _earliest_incomplete_seed_stage(ctx, "music_palette_compose")
        == "edl_narrative_audit"
    )
    pinned = premature_cap_hard_pin(ctx, "music_palette_compose")
    assert pinned == "music_palette_compose"
    assert pinned != "edl_narrative_audit"


def test_promote_complete_orphan_stamps_edl_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import promote_complete_orphan_stage_done

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "orphan_edl_promote")
    _write_raw(
        ctx,
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_1"],
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_1",
                    "source_start_ms": 0,
                    "source_end_ms": 500,
                    "duration_ms": 500,
                    "timeline_start_ms": 0,
                }
            ],
            "_meta": {"producer_stage": "edl", "stale": False},
        },
    )
    assert not ctx.is_done("edl")
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _ctx, sid: sid == "edl",
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, sid: None,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_completeness.artifact_status",
        lambda *_a, **_k: "complete",
    )
    promoted = promote_complete_orphan_stage_done(ctx, ("edl",))
    assert "edl" in promoted
    assert ctx.is_done("edl")


def test_promote_complete_orphan_stamps_assembly_preview_wav(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_5404: WAV present + missing .stage_done must promote (STAGE_ARTIFACT map)."""
    from interview_mux.delivery_guardrails import promote_complete_orphan_stage_done

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "orphan_asm_promote")
    preview = ctx.final_path("master", "assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF" + b"\x00" * 4096)
    assert not ctx.is_done("assembly_preview")
    promoted = promote_complete_orphan_stage_done(ctx, ("assembly_preview",))
    assert "assembly_preview" in promoted
    assert ctx.is_done("assembly_preview")
    assert seed_stage_complete(ctx, "assembly_preview") is True


def test_vo_synth_blocked_when_g1_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g8")
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_open",
                    "delivery": "synthesize",
                    "severity": "high",
                    "text": "Hello there.",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                }
            ]
        },
    )
    remaining = remaining_stages(ctx, "delivery")
    filtered = filter_delivery_candidates(ctx, remaining)
    assert "edl" not in filtered
    assert "edl_narrative_audit" not in filtered
    block = vo_synthesize_stability_block(ctx)
    assert block in {"g1_vo_open", "nugget_layup_compose", "transitions", "gap_report_stale_from_layup"}
    from interview_mux.delivery_guardrails import resolve_vo_synth_seed_resume

    assert resolve_vo_synth_seed_resume("g1_vo_open") == "vo_line_adjudicate"
    assert resolve_vo_synth_seed_resume("transitions_stale_from_layup") == "transitions"
    assert resolve_vo_synth_seed_resume("gap_report_stale_from_layup") == "nugget_layup_compose"
    assert resolve_vo_synth_seed_resume("transitions") == "transitions"


def test_resolve_vo_synth_seed_resume_never_returns_fake_stage() -> None:
    from interview_mux.delivery_guardrails import (
        VO_SYNTH_SEED_SENTINELS,
        resolve_vo_synth_seed_resume,
    )
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    pipeline = set(ANALYSIS_ORDER) | set(DELIVERY_ORDER)
    for sentinel, resume in VO_SYNTH_SEED_SENTINELS.items():
        assert sentinel not in pipeline
        assert resolve_vo_synth_seed_resume(sentinel) == resume
        assert resume in pipeline


def test_mmaudio_blocked_on_stale_sound_design(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g9")
    _write_raw(
        ctx,
        "understanding/sound_design_plan.json",
        {"assets": [], "_meta": {"stale": True, "stale_reason": "invalidated_by:nugget_layup_compose"}},
    )
    blockers = upstream_stale_blockers(ctx, "mmaudio_sfx")
    assert "sound_design_plan" in blockers


def test_upstream_stale_blockers_edl_sees_stale_transitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "stale_tr_edl")
    _write_raw(
        ctx,
        "master/transitions.json",
        {
            "transitions": [],
            "_meta": {
                "stale": True,
                "stale_reason": "invalidated_by:nugget_layup_compose",
            },
        },
    )
    for consumer in ("edl", "edl_narrative_audit", "assembly_preview", "vo_synthesize"):
        blockers = upstream_stale_blockers(ctx, consumer)
        assert "transitions" in blockers, consumer



def test_transcribe_not_rerun_after_g0_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g10")
    from interview_mux.delivery_guardrails import prepare_fingerprint_blocks_rerun
    from interview_mux.homunculus.runtime import dispatch_stage

    ctx.write_json("transcript/full.json", {"utterances": [{"text": "hello", "speaker": "spk_0"}]})
    ctx.write_json("ingest/transcript.json", {"utterances": [{"text": "hello"}]})
    mark_done_raw(ctx, "transcript_review")
    mark_done_raw(ctx, "transcribe")
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    # Outputs present enough for prepare_outputs_present / g0_closed.
    ran: list[str] = []
    try:
        dispatch_stage(ctx, "transcribe", lambda: ran.append("ran"), source="test")
    except RuntimeError as exc:
        assert "G0 is closed" in str(exc) or "g0" in str(exc).lower()
        assert ran == []
        return
    blocked = prepare_fingerprint_blocks_rerun(ctx, "transcribe")
    assert ran == [] or blocked == "g0_locked"


def test_heal_only_invalidation_does_not_archive_when_checkpoint_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "c1")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001", "seg_002"]})
    from interview_mux.order_hash import ordered_segment_ids_hash

    digest = ordered_segment_ids_hash(["seg_001", "seg_002"])
    ctx.write_json(
        CHECKPOINT_REL,
        {"phase": "A_sealed", "order_fingerprint": digest, "selection_fingerprint": digest},
    )
    preview = ctx.path("master", "assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF" + b"\x00" * 64)
    assert invalidation_is_structural(ctx, "nugget_layup_compose") is False
    assert invalidation_is_structural(ctx, "edl") is True


def test_wasted_work_and_phase_seal_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "d1")
    record_wasted_work(ctx, event="music_deferred", stage="mmaudio_sfx", detail={"reason": "assembly_missing"})
    assert ctx.artifact_exists(WASTED_WORK_REL)
    doc = ctx.read_json(WASTED_WORK_REL)
    assert doc["events"][0]["event"] == "music_deferred"


def test_lazy_musicgen_skips_unreferenced_slots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "e3")
    from interview_mux.stages.sfx_mmaudio import _collect_generation_items

    _write_raw(
        ctx,
        "understanding/sound_design_plan.json",
        {
            "assets": [
                {"asset_id": "theme_used", "role": "theme_cold_open"},
                {"asset_id": "theme_unused", "role": "theme_alt"},
            ],
            "flow_plans": {
                "podcast": {"cues": [{"asset_id": "theme_used", "role": "theme_cold_open"}]}
            },
        },
    )
    items = _collect_generation_items(ctx=ctx, profile="podcast", fallback_cues=[])
    ids = {str(i.get("asset_id")) for i in items}
    assert "theme_used" in ids
    assert "theme_unused" not in ids
    assert ctx.artifact_exists(WASTED_WORK_REL)


def test_exec_3751_replay_hollow_assembly_and_stale_sdp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ASSETS-free replay of O1 + stale SDP — MusicGen must not be a candidate."""
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "exec_3751_replay")
    mark_done_raw(ctx, "assembly_preview")
    _write_raw(
        ctx,
        "understanding/sound_design_plan.json",
        {"assets": [{"asset_id": "show_theme_v1_motif"}], "_meta": {"stale": True}},
    )
    remaining = remaining_stages(ctx, "delivery")
    filtered = filter_delivery_candidates(ctx, remaining)
    assert "mmaudio_sfx" not in filtered
    assert seed_stage_complete(ctx, "assembly_preview") is False
    assert upstream_stale_blockers(ctx, "mmaudio_sfx")
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_open",
                    "delivery": "synthesize",
                    "severity": "high",
                    "text": "Welcome.",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                }
            ]
        },
    )
    from interview_mux.stage_completion import vo_synthesize_should_defer_done

    assert vo_synthesize_should_defer_done(ctx, "vo_synthesize")
    filtered_g1 = filter_delivery_candidates(ctx, remaining_stages(ctx, "delivery"))
    assert "edl" not in filtered_g1


def test_transitions_survive_heal_layup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "f5_tr")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001", "seg_002"]})
    from interview_mux.order_hash import ordered_segment_ids_hash

    digest = ordered_segment_ids_hash(["seg_001", "seg_002"])
    ctx.write_json(
        CHECKPOINT_REL,
        {"phase": "A_sealed", "order_fingerprint": digest, "selection_fingerprint": digest},
    )
    trans = {
        "transitions": [
            {
                "before_segment_id": "seg_001",
                "after_segment_id": "seg_002",
                "text": "And then this happened next.",
            }
        ]
    }
    dest = ctx.final_path("master", "transitions.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(trans), encoding="utf-8")
    arch = ctx.run_dir / ".archived" / "20260831T120000Z" / "master"
    arch.mkdir(parents=True)
    (arch / "transitions.json").write_text(json.dumps(trans), encoding="utf-8")
    dest.unlink()
    restored = maybe_restore_master_bundle(ctx, stage="nugget_layup_compose")
    assert ctx.artifact_exists("master/transitions.json")
    assert "master/transitions.json" in restored or ctx.read_json("master/transitions.json")


def test_mix_blocked_until_music_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "b3_mix")
    ctx.write_json(
        CHECKPOINT_REL,
        {"phase": "A_sealed", "order_fingerprint": "abc", "selection_fingerprint": "abc"},
    )
    stamp_delivery_epoch(ctx, phase_a_sealed_at="2026-08-31T00:00:00+00:00")
    assert mix_epoch_block(ctx) == "music_incomplete"
    filtered = filter_delivery_candidates(ctx, ["mix", "nugget_layup_compose"])
    assert "mix" not in filtered
    stamp_delivery_epoch(ctx, music_complete_at="2026-08-31T01:00:00+00:00")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (True, ""),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _ctx: True,
    )
    assert mix_epoch_block(ctx) is None


def test_hollow_mmaudio_qa_does_not_complete_music_epoch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "hollow_qa")
    ctx.write_json(
        CHECKPOINT_REL,
        {"phase": "A_sealed", "order_fingerprint": "abc", "selection_fingerprint": "abc"},
    )
    stamp_delivery_epoch(ctx, phase_a_sealed_at="2026-08-31T00:00:00+00:00")
    _write_raw(ctx, "sound_design/mmaudio_qa.json", {"assets": [], "status": "complete"})
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (True, ""),
    )
    for sid in ("music_palette_compose", "sfx_prompt_craft", "mmaudio_sfx"):
        mark_done_raw(ctx, sid)
    assert music_epoch_complete(ctx) is False
    assert mix_epoch_block(ctx) == "music_incomplete"


def test_music_complete_stamp_survives_cleared_stage_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Orphan/heal cleared MUSIC_BEFORE_MIX markers — trust music_complete_at + SDP WAVs."""
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "music_stamp_trust")
    ctx.write_json(
        CHECKPOINT_REL,
        {"phase": "A_sealed", "order_fingerprint": "abc", "selection_fingerprint": "abc"},
    )
    stamp_delivery_epoch(
        ctx,
        phase_a_sealed_at="2026-08-31T00:00:00+00:00",
        music_complete_at="2026-08-31T01:00:00+00:00",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (False, "vo_adjudicate_incomplete"),
    )
    monkeypatch.setattr(
        "interview_mux.sdp_cross_validate.missing_sdp_asset_wavs",
        lambda _ctx: [],
    )
    assert music_epoch_complete(ctx) is True
    assert mix_epoch_block(ctx) is None
    for sid in ("music_palette_compose", "sfx_prompt_craft", "mmaudio_sfx"):
        assert ctx.is_done(sid)


def test_safe_mix_resume_routes_missing_sdp_wavs_to_mmaudio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import safe_mix_resume_stage

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "missing_sdp_wavs")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (True, ""),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, _sid: True,
    )
    monkeypatch.setattr(
        "interview_mux.sdp_cross_validate.missing_sdp_asset_wavs",
        lambda _ctx: ["theme_missing_bed"],
    )
    assert safe_mix_resume_stage(ctx) == "mmaudio_sfx"


def test_safe_mix_resume_routes_on_a_roll_residuals_to_junction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import (
        CriticalResidualView,
        safe_mix_resume_stage,
    )

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "mix_on_a_roll")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.critical_residual_view",
        lambda _ctx: CriticalResidualView(
            count=3, kinds=("on_a_roll",), sources=("junction_findings",)
        ),
    )
    assert safe_mix_resume_stage(ctx) == "junction_snip_qa"


def test_listen_delight_waiver_unattended(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "ld_waiver")
    ctx.write_json("run_meta.json", {"full_auto": True, "homunculus_version": "0.1.0"})
    _write_raw(ctx, "mastering/listen_delight_audit.json", {"status": "complete", "scores": {}})
    assert ensure_listen_delight_waiver_unattended(ctx) is True
    assert listen_delight_waived_unattended(ctx) is True


def test_phase_a_seal_writes_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "seal_a")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (True, ""),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: True,
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001"]})
    preview = ctx.path("master", "assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF" + b"\x00" * 64)
    row = seal_phase_a_if_stable(ctx)
    assert row is not None
    assert ctx.artifact_exists(CHECKPOINT_REL)
    assert row.get("phase") == "A_sealed"


def test_phase_a_seal_refuses_thin_layup_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-05: hollow layup file + green EDL/WAV/delight must not seal."""
    from interview_mux.delivery_guardrails import phase_a_sealed

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "c05_thin_layup")
    _write_raw(ctx, "understanding/nugget_layup_plan.json", {"slots": []})
    _write_raw(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_001"]})
    _write_raw(
        ctx,
        "master/edl.json",
        {"ordered_segment_ids": ["seg_001"], "clips": [{"segment_id": "seg_001", "duration_ms": 1000}]},
    )
    preview = ctx.path("master", "assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF" + b"\x00" * 64)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid != "nugget_layup_compose",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (False, "layup_incomplete"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.assembly_wav_present",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.listen_delight_cleared_for_progress",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.artifact_usable",
        lambda _ctx, _rel, consumer="": (True, ""),
    )
    row = seal_phase_a_if_stable(ctx)
    assert row is None
    assert not ctx.artifact_exists(CHECKPOINT_REL)
    assert phase_a_sealed(ctx) is False


def test_phase_a_seal_soft_path_does_not_rewrite_layup_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-05: layup_incomplete must never soft-rewrite to phase_a_unsealed."""
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "c05_no_rewrite")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (False, "layup_incomplete"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.assembly_wav_present",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.listen_delight_cleared_for_progress",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.artifact_usable",
        lambda _ctx, _rel, consumer="": (True, ""),
    )
    assert seal_phase_a_if_stable(ctx) is None
    assert not ctx.artifact_exists(CHECKPOINT_REL)


def test_phase_a_seal_when_layup_seed_complete_and_edl_marker_lags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-05: marker-lag soft path still seals when layup seed_complete."""
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "c05_marker_lag")
    _write_raw(
        ctx,
        "master/edl.json",
        {"ordered_segment_ids": ["seg_001"], "clips": [{"segment_id": "seg_001", "duration_ms": 1000}]},
    )
    preview = ctx.path("master", "assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF" + b"\x00" * 64)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid
        in {
            "nugget_layup_compose",
            "vo_line_adjudicate",
            "assembly_preview",
            "listen_delight_audit",
        },
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (False, "edl_incomplete"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.assembly_wav_present",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.listen_delight_cleared_for_progress",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.upstream_stale_blockers",
        lambda _ctx, _stage: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._layup_escalation_blocking",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.artifact_usable",
        lambda _ctx, _rel, consumer="": (True, ""),
    )
    monkeypatch.setattr(
        "interview_mux.gates.check_g1_vo",
        lambda _ctx: [],
    )
    row = seal_phase_a_if_stable(ctx)
    assert row is not None
    assert row.get("phase") == "A_sealed"
    assert ctx.artifact_exists(CHECKPOINT_REL)


def test_music_deferred_until_checkpoint_sealed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "seal_req")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (False, "phase_a_unsealed"),
    )
    filtered = filter_delivery_candidates(ctx, ["music_palette_compose", "mmaudio_sfx"])
    assert "mmaudio_sfx" not in filtered
    assert "music_palette_compose" not in filtered


def test_phase_a_seal_required_not_optional(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import phase_a_sealed

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "seal_opt")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid
        in {
            "nugget_layup_compose",
            "vo_line_adjudicate",
            "edl",
            "assembly_preview",
            "listen_delight_audit",
        },
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.assembly_wav_present",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.upstream_stale_blockers",
        lambda _ctx, _stage: [],
    )
    ok, reason = delivery_stable_for_music(ctx)
    assert ok is False
    assert reason == "phase_a_unsealed"
    assert phase_a_sealed(ctx) is False


def test_ship_path_ready_pins_finalize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import ship_path_ready

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "ship_pin")
    ready, _ = ship_path_ready(ctx)
    assert ready is False
    asm = ctx.path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF" + b"\x00" * 4096)
    mark_done_raw(ctx, "mix")
    mark_done_raw(ctx, "listen_delight_audit")
    _write_raw(ctx, "mastering/listen_delight_audit.json", {"status": "complete", "passed": True})
    _write_raw(ctx, "master/post_master_quality.json", {"publish_allowed": True})
    _write_raw(ctx, "master/junction_snip_qa.json", {"critical_count": 0, "residuals": []})
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda._junction_commitment_matches_assembly",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid in {"mix", "junction_snip_qa", "listen_delight_audit"},
    )
    ready, _ = ship_path_ready(ctx)
    assert ready is True
    filtered = filter_delivery_candidates(
        ctx, ["junction_snip_qa", "master_finalize", "podcast_encode_mp3"]
    )
    assert "junction_snip_qa" not in filtered
    assert "master_finalize" in filtered


def test_ship_path_ready_requires_junction_seed_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_10066: missing junction QA must not drop junction from the walk."""
    from interview_mux.delivery_guardrails import ship_path_ready

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "ship_junction_required")
    asm = ctx.path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF" + b"\x00" * 4096)
    mark_done_raw(ctx, "mix")
    mark_done_raw(ctx, "listen_delight_audit")
    _write_raw(ctx, "mastering/listen_delight_audit.json", {"status": "complete", "passed": True})
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid in {"mix", "listen_delight_audit"},
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _ctx: [],
    )
    ready, reason = ship_path_ready(ctx)
    assert ready is False
    assert reason == "junction_incomplete"
    filtered = filter_delivery_candidates(
        ctx, ["junction_snip_qa", "master_finalize"]
    )
    assert "junction_snip_qa" in filtered


def test_vo_synth_blocked_when_transitions_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g8_tr")
    block = vo_synthesize_stability_block(ctx)
    assert block in {"transitions", "nugget_layup_compose"}


def test_vo_synth_not_blocked_by_synthesize_only_g1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synthesize-delivery G1 holes are vo_synthesize's job — no g1_vo_open deadlock."""
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g8_synth_g1")
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_007",
                    "delivery": "synthesize",
                    "severity": "high",
                    "text": "Bridge the story.",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_007",
                    "placement": "before",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid in {"nugget_layup_compose", "transitions"},
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._layup_escalation_blocking",
        lambda _ctx: False,
    )
    # C-05: understanding path is SSOT; mastering soft escape removed.
    _write_raw(ctx, "understanding/nugget_layup_plan.json", {"slots": []})
    _write_raw(ctx, "master/transitions.json", {"transitions": []})
    mark_done_raw(ctx, "nugget_layup_compose")
    mark_done_raw(ctx, "transitions")
    assert vo_synthesize_stability_block(ctx) is None


def test_vo_synth_blocked_when_layup_seed_incomplete_despite_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C-05: file-exists alone must not soft-escape seed_stage_complete(layup)."""
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "c05_layup_soft")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid == "transitions",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._layup_escalation_blocking",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_record_open",
        lambda _ctx: [],
    )
    _write_raw(ctx, "understanding/nugget_layup_plan.json", {"slots": []})
    _write_raw(ctx, "mastering/nugget_layup_plan.json", {"slots": []})
    mark_done_raw(ctx, "nugget_layup_compose")
    assert vo_synthesize_stability_block(ctx) == "nugget_layup_compose"


def test_vo_synth_blocked_when_g1_record_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g8_record_g1")
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_host_record_001",
                    "delivery": "record",
                    "severity": "high",
                    "text": "Operator must record this.",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._layup_escalation_blocking",
        lambda _ctx: False,
    )
    _write_raw(ctx, "master/transitions.json", {"transitions": []})
    assert vo_synthesize_stability_block(ctx) == "g1_vo_open"


def test_seal_adjudicate_stale_when_g1_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import seal_adjudicate_stale_when_g1_green

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "seal_adj")
    _write_raw(
        ctx,
        "understanding/vo_line_adjudication.json",
        {
            "version": 1,
            "lines": [],
            "_meta": {
                "stale": True,
                "stale_reason": "invalidated_by:nugget_layup_compose",
            },
        },
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _ctx: [],
    )
    assert seal_adjudicate_stale_when_g1_green(ctx) is True
    doc = ctx.read_json("understanding/vo_line_adjudication.json")
    assert not (doc.get("_meta") or {}).get("stale")
    assert (ctx.run_dir / ".stage_done" / "vo_line_adjudicate").is_file()


def test_preclean_skipped_when_ingest_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import prepare_fingerprint_blocks_rerun

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "preclean_fp")
    ctx.write_json("ingest/ingest_checksums.json", {"sha256": "abc"})
    mark_done_raw(ctx, "audio_preclean")
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.prepare_outputs_present",
        lambda _ctx, _sid: True,
    )
    assert prepare_fingerprint_blocks_rerun(ctx, "audio_preclean") == "ingest_unchanged"


def test_seed_prereq_transitions_skips_complete_seams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "seams_seed")
    from interview_mux.homunculus.runtime import _seed_prereq_block
    from interview_mux.homunculus.agenda import stage_outputs_present

    # Mark seams done with mastering plan outputs (shared seams artifact).
    ctx.write_json(
        "mastering/mastering_plan.json",
        {"air_script": {"beats": [], "vo_seats": {"seated_line_ids": [], "omitted_line_ids": []}}},
    )
    mark_done_raw(ctx, "air_script_seams")
    assert stage_outputs_present(ctx, "air_script_seams") or ctx.is_done("air_script_seams")
    # Even if earliest incomplete reports seams, seed_complete should clear the block.
    block = _seed_prereq_block(ctx, "transitions")
    assert block != "air_script_seams"


def test_stamp_stale_layup_clears_transitions_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "stamp_tr")
    from interview_mux.artifact_lifecycle import stamp_stale_and_archive

    _write_raw(
        ctx,
        "master/transitions.json",
        {"transitions": [], "_meta": {"producer_stage": "transitions"}},
    )
    mark_done_raw(ctx, "transitions")
    stamped = stamp_stale_and_archive(ctx, "nugget_layup_compose")
    assert any("transitions" in s for s in stamped)
    assert not ctx.is_done("transitions")
    doc = ctx.read_json("master/transitions.json")
    assert (doc.get("_meta") or {}).get("stale") is True


def test_resolve_assembly_and_gap_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "asm_gap_helpers")
    assert resolve_assembly_stale_resume(ctx) == "edl"
    _write_raw(ctx, "master/edl.json", {"ordered_segment_ids": ["a"], "clips": []})
    monkeypatch.setattr(
        "interview_mux.heal_routing.mix_assembly_seated",
        lambda _ctx: False,
    )
    assert resolve_assembly_stale_resume(ctx) == "mix"
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {"_meta": {"stale_reason": "invalidated_by:optimal_questions"}},
    )
    assert resolve_gap_report_stale_producer(ctx) == "optimal_questions"
    assert premature_cap_hard_pin(
        ctx, "master_finalize", message="master/assembly_ledger.json missing"
    ) in {"edl", "topic_coverage_audit", "master_finalize"}


def test_ship_path_ready_blocks_uncommitted_master(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RSTM committed-master-honesty: bare master.wav must not be ship-ready."""
    from interview_mux.delivery_guardrails import ship_path_ready

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "ship_uncommitted")
    asm = ctx.path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF" + b"\x00" * 4096)
    master = ctx.path("master", "master.wav")
    master.write_bytes(b"RIFF" + b"\x00" * 64)
    mark_done_raw(ctx, "mix", "listen_delight_audit")
    _write_raw(ctx, "mastering/listen_delight_audit.json", {"status": "complete", "passed": True})
    _write_raw(ctx, "master/junction_snip_qa.json", {"critical_count": 0, "residuals": []})
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda._junction_commitment_matches_assembly",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid in {"mix", "junction_snip_qa", "listen_delight_audit"},
    )
    monkeypatch.setattr(
        "interview_mux.delivery_invariants.committed_master_wav",
        lambda _ctx: False,
    )
    ready, reason = ship_path_ready(ctx)
    assert ready is False
    assert reason == "master_uncommitted"


def test_a04_waived_unattended_alone_not_delivery_stable_or_ship(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-04 / SYN-DELIGHT-01: telemetry waiver must not green music or ship alone."""
    from interview_mux.delivery_guardrails import (
        LISTEN_DELIGHT_WAIVER_REL,
        listen_delight_cleared_for_progress,
        ship_path_ready,
    )

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "a04_telemetry")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid
        in {
            "nugget_layup_compose",
            "vo_line_adjudicate",
            "edl",
            "assembly_preview",
            # listen_delight_audit intentionally incomplete
            "mix",
            "junction_snip_qa",
        },
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.assembly_wav_present",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.upstream_stale_blockers",
        lambda _ctx, _stage: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.read_checkpoint",
        lambda _ctx: {"phase": "A_sealed"},
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.read_delivery_epoch",
        lambda _ctx: {"phase_a_sealed_at": "2026-01-01T00:00:00Z"},
    )
    _write_raw(
        ctx,
        LISTEN_DELIGHT_WAIVER_REL,
        {"status": "waived_unattended", "stage": "listen_delight_audit"},
    )
    _write_raw(ctx, "mastering/listen_delight_audit.json", {"passed": False})
    assert listen_delight_cleared_for_progress(ctx) is False
    ok, reason = delivery_stable_for_music(ctx)
    assert ok is False
    assert reason == "listen_delight_incomplete"

    asm = ctx.path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF" + b"\x00" * 4096)
    _write_raw(ctx, "master/junction_snip_qa.json", {"critical_count": 0})
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda._junction_commitment_matches_assembly",
        lambda _ctx: True,
    )
    ready, ship_reason = ship_path_ready(ctx)
    assert ready is False
    assert ship_reason == "listen_delight_incomplete"


def test_a04_quality_waived_clears_delight_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-04: quality_waived (or e2e quality waivers) may clear music delight floor."""
    from interview_mux.delivery_guardrails import (
        LISTEN_DELIGHT_WAIVER_REL,
        listen_delight_cleared_for_progress,
    )

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "a04_quality")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid != "listen_delight_audit",
    )
    _write_raw(
        ctx,
        LISTEN_DELIGHT_WAIVER_REL,
        {"status": "quality_waived", "stage": "listen_delight_audit"},
    )
    assert listen_delight_cleared_for_progress(ctx) is True


def test_shared_path_palettes_plan_is_not_orphan_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sound_design_palettes writing plan.json must not sticky-orphan sound_design_plan."""
    from interview_mux.delivery_guardrails import reconcile_orphan_artifacts

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "orphan_shared_sdp")
    mark_done_raw(ctx, "sound_design_palettes")
    _write_raw(
        ctx,
        "understanding/sound_design_plan.json",
        {
            "version": 1,
            "palettes": [],
            "assets": [],
            "_meta": {"producer_stage": "sound_design_palettes"},
        },
    )
    assert not ctx.is_done("sound_design_plan")
    orphans = reconcile_orphan_artifacts(ctx)
    assert "sound_design_plan" not in orphans
