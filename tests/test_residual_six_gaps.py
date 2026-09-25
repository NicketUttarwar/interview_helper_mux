"""Residual cluster six-gap closure: F-02, F-03, B-02/B-03, SDP thrash.

Catalog IDs in docstrings for RSTM Done-when traceability.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    critical_delivery_residual_count,
    record_delivery_residual,
    record_wasted_work,
    ship_path_ready,
)
from interview_mux.heal_routing import FAMILY_JUNCTION, HALT_FAMILIES, classify_heal_error
from interview_mux.selection_auto_pack import pack_selection_to_duration
from interview_mux.session_log import read_log
from interview_mux.soundscape_policy import (
    POLICY_PATH,
    build_policy,
    invent_obligation_status,
    load_policy,
    run_soundscape_policy_build,
    save_operator_overrides,
)
from interview_mux.thrash_hardening import note_authority_undo_attempt
from run_fixtures import isolated_run_ctx, mark_done_raw, minimal_source_acoustic_profile


def _seg(segment_id: str, *, start_ms: int, end_ms: int, speaker: str) -> dict:
    return {
        "segment_id": segment_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker_id": speaker,
        "speaker_role": "interviewee",
        "type": "interviewee_answer",
        "text": f"Segment {segment_id}.",
        "topic_tags": [],
        "flags": [],
    }


def _write_pack_fixture(ctx) -> None:
    segments = [
        _seg("seg_001", start_ms=0, end_ms=10000, speaker="spk_a"),
        _seg("seg_002", start_ms=10000, end_ms=20000, speaker="spk_a"),
        _seg("seg_003", start_ms=20000, end_ms=30000, speaker="spk_a"),
        _seg("seg_004", start_ms=30000, end_ms=40000, speaker="spk_b"),
        _seg("seg_005", start_ms=40000, end_ms=50000, speaker="spk_b"),
    ]
    ctx.write_json("segments/manifest.json", {"segments": segments}, skip_handoff=True)
    path = ctx.path("analysis", "vernacular_must_keep.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"must_keep_segment_ids": ["seg_005"]}),
        encoding="utf-8",
    )


def _seed_unpaid_invent_policy_inputs(ctx) -> None:
    sap = minimal_source_acoustic_profile(
        pacing={
            "global_wpm": 140,
            "wpm_by_quartile": [120, 130, 140, 150],
            "pace_class": "conversational",
            "speech_active_ratio": 0.7,
            "overlap_proxy": 0.05,
        },
        source_music_risk="low",
        mix_contract={
            "underscore_policy": "normal",
            "duck_under_speech_db": 16,
            "stinger_max_per_minute": 3,
            "bed_level_db_range": [-30, -26],
        },
    )
    ctx.write_json("understanding/source_acoustic_profile.json", sap)
    fixture = Path(__file__).parent / "fixtures" / "sonic_context" / "one_on_one.json"
    sonic = json.loads(fixture.read_text(encoding="utf-8"))
    sonic["mix_policy"]["underscore_policy"] = "normal"
    path = ctx.path("understanding", "sonic_context.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sonic), encoding="utf-8")
    ctx.write_json(
        "understanding/delivery_brief.json",
        {
            "version": 1,
            "source_duration_ms": 600000,
            "target_duration_sec": {"min": 300, "ideal": 420, "max": 540},
            "question_budget": {"min": 0, "ideal": 2, "max": 4},
            "chapter_budget": {"min": 2, "ideal": 3, "max": 4},
            "selection_mode": "coverage_first",
            "sfx_density": {"max_beds": 2, "max_punctuators": 2, "max_foley": 1},
            "ranking_weights": {},
            "rationale": [],
            "operator_overrides": {},
            "generated": {},
        },
    )
    from interview_mux.analysis_memory import default_sound_design_plan

    sdp = default_sound_design_plan()
    sdp["palettes"] = []
    sdp.setdefault("coherence", {})["invent_obligation"] = "sound_design_plan"
    sdp["coherence"]["deferred_ok"] = True
    ctx.write_json("understanding/sound_design_plan.json", sdp, skip_handoff=True)


def test_f02_shadow_must_keep_drop_ledgers(tmp_path, monkeypatch):
    """F-02: shadow vernacular must_keep drop always ledgers wasted_work."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f02_ledger")
    _write_pack_fixture(ctx)

    def _cfg():
        return {"audio_probes": {"enforcement_mode": "shadow", "shadow_must_keep_policy": "ledger"}}

    monkeypatch.setattr("interview_mux.config.merged_config", _cfg)
    monkeypatch.setattr(
        "interview_mux.stages.audio_probes.merged_config",
        _cfg,
    )
    selection = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_003", "seg_004", "seg_005"],
        "excluded_segment_ids": [],
        "segment_ranks": {
            "seg_001": 1,
            "seg_002": 2,
            "seg_003": 3,
            "seg_004": 4,
            "seg_005": 5,
        },
    }
    out = pack_selection_to_duration(
        ctx,
        selection,
        target_sec=45.0,
        stage="test_f02",
        meta_key="test_pack",
        action_id="pipeline.selection.test_f02",
        log_label="F02 pack",
    )
    assert "seg_005" in (out.get("_meta") or {}).get("test_pack", {}).get(
        "shadow_vernacular_dropped", []
    ) or "seg_005" in (out.get("_meta") or {}).get("test_pack", {}).get("dropped", [])
    assert ctx.artifact_exists("operator/wasted_work.json")
    events = ctx.read_json("operator/wasted_work.json").get("events") or []
    assert any(
        isinstance(e, dict) and e.get("event") == "vernacular_shadow_drop" for e in events
    ), events


