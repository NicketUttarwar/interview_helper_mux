"""Tests for SFX post-listen gates, auto-refine recovery, and flow hardening."""

from __future__ import annotations

import pytest

from interview_mux.gates import check_post_listen_gate_pending, require_post_listen_clear
from interview_mux.llm_flow_hardening import require_spend_artifacts_complete
from interview_mux.stages import sfx_mmaudio
from run_fixtures import (
    isolated_run_ctx,
    patch_merged_config,
    seed_flow1_sound_spend_ready,
    seed_from_sonic_fixture,
)


def test_check_post_listen_gate_pending_warn_mode_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"sound_design": {"post_listen_gate_mode": "warn"}})
    ctx = isolated_run_ctx(tmp_path, "gate_warn")
    ctx.write_json(
        "run_meta.json",
        {"sfx_listen_results": [{"asset_id": "bed_01", "result": "fail"}]},
        skip_handoff=True,
    )
    assert check_post_listen_gate_pending(ctx) == []


def test_check_post_listen_gate_pending_block_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"sound_design": {"post_listen_gate_mode": "block_mix"}})
    ctx = isolated_run_ctx(tmp_path, "gate_block")
    ctx.write_json(
        "run_meta.json",
        {"sfx_listen_results": [{"asset_id": "bed_01", "result": "fail"}]},
        skip_handoff=True,
    )
    assert check_post_listen_gate_pending(ctx) == ["bed_01"]


def test_require_post_listen_clear_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"sound_design": {"post_listen_gate_mode": "block"}})
    ctx = isolated_run_ctx(tmp_path, "gate_raise")
    ctx.write_json(
        "run_meta.json",
        {"sfx_listen_results": [{"asset_id": "stinger_01", "result": "fail"}]},
        skip_handoff=True,
    )
    with pytest.raises(SystemExit, match="Post-listen gate"):
        require_post_listen_clear(ctx, stage="mix_flow1")


def test_require_spend_artifacts_uses_post_listen_helper(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {"flow_hardening": {"enabled": True, "spend_block_stages": ["mix_flow1"]}},
            "sound_design": {"post_listen_gate_mode": "block_mix"},
        },
    )
    ctx = isolated_run_ctx(tmp_path, "gate_mix_block")
    seed_flow1_sound_spend_ready(ctx)
    meta = ctx.read_json("run_meta.json")
    meta["sfx_listen_results"] = [{"asset_id": "bed_01", "result": "fail", "at": "2026-01-01T00:00:00+00:00"}]
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    with pytest.raises(SystemExit, match="Post-listen gate"):
        require_spend_artifacts_complete(ctx, "mix_flow1")


def test_maybe_auto_refine_invokes_refine_on_qa_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "mmaudio": {
                "auto_refine_enabled": True,
                "auto_refine_on_qa_fail": True,
                "auto_refine_on_listen_fail": False,
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "sfx_auto_refine")
    seed_flow1_sound_spend_ready(ctx)
    seed_from_sonic_fixture(ctx, "one_on_one", seed_base=False)
    ctx.write_json(
        "sound_design/mmaudio_qa.json",
        {
            "version": 1,
            "assets": [{"asset_id": "bed_01", "verdict": "fail", "role": "ambient_bed"}],
        },
        skip_handoff=True,
    )

    refined: list[str] = []

    def _fake_refine(ctx_, asset_ids=None):
        refined.extend(asset_ids or [])

    monkeypatch.setattr(
        sfx_mmaudio,
        "mmaudio_cfg",
        lambda: {
            "auto_refine_enabled": True,
            "auto_refine_on_qa_fail": True,
            "auto_refine_on_listen_fail": False,
            "auto_refine_max_attempts_per_asset": 2,
        },
    )
    monkeypatch.setattr("interview_mux.stages.sound_design_stages.run_sfx_prompt_refine", _fake_refine)
    monkeypatch.setattr(sfx_mmaudio, "_regenerate_assets_after_refine", lambda *a, **k: None)

    sfx_mmaudio.maybe_auto_refine(ctx, "mmaudio_sfx_flow1")
    assert refined == ["bed_01"]


def test_sync_post_listen_gate_state_block_mix(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {
            "sound_design": {
                "post_listen_gate_mode": "block_mix",
                "block_mix_on_mmaudio_qa_fail": True,
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "gate_sync")
    ctx.write_json(
        "run_meta.json",
        {"sfx_listen_results": [{"asset_id": "bed_01", "result": "fail"}]},
        skip_handoff=True,
    )
    ctx.write_json(
        "sound_design/mmaudio_qa.json",
        {"version": 1, "assets": [{"asset_id": "sting_01", "verdict": "fail"}]},
        skip_handoff=True,
    )
    from interview_mux.gates import sync_post_listen_gate_state

    state = sync_post_listen_gate_state(ctx)
    assert state["mode"] == "block_mix"
    assert set(state["blocked_assets"]) == {"bed_01", "sting_01"}
    meta = ctx.read_json("run_meta.json")
    assert meta["post_listen_gate_state"]["blocked_assets"] == ["bed_01", "sting_01"]
