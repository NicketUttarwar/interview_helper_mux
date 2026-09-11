"""Thrash edge-case hardening (T1–T8) + follow-on hardness layers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    premature_cap_hard_pin,
    promote_complete_orphan_stage_done,
)
from interview_mux.identical_failures import (
    clear_halts_for_stages_if_predicate_flipped,
    hydrate_driver_fail_counts,
    read_identical_failures,
    record_identical_failure,
    upsert_fail_key,
)
from interview_mux.run_context import RunContext
from interview_mux.thrash_hardening import (
    FAIL_CLASS_DELIVERY_BLOCKED,
    FAIL_CLASS_MUSIC_EPOCH,
    FAIL_CLASS_VO_G1,
    THRASH_HIT_THRESHOLD,
    artifact_usable,
    assert_may_force_done,
    bump_assembly_seating_generation,
    canonical_resume_pin,
    demote_incomplete_orphans,
    discard_pending_shadows_for_stage,
    enforce_job_complete_honesty,
    fail_class_for_failure,
    forensics_suppress_allowed,
    heal_navigate,
    narrative_audit_cap_exceeded,
    note_narrative_audit_cycle,
    premature_fail_class,
    premature_fail_key,
    record_thrash_hit,
    stage_predicate_token,
    suppress_allowed,
    thrash_summary,
    wasted_work_summary,
)
from run_fixtures import isolated_run_ctx, mark_done_raw


def _ctx(tmp_path: Path, name: str = "thrash") -> RunContext:
    return isolated_run_ctx(tmp_path, name)


def _write_raw(ctx: RunContext, rel: str, data: dict) -> None:
    path = ctx.path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_discard_pending_shadows_keeps_unflushed_wav(tmp_path: Path) -> None:
    """mark_done runs before flush — must not rmtree unflushed ingest/normalized.wav."""
    ctx = _ctx(tmp_path, "discard_shadows")
    pending = ctx.run_dir / ".pending_writes" / "ingest" / "ingest"
    pending.mkdir(parents=True)
    wav = pending / "normalized.wav"
    wav.write_bytes(b"RIFF" + b"\0" * 64)
    shadow = pending / "loudness.json"
    shadow.write_text('{"ok":1}', encoding="utf-8")
    final_loud = ctx.final_path("ingest", "loudness.json")
    final_loud.parent.mkdir(parents=True, exist_ok=True)
    final_loud.write_text('{"ok":1}', encoding="utf-8")

    removed = discard_pending_shadows_for_stage(ctx, "ingest")
    assert "ingest/loudness.json" in removed
    assert wav.is_file()
    assert not shadow.is_file()


def test_mark_done_does_not_wipe_unflushed_pending(tmp_path: Path) -> None:
    """Regression: thrash discard must not run from mark_done before flush."""
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    ctx = _ctx(tmp_path, "mark_done_pending")
    enter_stage_staging("ingest")
    try:
        pending = ctx.run_dir / ".pending_writes" / "ingest" / "ingest"
        pending.mkdir(parents=True)
        wav = pending / "normalized.wav"
        wav.write_bytes(b"RIFF" + b"\0" * 200)
        mark_done_raw(ctx, "ingest")
        assert wav.is_file(), "mark_done must leave unflushed normalized.wav"
        assert ctx.is_done("ingest")
    finally:
        exit_stage_staging()


def test_premature_fail_class_stable_for_music_and_mix() -> None:
    assert premature_fail_class("music_palette_compose") == FAIL_CLASS_MUSIC_EPOCH
    assert premature_fail_class("mmaudio_sfx") == FAIL_CLASS_MUSIC_EPOCH
    assert premature_fail_key("delivery", "music_palette_compose") == (
        "delivery:premature_complete:music_epoch"
    )
    assert premature_fail_key("delivery", "edl_narrative_audit") != premature_fail_key(
        "delivery", "music_palette_compose"
    )


def test_fail_class_for_failure_shared() -> None:
    assert fail_class_for_failure(reason="G1 VO pickup missing") == "vo_g1"
    assert fail_class_for_failure(stage="master_finalize") == "finalize_inputs"


def test_canonical_pin_music_not_narrative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "canon_music")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    preview = ctx.final_path("master", "assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF....WAVEfmt ")

    def _seed(_ctx: RunContext, sid: str) -> bool:
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
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (False, "phase_a_unsealed"),
    )
    pin = canonical_resume_pin(ctx, FAIL_CLASS_MUSIC_EPOCH)
    assert pin == "music_palette_compose"
    assert premature_cap_hard_pin(ctx, "music_palette_compose") == "music_palette_compose"
    nav = heal_navigate(ctx, error="music incomplete", stage="mix")
    assert nav["from_stage"] == "music_palette_compose"


def test_canonical_pin_delivery_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "blocked")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (False, "phase_a_unsealed"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid
        not in {
            "music_palette_compose",
            "sfx_prompt_craft",
            "mmaudio_sfx",
        },
    )
    pin = canonical_resume_pin(ctx, FAIL_CLASS_DELIVERY_BLOCKED)
    assert pin == "music_palette_compose"


def test_halt_clear_requires_predicate_flip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "halt_flip")
    token = stage_predicate_token(ctx, "music_palette_compose")
    record_identical_failure(
        ctx,
        failed_stage="music_palette_compose",
        reason="delivery:premature_complete:music_epoch",
    )
    doc = read_identical_failures(ctx)
    for row in (doc.get("signatures") or {}).values():
        if isinstance(row, dict):
            row["predicate_token"] = token
            row["count"] = 3
            row["halt"] = True
            row["fail_key"] = "delivery:premature_complete:music_epoch"
    from interview_mux import identical_failures as idf

    idf._write(ctx, doc)
    cleared = clear_halts_for_stages_if_predicate_flipped(ctx, {"music_palette_compose"})
    assert cleared == 0


def test_promote_orphan_and_assert_force_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "orphan_force")
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

    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, sid: "hollow" if sid == "mix" else None,
    )
    with pytest.raises(RuntimeError, match="refuse force-done"):
        assert_may_force_done(ctx, "mix")


def test_demote_incomplete_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "demote")
    _write_raw(
        ctx,
        "master/edl.json",
        {"version": 1, "ordered_segment_ids": [], "clips": []},
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, sid: "empty clips" if sid == "edl" else None,
    )
    demoted = demote_incomplete_orphans(ctx)
    assert "edl" in demoted
    assert not ctx.artifact_exists("master/edl.json")


def test_demote_skips_when_assembly_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "demote_asm")
    _write_raw(
        ctx,
        "master/edl.json",
        {"version": 1, "ordered_segment_ids": [], "clips": []},
    )
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF" + b"\0" * 100)
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, sid: "empty clips" if sid == "edl" else None,
    )
    assert demote_incomplete_orphans(ctx) == []
    assert ctx.artifact_exists("master/edl.json")


def test_demote_stamps_nonempty_instead_of_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "demote_stamp")
    _write_raw(
        ctx,
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "clips": [{"type": "speech", "segment_id": "seg_001"}],
        },
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, sid: "empty clips" if sid == "edl" else None,
    )
    assert demote_incomplete_orphans(ctx) == []
    assert ctx.artifact_exists("master/edl.json")
    meta = (ctx.read_json("master/edl.json") or {}).get("_meta") or {}
    assert meta.get("orphan_incomplete") is True


def test_demote_skips_soft_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "demote_soft")
    _write_raw(
        ctx,
        "master/edl.json",
        {"version": 1, "ordered_segment_ids": ["a"], "clips": [{"type": "speech"}]},
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, sid: "master/edl.json unusable (stale_meta:layup)"
        if sid == "edl"
        else None,
    )
    demoted = demote_incomplete_orphans(ctx)
    assert demoted == []
    assert ctx.artifact_exists("master/edl.json")


def test_hard_incompleteness_reason() -> None:
    from interview_mux.thrash_hardening import hard_incompleteness_reason

    assert hard_incompleteness_reason("master/edl.json is pending")
    assert hard_incompleteness_reason("empty clips")
    assert not hard_incompleteness_reason("stale_meta:layup")
    assert not hard_incompleteness_reason("fingerprint_mismatch")


def test_path_to_master_and_seating_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "path_master")
    from interview_mux.thrash_hardening import (
        edl_content_authority_token,
        maybe_bump_seating_for_edl_rewrite,
        path_to_master_pin,
    )

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.assembly_wav_present",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.heal_routing.mix_assembly_seated",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid != "master_finalize",
    )
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF")
    _write_raw(
        ctx,
        "master/edl.json",
        {"ordered_segment_ids": ["a"], "clips": [], "version": 1, "timeline_duration_ms": 0},
    )
    _write_raw(ctx, "master/assembly_ledger.json", {"complete": True})
    _write_raw(ctx, "master/seam_autopsy.json", {"ok": True})
    pin = path_to_master_pin(ctx)
    # Hollow RIFF assembly is treated as stale vs EDL; otherwise pin finalize.
    assert pin == "master_finalize" or "assembly_stale" in str(pin)
    assert pin != "edl_narrative_audit"

    tok = edl_content_authority_token(
        {"order_content_hash": "h1", "ordered_segment_ids": ["a"], "clips": []}
    )
    # Same content → no seating bump.
    assert (
        maybe_bump_seating_for_edl_rewrite(
            ctx,
            before_token=tok,
            after_edl={
                "order_content_hash": "h1",
                "ordered_segment_ids": ["a"],
                "clips": [],
            },
            source="test",
        )
        is False
    )
    assert (
        maybe_bump_seating_for_edl_rewrite(
            ctx,
            before_token=tok,
            after_edl={
                "order_content_hash": "h2",
                "ordered_segment_ids": ["b"],
                "clips": [],
            },
            source="test",
        )
        is True
    )


def test_ensure_finalize_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "fin_restore")
    from interview_mux.thrash_hardening import ensure_finalize_inputs_present

    arch = ctx.run_dir / ".archived" / "x" / "master"
    arch.mkdir(parents=True)
    (arch / "edl.json").write_text(
        json.dumps({"ordered_segment_ids": ["a"], "clips": [{"type": "speech"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_recovery.restore_master_artifact",
        lambda _ctx, rel, min_bytes=0: (
            (_ctx.final_path("master", "edl.json").parent.mkdir(parents=True, exist_ok=True),
             _ctx.final_path("master", "edl.json").write_text(
                 (arch / "edl.json").read_text(encoding="utf-8"), encoding="utf-8"
             ),
             _ctx.final_path("master", "edl.json"))[-1]
            if rel.endswith("edl.json")
            else None
        ),
    )
    restored = ensure_finalize_inputs_present(ctx)
    assert "master/edl.json" in restored or ctx.artifact_exists("master/edl.json")


def test_artifact_usable_stale_meta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "usable")
    _write_raw(
        ctx,
        "master/transitions.json",
        {"transitions": [], "_meta": {"stale": True, "stale_reason": "layup"}},
    )
    ok, reason = artifact_usable(ctx, "master/transitions.json")
    assert ok is False
    assert "stale" in reason


def test_forensics_and_homunculus_suppress_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "suppress")
    assert forensics_suppress_allowed(ctx, FAIL_CLASS_MUSIC_EPOCH) is True
    assert forensics_suppress_allowed(ctx, FAIL_CLASS_MUSIC_EPOCH) is True
    assert forensics_suppress_allowed(ctx, FAIL_CLASS_MUSIC_EPOCH) is True
    assert forensics_suppress_allowed(ctx, FAIL_CLASS_MUSIC_EPOCH) is False
    assert suppress_allowed(ctx, FAIL_CLASS_VO_G1, source="homunculus") is True
    assert suppress_allowed(ctx, FAIL_CLASS_VO_G1, source="homunculus") is True
    assert suppress_allowed(ctx, FAIL_CLASS_VO_G1, source="homunculus") is True
    assert suppress_allowed(ctx, FAIL_CLASS_VO_G1, source="homunculus") is False


def test_order_change_marks_seating_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "order_stale")
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["a", "b"]},
    )
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF")
    mark_done_raw(ctx, "mix")
    from interview_mux.air_order_integrity import on_selection_order_changed
    from interview_mux.heal_routing import mix_assembly_seated

    notes = on_selection_order_changed(
        ctx,
        source="test",
        previous={"ordered_segment_ids": ["a", "b"]},
        current={"ordered_segment_ids": ["b", "a"]},
    )
    assert "assembly_seating_stale" in notes
    assert mix_assembly_seated(ctx) is False
    bump_assembly_seating_generation(ctx, "edl_rewrite")
    assert ctx.read_json("run_meta.json").get("assembly_seating_stale") is True


def test_clear_pair_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "freeze")
    from interview_mux.transition_vo import (
        PAIR_FREEZE_REL,
        clear_transitions_pair_freeze,
    )

    ctx.write_json(PAIR_FREEZE_REL, {"version": 1, "pairs": ["a|b"]})
    assert clear_transitions_pair_freeze(ctx) is True
    assert not ctx.artifact_exists(PAIR_FREEZE_REL)


def test_narrative_audit_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "narr_cap")
    assert narrative_audit_cap_exceeded(ctx) is False
    for _ in range(3):
        note_narrative_audit_cycle(ctx)
    assert narrative_audit_cap_exceeded(ctx) is True


def test_thrash_detector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "thrash_det")
    token = "music_palette_compose:0:0:ok"
    thrash = None
    for _ in range(THRASH_HIT_THRESHOLD):
        thrash = record_thrash_hit(
            ctx,
            fail_class=FAIL_CLASS_MUSIC_EPOCH,
            pin="music_palette_compose",
            predicate_token=token,
            stage="music_palette_compose",
        )
    assert thrash is not None
    assert thrash.get("active") is True
    assert thrash_summary(ctx) is not None
    meta = ctx.read_json("run_meta.json")
    # Soft signal only — do not hard-pause healthy retries.
    assert not meta.get("needs_operator")
    assert meta.get("thrash_pause_recommended") is True


def test_job_complete_honesty_skips_active_driver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "job_driver")
    ctx.write_json(
        "run_meta.json", {"partial_auto_driver_active": True}, skip_handoff=True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.remaining_stages",
        lambda _ctx, _phase: ["music_palette_compose", "mix"],
    )
    out = enforce_job_complete_honesty(
        ctx, {"status": "complete", "message": "Finished: EDL narrative audit"}
    )
    # O7: sticky partial_auto_driver_active alone does not skip honesty — remaining
    # delivery stages demote false complete.
    assert out["status"] in {"error", "incomplete", "running"}
    assert out["status"] != "complete" or not (
        ["music_palette_compose", "mix"]
    )


def test_artifact_usable_pending_only_seating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "pending_seat")
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    pending = ctx.run_dir / ".pending_writes" / "mix" / "master"
    pending.mkdir(parents=True)
    wav = pending / "assembly.wav"
    wav.write_bytes(b"RIFF" + b"\0" * 64)
    # Leftover pending, no active stage → unusable for seating consumers.
    ok, reason = artifact_usable(ctx, "master/assembly.wav", consumer="junction_snip_qa")
    assert ok is False
    assert reason == "pending_only_seating"
    # Same orphan pending must not satisfy mix completeness (heal false-done).
    ok_mix_orphan, reason_mix_orphan = artifact_usable(
        ctx, "master/assembly.wav", consumer="mix"
    )
    assert ok_mix_orphan is False
    assert reason_mix_orphan == "pending_only_seating"
    # Producer mid-stage may only have pending.
    enter_stage_staging("mix")
    try:
        ok2, reason2 = artifact_usable(ctx, "master/assembly.wav", consumer="mix")
        assert ok2 is True
        assert reason2 == ""
    finally:
        exit_stage_staging()


def test_mix_stale_ignores_orphan_pending_assembly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Crashed mix left pending assembly.wav — must not report assembly_stale."""
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "orphan_asm_stale")
    from interview_mux.air_order import mix_stale_versus_live
    from interview_mux.homunculus.agenda import assembly_stale_versus_edl

    edl = ctx.run_dir / "master"
    edl.mkdir(parents=True)
    (edl / "edl.json").write_text('{"version":1,"clips":[]}\n', encoding="utf-8")
    pending = ctx.run_dir / ".pending_writes" / "mix" / "master"
    pending.mkdir(parents=True)
    (pending / "assembly.wav").write_bytes(b"RIFF" + b"\0" * 64)
    assert ctx.artifact_exists("master/assembly.wav") is True
    assert ctx.final_path("master", "assembly.wav").is_file() is False
    assert mix_stale_versus_live(ctx) is False
    assert assembly_stale_versus_edl(ctx) is False