def test_f02_shadow_must_keep_block_restores(tmp_path, monkeypatch):
    """F-02: shadow_must_keep_policy=block restores must_keep ids."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f02_block")
    _write_pack_fixture(ctx)

    def _cfg():
        return {"audio_probes": {"enforcement_mode": "shadow", "shadow_must_keep_policy": "block"}}

    monkeypatch.setattr("interview_mux.config.merged_config", _cfg)
    monkeypatch.setattr("interview_mux.stages.audio_probes.merged_config", _cfg)
    selection = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_003", "seg_004", "seg_005"],
        "excluded_segment_ids": [],
        "segment_ranks": {
            "seg_001": 1,
            "seg_002": 2,
            "seg_003": 3,
            "seg_004": 4,
            "seg_005": 5,
        },
    }
    out = pack_selection_to_duration(
        ctx,
        selection,
        target_sec=45.0,
        stage="test_f02_block",
        meta_key="test_pack",
        action_id="pipeline.selection.test_f02_block",
        log_label="F02 block",
    )
    assert "seg_005" in out["ordered_segment_ids"]
    assert "seg_005" not in (out.get("_meta") or {}).get("test_pack", {}).get("dropped", [])
    events = (ctx.read_json("operator/wasted_work.json").get("events") or []) if ctx.artifact_exists(
        "operator/wasted_work.json"
    ) else []
    assert any(isinstance(e, dict) and e.get("event") == "vernacular_shadow_drop" for e in events)


def test_f02_ledger_inject_fail_still_visible(tmp_path, monkeypatch):
    """F-02: ledger raise/False → soft residual or meta still set; pack continues."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f02_ledger_fail")
    _write_pack_fixture(ctx)

    def _cfg():
        return {"audio_probes": {"enforcement_mode": "shadow", "shadow_must_keep_policy": "ledger"}}

    monkeypatch.setattr("interview_mux.config.merged_config", _cfg)
    monkeypatch.setattr("interview_mux.stages.audio_probes.merged_config", _cfg)

    def _boom(*_a, **_k):
        raise RuntimeError("inject_ledger_fail")

    monkeypatch.setattr("interview_mux.delivery_guardrails.record_wasted_work", _boom)
    selection = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_003", "seg_004", "seg_005"],
        "excluded_segment_ids": [],
        "segment_ranks": {
            "seg_001": 1,
            "seg_002": 2,
            "seg_003": 3,
            "seg_004": 4,
            "seg_005": 5,
        },
    }
    out = pack_selection_to_duration(
        ctx,
        selection,
        target_sec=45.0,
        stage="test_f02_ledger_fail",
        meta_key="test_pack",
        action_id="pipeline.selection.test_f02_ledger_fail",
        log_label="F02 ledger fail",
    )
    assert "test_pack" in (out.get("_meta") or {})
    assert (out.get("_meta") or {})["test_pack"].get("dropped")
    assert ctx.artifact_exists("operator/delivery_residuals.json")
    residuals = ctx.read_json("operator/delivery_residuals.json").get("residuals") or []
    soft = [
        r
        for r in residuals
        if isinstance(r, dict)
        and r.get("kind") == "vernacular_shadow_ledger_fail"
        and r.get("severity") == "soft"
    ]
    assert soft, residuals
    # Soft residual must not count as critical / sticky true-waste.
    assert critical_delivery_residual_count(ctx) == 0


