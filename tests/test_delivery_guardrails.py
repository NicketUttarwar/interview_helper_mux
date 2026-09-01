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
from tests.run_fixtures import isolated_run_ctx


def _write_raw(ctx: RunContext, rel: str, data: dict) -> None:
    path = ctx.path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _ctx(tmp_path: Path, name: str = "gdr") -> RunContext:
    return isolated_run_ctx(tmp_path, name)


def test_seed_complete_blocks_hollow_assembly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "hollow_asm")
    ctx.mark_done("assembly_preview", force=True)
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
    ctx.mark_done("mmaudio_sfx", force=True)
    ctx.mark_done("mix", force=True)
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


def test_transcribe_not_rerun_after_g0_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g10")
    from interview_mux.delivery_guardrails import prepare_fingerprint_blocks_rerun
    from interview_mux.homunculus.runtime import dispatch_stage

    ctx.write_json("transcript/full.json", {"utterances": [{"text": "hello", "speaker": "spk_0"}]})
    ctx.write_json("ingest/transcript.json", {"utterances": [{"text": "hello"}]})
    ctx.mark_done("transcript_review", force=True)
    ctx.mark_done("transcribe", force=True)
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
    ctx.mark_done("assembly_preview", force=True)
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
        ctx.mark_done(sid, force=True)
    assert music_epoch_complete(ctx) is False
    assert mix_epoch_block(ctx) == "music_incomplete"


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
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001"]})
    preview = ctx.path("master", "assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF" + b"\x00" * 64)
    row = seal_phase_a_if_stable(ctx)
    assert row is not None
    assert ctx.artifact_exists(CHECKPOINT_REL)
    assert row.get("phase") == "A_sealed"


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
    ctx.mark_done("mix", force=True)
    ctx.mark_done("listen_delight_audit", force=True)
    _write_raw(ctx, "mastering/listen_delight_audit.json", {"status": "complete", "passed": True})
    _write_raw(ctx, "master/post_master_quality.json", {"publish_allowed": True})
    _write_raw(ctx, "master/junction_snip_qa.json", {"critical_count": 0, "residuals": []})
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid in {"mix", "listen_delight_audit"},
    )
    ready, _ = ship_path_ready(ctx)
    assert ready is True
    filtered = filter_delivery_candidates(
        ctx, ["junction_snip_qa", "master_finalize", "podcast_encode_mp3"]
    )
    assert "junction_snip_qa" not in filtered
    assert "master_finalize" in filtered


def test_vo_synth_blocked_when_transitions_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "g8_tr")
    block = vo_synthesize_stability_block(ctx)
    assert block in {"transitions", "nugget_layup_compose"}


def test_preclean_skipped_when_ingest_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import prepare_fingerprint_blocks_rerun

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "preclean_fp")
    ctx.write_json("ingest/ingest_checksums.json", {"sha256": "abc"})
    ctx.mark_done("audio_preclean", force=True)
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.prepare_outputs_present",
        lambda _ctx, _sid: True,
    )
    assert prepare_fingerprint_blocks_rerun(ctx, "audio_preclean") == "ingest_unchanged"