def test_job_complete_honesty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "job_honest")
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.remaining_stages",
        lambda _ctx, _phase: ["music_palette_compose", "mix"],
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.heal_navigate",
        lambda *_a, **_k: {
            "intent": FAIL_CLASS_MUSIC_EPOCH,
            "from_stage": "music_palette_compose",
            "mode": "delivery",
        },
    )
    out = enforce_job_complete_honesty(
        ctx, {"status": "complete", "message": "Finished: EDL narrative audit"}
    )
    assert out["status"] == "error"
    assert "music_palette_compose" in out.get("message", "")


def test_ship_path_honesty_missing_mp3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "ship_honest")
    master = ctx.final_path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF")
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.remaining_stages",
        lambda _ctx, _phase: ["podcast_encode_mp3", "podcast_publish"],
    )
    out = enforce_job_complete_honesty(
        ctx, {"status": "complete", "message": "Finished: master finalize"}
    )
    assert out["status"] == "error"
    assert "Ship incomplete" in out.get("message", "")
    assert out.get("resume_hint") == "podcast_encode_mp3"
    pin = ctx.read_json("operator/delivery_pin.json")
    assert pin.get("intent") == "ship_path"


def test_ship_path_honesty_respects_g_publish_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "ship_gate")
    master = ctx.final_path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF")
    ctx.write_json(
        "run_meta.json", {"g_publish_pending": True}, skip_handoff=True
    )
    out = enforce_job_complete_honesty(
        ctx, {"status": "complete", "message": "Finished: awaiting g-publish"}
    )
    # Soft message with g-publish also short-circuits; pending alone is enough.
    assert out["status"] == "complete"