def test_f02_discover_fail_logs(tmp_path, monkeypatch):
    """F-02: discover failure logs; pack still completes."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f02_discover_fail")
    _write_pack_fixture(ctx)

    def _cfg():
        return {"audio_probes": {"enforcement_mode": "shadow", "shadow_must_keep_policy": "ledger"}}

    monkeypatch.setattr("interview_mux.config.merged_config", _cfg)
    monkeypatch.setattr("interview_mux.stages.audio_probes.merged_config", _cfg)

    def _discover_boom(_ctx):
        raise RuntimeError("inject_discover_fail")

    monkeypatch.setattr(
        "interview_mux.stages.audio_probes.load_must_keep_segment_ids",
        _discover_boom,
    )
    selection = {
        "ordered_segment_ids": ["seg_001", "seg_002", "seg_003", "seg_004", "seg_005"],
        "excluded_segment_ids": [],
        "segment_ranks": {
            "seg_001": 1,
            "seg_002": 2,
            "seg_003": 3,
            "seg_004": 4,
            "seg_005": 5,
        },
    }
    out = pack_selection_to_duration(
        ctx,
        selection,
        target_sec=45.0,
        stage="test_f02_discover",
        meta_key="test_pack",
        action_id="pipeline.selection.test_f02_discover",
        log_label="F02 discover fail",
    )
    assert "test_pack" in (out.get("_meta") or {})
    entries = read_log(ctx.run_dir)
    assert any(
        (e.get("action_id") == "vernacular.shadow.discover_failed")
        or ("discover failed" in str(e.get("message") or "").lower())
        for e in entries
    ), entries[-10:]


def test_f02_record_wasted_work_schema_bypass(tmp_path, monkeypatch):
    """F-02: schema ValueError still persists ledger via file_store + schema_bypass stamp."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f02_schema_bypass")

    def _raise_schema(*_a, **_k):
        raise ValueError("operator/wasted_work.json: schema validation failed — inject")

    monkeypatch.setattr(ctx, "write_json", _raise_schema)
    ok = record_wasted_work(ctx, event="vernacular_shadow_drop", stage="test", detail={"x": 1})
    assert ok is True
    raw = json.loads(ctx.path("operator", "wasted_work.json").read_text(encoding="utf-8"))
    assert raw.get("schema_bypass") is True
    assert any(e.get("event") == "vernacular_shadow_drop" for e in (raw.get("events") or []))


def test_f03_invent_gate_blocks_heuristic_beds(tmp_path, monkeypatch):
    """F-03: unpaid invent_obligation → invent_gate blocked; dens invent beds cleared.

    Soft-block keeps planned/inject beds when present; with no
    planned SDP beds the slot list stays empty.
    """
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f03_invent")
    _seed_unpaid_invent_policy_inputs(ctx)

    status = invent_obligation_status(ctx)
    assert status["unpaid"] is True
    policy = build_policy(ctx, refresh_slots=True)
    assert policy.get("invent_gate") == "blocked"
    assert int((policy.get("sfx_density") or {}).get("max_beds") or 0) == 0
    cov = (policy.get("mix_contract") or {}).get("max_bed_coverage_ratio")
    assert cov is not None and float(cov) == 0.0
    assert policy.get("cue_slots") == []
    assert policy.get("musical_direction_complete") is False
    assert "soft_block" in str(policy.get("invent_gate_reason") or "")


def test_ssp_b1_fail_closed_invent_blocked_incomplete(tmp_path, monkeypatch):
    """SSP-B1: fail_closed + invent blocked → run refuses heal-done."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.soundscape_policy.fail_closed",
        lambda _cfg=None: True,
    )
    ctx = isolated_run_ctx(tmp_path, "ssp_b1_invent")
    _seed_unpaid_invent_policy_inputs(ctx)
    with pytest.raises(RuntimeError, match="invent_gate=blocked"):
        run_soundscape_policy_build(ctx)
    assert not ctx.is_done("soundscape_policy_build")


def test_f03_operator_override_cannot_bypass_invent_gate(tmp_path, monkeypatch):
    """F-03 THE REPRO: unpaid SDP + dens override still invent-blocked; desired prefs kept."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f03_override_bypass")
    _seed_unpaid_invent_policy_inputs(ctx)
    base = build_policy(ctx, refresh_slots=True)
    ctx.write_json(POLICY_PATH, base)

    policy = save_operator_overrides(
        ctx,
        {
            "underscore_policy": "normal",
            "sfx_density": {"max_beds": 3, "max_punctuators": 2, "max_foley": 1},
            "invent_gate": "clear",
            "invent_waived": True,
        },
    )
    assert policy.get("invent_gate") == "blocked"
    assert int((policy.get("sfx_density") or {}).get("max_beds") or 0) == 0
    assert policy.get("underscore_policy") == "skip"
    ov = policy.get("operator_overrides") or {}
    assert ov.get("underscore_policy") == "normal"
    assert int((ov.get("sfx_density") or {}).get("max_beds") or 0) == 3
    assert "invent_gate" not in ov
    assert "invent_waived" not in ov


