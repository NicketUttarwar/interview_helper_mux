"""Sealed AirOrder + autonomous recovery contract tests (plan: autonomous EDL recovery)."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from interview_mux.air_order import (
    assert_consumer,
    commit,
    generation,
    read_live,
    rollback,
    snapshot,
    write_live_edl,
)
from interview_mux.homunculus.agenda import PROTECTED_DELIVERY_OUTPUTS, stage_outputs_present
from interview_mux.homunculus.runtime import recovery_allowed
from interview_mux.identical_failures import failure_signature, is_halted, record_identical_failure
from interview_mux.order_hash import bump_order_lock, edl_speech_clip_ids, order_drift_heal_action
from interview_mux.recovery_controller import classify_error_class, handle_stage_failure
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


def _speech(sid: str) -> dict:
    return {
        "type": "speech",
        "segment_id": sid,
        "source_start_ms": 0,
        "source_end_ms": 1000,
        "duration_ms": 1000,
        "timeline_start_ms": 0,
    }


def _edl(ids: list[str], *, gen: int | None = None) -> dict:
    clips = []
    t = 0
    for sid in ids:
        clip = _speech(sid)
        clip["timeline_start_ms"] = t
        clips.append(clip)
        t += 1000
    out = {
        "version": 1,
        "ordered_segment_ids": list(ids),
        "clips": clips,
        "timeline_duration_ms": t,
    }
    if gen is not None:
        out["air_order_generation"] = gen
    return out


def test_recovery_allowed_for_classified_edl_drift_without_analyze_issue(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "air_rec_allowed")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    exc = SystemExit(
        "selection_edl_order_drift: speech clip order diverges from ordered_segment_ids"
    )
    assert classify_error_class("mix", exc) == "selection_edl_order_drift"
    assert recovery_allowed(ctx, "mix", exc=exc) is True


def test_commit_excludes_unseated_in_same_generation(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "air_exclude")
    seated = ["seg_a", "seg_b", "seg_c"]
    sel = bump_order_lock(
        {"ordered_segment_ids": seated + ["seg_extra_1", "seg_extra_2"], "version": 1},
        source="test",
    )
    edl = _edl(seated)
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ctx.write_json("master/edl.json", edl, skip_handoff=True)
    assert order_drift_heal_action(sel, edl) == "exclude_unseated"
    bundle = commit(ctx, source="test_exclude")
    live_sel = ctx.read_json("master/selection.json")
    live_edl = ctx.read_json("master/edl.json")
    assert live_sel["ordered_segment_ids"] == seated
    assert edl_speech_clip_ids(live_edl) == seated
    assert bundle["generation"] == generation(ctx)
    assert live_sel.get("air_order_generation") == live_edl.get("air_order_generation")
    reasons = {
        str(r.get("segment_id")): str(r.get("reason"))
        for r in (live_sel.get("excluded_segment_ids") or [])
        if isinstance(r, dict)
    }
    assert reasons.get("seg_extra_1") == "edl_unseated"
    assert reasons.get("seg_extra_2") == "edl_unseated"


def test_take_best_commit_or_rollback_never_clips_subset(tmp_path: Path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "air_take_best")
    from interview_mux.timeline_optimizer import apply as apply_mod

    prev = bump_order_lock({"ordered_segment_ids": ["a", "b"], "version": 1}, source="prev")
    ctx.write_json("master/selection.json", prev, skip_handoff=True)
    ctx.write_json("master/edl.json", _edl(["a", "b"]), skip_handoff=True)
    commit(ctx, source="seed")
    gen_before = generation(ctx)

    monkeypatch.setattr(
        apply_mod,
        "load_best",
        lambda _ctx: {
            "candidate_id": "cand1",
            "score": 9.0,
            "ordered_segment_ids": ["a", "b", "c", "d", "e"],
        },
    )

    def _fail_remaster(_ctx, *, until_mix: bool = True):
        raise RuntimeError("remaster boom")

    monkeypatch.setattr(apply_mod, "remaster_sync", _fail_remaster)
    monkeypatch.setattr(
        apply_mod,
        "load_optimizer_state",
        lambda _ctx: {"promotions": []},
    )
    monkeypatch.setattr(apply_mod, "save_optimizer_state", lambda _ctx, _s: None)
    monkeypatch.setattr(
        "interview_mux.synthetic_framing.run_synthetic_framing_plan",
        lambda *_a, **_k: None,
    )

    with pytest.raises(RuntimeError, match="remaster"):
        apply_mod.take_best_candidate(ctx, remaster=True, sync_remaster=True)

    live_sel = ctx.read_json("master/selection.json")
    live_edl = ctx.read_json("master/edl.json")
    assert live_sel["ordered_segment_ids"] == ["a", "b"]
    assert edl_speech_clip_ids(live_edl) == ["a", "b"]
    assert generation(ctx) == gen_before


def test_mix_refuses_mismatched_air_order_generation(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "air_mix_refuse")
    sel = bump_order_lock({"ordered_segment_ids": ["a", "b"], "version": 1}, source="t")
    edl = _edl(["a", "b"])
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ctx.write_json("master/edl.json", edl, skip_handoff=True)
    commit(ctx, source="seed")
    # Corrupt EDL stamp to simulate mixed generation
    edl_now = ctx.read_json("master/edl.json")
    edl_now["air_order_generation"] = int(edl_now.get("air_order_generation") or 1) + 99
    # Bypass seal to plant mismatch
    from interview_mux.write_staging import write_mirrored_json

    setattr(ctx, "_air_order_committing", True)
    write_mirrored_json(ctx, "master/edl.json", edl_now)
    setattr(ctx, "_air_order_committing", False)
    with pytest.raises(SystemExit, match="assembly_not_rendered_from_current_edl|generation"):
        assert_consumer(ctx, "mix")


def test_glue_slot_one_owner_in_commit(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "air_glue")
    from interview_mux.file_store import write_json as fs_write_json

    sel = bump_order_lock({"ordered_segment_ids": ["seg_001"], "version": 1}, source="t")
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ctx.write_json("master/edl.json", _edl(["seg_001"]), skip_handoff=True)
    fs_write_json(
        ctx.path("understanding/gap_report.json"),
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "targets_segment_id": "seg_001",
                    "gap_type": "episode_orientation",
                    "placement": "before",
                    "delivery": "synthesize",
                    "text": "Welcome to the show with our guest.",
                    "opening_sequence": "intro_music_body",
                    "episode_orientation": True,
                },
                {
                    "line_id": "vo_layup_seg_001",
                    "targets_segment_id": "seg_001",
                    "gap_type": "context",
                    "placement": "before",
                    "origin": "nugget_layup",
                    "delivery": "synthesize",
                    "text": "Duplicate opening layup that must yield.",
                },
            ]
        },
    )
    bundle = commit(ctx, source="glue_test")
    occ = bundle.get("glue_occupancy") or {}
    row = occ.get("seg_001") or {}
    assert row.get("owner") == "episode_orientation"
    gap = ctx.read_json("understanding/gap_report.json")
    layup = next(
        ln
        for ln in gap["interviewer_lines"]
        if ln.get("line_id") == "vo_layup_seg_001"
    )
    assert layup.get("skipped_optional") or layup.get("skip") or layup.get("air_script_omit")


def test_delivery_resume_does_not_mark_mix_done_when_commitment_diverged(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "air_resume")
    sel = bump_order_lock(
        {"ordered_segment_ids": ["a", "b", "c"], "version": 1}, source="t"
    )
    edl = _edl(["a", "b"])  # subset → exclude/rebuild, not committed mix
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ctx.write_json("master/edl.json", edl, skip_handoff=True)
    (ctx.run_dir / "master" / "assembly.wav").write_bytes(b"RIFF" + b"\x00" * 64)
    assert stage_outputs_present(ctx, "mix") is False
    assert order_drift_heal_action(sel, edl) == "exclude_unseated"


def test_identical_failures_is_halted_stops_edl_rebuild(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "air_halt")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    exc = SystemExit("selection_edl_order_drift: speech clip order diverges")
    # Seed selection/edl so playbook can run once
    ctx.write_json(
        "master/selection.json",
        bump_order_lock({"ordered_segment_ids": ["a", "b", "c"], "version": 1}, source="t"),
        skip_handoff=True,
    )
    ctx.write_json("master/edl.json", _edl(["a", "b"]), skip_handoff=True)

    first = handle_stage_failure(ctx, "mix", exc)
    assert first.status in {"recovered", "escalate"}
    # Force halt via three records of same signature
    sig = failure_signature(
        failed_stage="mix",
        producer="selection_edl_order_drift",
        reason=str(exc)[:400],
    )
    for _ in range(3):
        record_identical_failure(
            ctx,
            failed_stage="mix",
            producer="selection_edl_order_drift",
            reason=str(exc)[:400],
        )
    assert is_halted(ctx, sig)
    second = handle_stage_failure(ctx, "mix", exc)
    assert second.status == "escalate"
    assert second.playbook_id in {"identical_failure_halt", "budget_exhausted"}


def test_ranking_passes_source_start_ms_so_earlier_keeps_are_not_after_signoff() -> None:
    from interview_mux.stages import selection as sel_mod

    src = inspect.getsource(sel_mod)
    assert "_source_start_ms_map" in src
    assert "source_start_ms=_source_start_ms_map" in src
    assert src.count("repair_selection_order(") >= 6
    assert src.count("source_start_ms=_source_start_ms_map") >= 6


def test_master_finalize_hollow_without_pmq() -> None:
    outs = PROTECTED_DELIVERY_OUTPUTS["master_finalize"]
    assert "master/post_master_quality.json" in outs
    assert "master/master.wav" in outs


def test_direct_edl_write_sites_go_through_commit() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "interview_mux"
    sites = [
        root / "stages" / "assembly.py",
        root / "sound_design.py",
        root / "junction_snip_qa.py",
        root / "transition_vo.py",
        root / "opening_orientation.py",
        root / "vo_synthesis_audit.py",
        root / "omit_ledger.py",
        root / "edl_source_contract.py",
    ]
    for path in sites:
        text = path.read_text(encoding="utf-8")
        # No bare write_json / write_committed_json of master/edl.json outside air_order
        bare = (
            'write_json("master/edl.json"' in text
            or "write_json('master/edl.json'" in text
            or 'write_committed_json(ctx, "master/edl.json"' in text
        )
        assert not bare, f"{path.name} still writes master/edl.json directly"
        assert "write_live_edl" in text or path.name == "edl_source_contract.py"
        if path.name == "edl_source_contract.py":
            assert "write_live_edl" in text


def test_order_drift_exclude_unseated_action() -> None:
    sel = {"ordered_segment_ids": ["a", "b", "c", "d"]}
    edl = {"clips": [_speech("a"), _speech("b"), _speech("c")]}
    assert order_drift_heal_action(sel, edl) == "exclude_unseated"
    edl2 = {"clips": [_speech("a"), _speech("c"), _speech("b")]}
    assert order_drift_heal_action(sel, edl2) == "rebuild"