def test_delivery_pin_summary_from_thrash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "pin_sum")
    from interview_mux.thrash_hardening import delivery_pin_summary, note_delivery_pin

    note_delivery_pin(
        ctx,
        from_stage="mix",
        intent="mix_seat",
        reason="assembly present",
        source="heal_navigate",
    )
    summary = delivery_pin_summary(ctx)
    assert summary is not None
    assert summary["from_stage"] == "mix"
    assert summary["intent"] == "mix_seat"


def test_wasted_work_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "ww")
    from interview_mux.delivery_guardrails import record_wasted_work

    record_wasted_work(ctx, event="music_deferred", stage="mix", detail={"reason": "x"})
    record_wasted_work(ctx, event="thrash_detected", stage="delivery", detail={})
    summary = wasted_work_summary(ctx)
    assert summary["counts"].get("music_deferred", 0) >= 1


def test_progress_stall_skips_active_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "stall_active")
    from interview_mux.thrash_hardening import note_progress_stall

    ctx.write_json(
        "gui_job.json",
        {"status": "running", "current_stage": "mmaudio_sfx", "updated_at": __import__("time").time()},
        skip_handoff=True,
    )
    assert (
        note_progress_stall(ctx, remaining=["mmaudio_sfx", "mix"], stage="mmaudio_sfx")
        is None
    )