def test_f03_load_policy_regates_corrupt_disk(tmp_path, monkeypatch):
    """F-03: corrupt disk blocked+max_beds=3 → load_policy re-clamps."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f03_load_regate")
    _seed_unpaid_invent_policy_inputs(ctx)
    corrupt = build_policy(ctx, refresh_slots=False)
    corrupt["invent_gate"] = "blocked"
    dens = dict(corrupt.get("sfx_density") or {})
    dens["max_beds"] = 3
    dens["max_punctuators"] = 2
    corrupt["sfx_density"] = dens
    corrupt["underscore_policy"] = "normal"
    path = ctx.path(*POLICY_PATH.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(corrupt), encoding="utf-8")

    loaded = load_policy(ctx)
    assert loaded is not None
    assert loaded.get("invent_gate") == "blocked"
    assert int((loaded.get("sfx_density") or {}).get("max_beds") or 0) == 0
    assert loaded.get("underscore_policy") == "skip"


def test_f03_invent_waived_allows_dens(tmp_path, monkeypatch):
    """F-03: invent_waived via SDP allows dens beds."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f03_waived")
    _seed_unpaid_invent_policy_inputs(ctx)
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    sdp["coherence"]["invent_waived"] = True
    ctx.write_json("understanding/sound_design_plan.json", sdp, skip_handoff=True)

    status = invent_obligation_status(ctx)
    assert status["unpaid"] is False
    assert status["waived"] is True
    policy = build_policy(ctx, refresh_slots=True)
    assert policy.get("invent_gate") in {"clear", "satisfied"}
    assert int((policy.get("sfx_density") or {}).get("max_beds") or 0) >= 1


def test_b02_fuse_oscillation_residual_blocks_ship(tmp_path, monkeypatch):
    """B-02: fuse oscillation residual is visible to ship_path_ready."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "b02_residual")
    record_delivery_residual(
        ctx,
        kind="fuse_oscillation",
        severity="critical",
        stage="connector_fuse_pass",
        detail={"pass_id": "test", "sig": "a|b"},
    )
    assert critical_delivery_residual_count(ctx) >= 1
    assert ctx.artifact_exists("operator/delivery_residuals.json")
    asm = ctx.path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF" + b"\x00" * 4096)
    mark_done_raw(ctx, "mix")
    mark_done_raw(ctx, "listen_delight_audit")
    mark_done_raw(ctx, "junction_snip_qa")
    delight = ctx.path("mastering", "listen_delight_audit.json")
    delight.parent.mkdir(parents=True, exist_ok=True)
    delight.write_text(json.dumps({"status": "complete", "passed": True}), encoding="utf-8")
    qa = ctx.path("master", "junction_snip_qa.json")
    qa.parent.mkdir(parents=True, exist_ok=True)
    qa.write_text(
        json.dumps({"critical_count": 0, "critical_residual_count": 0, "residuals": []}),
        encoding="utf-8",
    )
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
        "interview_mux.delivery_guardrails.listen_delight_cleared_for_progress",
        lambda _ctx: True,
    )
    ready, reason = ship_path_ready(ctx)
    assert ready is False
    assert reason == "critical_delivery_residuals"


def test_b03_junction_family_in_halt_and_classify(tmp_path, monkeypatch):
    """B-03: FAMILY_JUNCTION in HALT_FAMILIES; hitch/fuse map to junction family."""
    assert FAMILY_JUNCTION in HALT_FAMILIES
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "b03_family")
    hitch = classify_heal_error("hitch_listen_restage incomplete_cut", ctx)
    assert hitch is not None
    assert hitch.family == FAMILY_JUNCTION
    fuse = classify_heal_error("fuse_oscillation_halt on connector_fuse", ctx)
    assert fuse is not None
    assert fuse.family == FAMILY_JUNCTION


def test_sdp_empty_scaffold_hash_not_thrash(tmp_path, monkeypatch):
    """SDP: empty scaffold hash ↔ hardened content is progress, not thrash halt."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "exec_sdp_thrash")
    empty = "4d59a639ec9a6a95a36e9cbc"
    hard_a = "aaaaaaaaaaaaaaaaaaaaaaaa"
    hard_b = "bbbbbbbbbbbbbbbbbbbbbbbb"
    r1 = note_authority_undo_attempt(
        ctx,
        artifact="understanding/sound_design_plan.json",
        action_class="scaffold",
        content_hash=empty,
    )
    assert r1.get("halt") is False
    r2 = note_authority_undo_attempt(
        ctx,
        artifact="understanding/sound_design_plan.json",
        action_class="sound_design_plan",
        content_hash=hard_a,
    )
    assert r2.get("halt") is False
    r3 = note_authority_undo_attempt(
        ctx,
        artifact="understanding/sound_design_plan.json",
        action_class="write_json",
        content_hash=empty,
    )
    # empty still in window + nonempty prior → not thrash
    assert r3.get("halt") is False
    r4 = note_authority_undo_attempt(
        ctx,
        artifact="understanding/sound_design_plan.json",
        action_class="commit_sound_design_plan",
        content_hash=hard_b,
    )
    assert r4.get("halt") is False