def test_phase_a_deadline_soft_no_needs_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "phase_a_soft")
    from interview_mux.thrash_hardening import (
        PHASE_A_SEAL_DEADLINE_ATTEMPTS,
        ensure_phase_a_seal_deadline,
    )

    preview = ctx.final_path("master", "assembly_preview.wav")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"RIFF")
    ctx.write_json("run_meta.json", {}, skip_handoff=True)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed", lambda _ctx: False
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _ctx: (False, "phase_a_unsealed"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.promote_complete_orphan_stage_done",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seal_phase_a_if_stable",
        lambda _ctx: None,
    )
    for _ in range(PHASE_A_SEAL_DEADLINE_ATTEMPTS):
        out = ensure_phase_a_seal_deadline(ctx)
    assert out.get("soft_deadline") is True
    assert out.get("halt") is False
    meta = ctx.read_json("run_meta.json")
    assert not meta.get("needs_operator")


def test_clear_thrash_on_predicate_flip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "thrash_clear")
    from interview_mux.thrash_hardening import (
        clear_thrash_on_predicate_flip,
        thrash_summary,
    )

    token = "music_palette_compose:0:0:ok"
    for _ in range(THRASH_HIT_THRESHOLD):
        record_thrash_hit(
            ctx,
            fail_class=FAIL_CLASS_MUSIC_EPOCH,
            pin="music_palette_compose",
            predicate_token=token,
            stage="music_palette_compose",
        )
    assert thrash_summary(ctx) is not None
    assert clear_thrash_on_predicate_flip(
        ctx, stage="music_palette_compose", prior_token="old-token"
    )
    assert thrash_summary(ctx) is None


def test_expensive_lease_and_pin_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "lease_parity")
    from interview_mux.delivery_guardrails import premature_cap_hard_pin
    from interview_mux.thrash_hardening import (
        expensive_stage_lease_active,
        heal_navigate,
    )

    ctx.write_json(
        "gui_job.json",
        {"status": "running", "current_stage": "mmaudio_sfx"},
        skip_handoff=True,
    )
    leased, stage = expensive_stage_lease_active(ctx)
    assert leased and stage == "mmaudio_sfx"
    assert premature_cap_hard_pin(ctx, "edl_narrative_audit") == "mmaudio_sfx"

    ctx.write_json("gui_job.json", {"status": "idle"}, skip_handoff=True)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._music_epoch_producer_pin",
        lambda _ctx: "music_palette_compose",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.promote_complete_orphan_stage_done",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seal_phase_a_if_stable",
        lambda _ctx: None,
    )
    nav = heal_navigate(ctx, intent=FAIL_CLASS_MUSIC_EPOCH)
    pin = premature_cap_hard_pin(ctx, "music_palette_compose")
    # Music-epoch heal may pin the palette producer or an earlier sanitize/order gate.
    assert nav["from_stage"] == pin
    assert pin in {
        "music_palette_compose",
        "selection_order_sanitize",
        "mmaudio_sfx",
        "sfx_prompt_craft",
    }


def test_hydrate_fail_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = _ctx(tmp_path, "hydrate")
    upsert_fail_key(
        ctx,
        "delivery:premature_complete:music_epoch",
        2,
        failed_stage="music_palette_compose",
        predicate_token="tok-a",
    )
    hydrated = hydrate_driver_fail_counts(ctx)
    assert hydrated.get("delivery:premature_complete:music_epoch") == 2
    assert hydrated.get("_pred:delivery:premature_complete:music_epoch") == "tok-a"
