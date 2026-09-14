"""HX-5: remaster re-arms g_listen_pending in warn, block, and block_mix.

Skipped / cleared / refused_low_gain still do not re-arm.
check_g_listen_pending (critic-alone) is unchanged.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from interview_mux.config import merged_config
from interview_mux.gates import check_g_listen_pending
from interview_mux.junction_snip_qa import _set_g_listen_pending_after_remaster
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, patch_merged_config


def _cfg(mode: str) -> dict[str, Any]:
    cfg = deepcopy(merged_config())
    sd = dict(cfg.get("sound_design") or {})
    sd["g_listen_mode"] = mode
    cfg["sound_design"] = sd
    return cfg


def _plant_critic(ctx: RunContext, *, recommended: bool = True) -> None:
    path = ctx.final_path("master", "listen_critic.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"g_listen_recommended": recommended, "quality_score": 0.4}),
        encoding="utf-8",
    )


def _pending(ctx: RunContext) -> bool:
    if not ctx.artifact_exists("run_meta.json"):
        return False
    meta = ctx.read_json("run_meta.json")
    return bool(isinstance(meta, dict) and meta.get("g_listen_pending"))


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hx5_g_listen")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hx5_block_rearms(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_merged_config(monkeypatch, _cfg("block"))
    _plant_critic(ctx)
    _set_g_listen_pending_after_remaster(ctx)
    assert _pending(ctx) is True


def test_hx5_block_mix_rearms(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_merged_config(monkeypatch, _cfg("block_mix"))
    _plant_critic(ctx)
    _set_g_listen_pending_after_remaster(ctx)
    assert _pending(ctx) is True


def test_hx5_warn_rearms(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_merged_config(monkeypatch, _cfg("warn"))
    _plant_critic(ctx)
    _set_g_listen_pending_after_remaster(ctx)
    assert _pending(ctx) is True
    meta = ctx.read_json("run_meta.json")
    assert meta.get("g_listen_quality_score") == 0.4


def test_hx5_warn_honors_cleared(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx.mutate_run_meta(lambda m: m.update({"g_listen_cleared": True}))
    patch_merged_config(monkeypatch, _cfg("warn"))
    _plant_critic(ctx)
    _set_g_listen_pending_after_remaster(ctx)
    assert _pending(ctx) is False


def test_hx5_warn_honors_skipped(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx.mutate_run_meta(lambda m: m.update({"g_listen_skipped": True}))
    patch_merged_config(monkeypatch, _cfg("warn"))
    _plant_critic(ctx)
    _set_g_listen_pending_after_remaster(ctx)
    assert _pending(ctx) is False


def test_hx5_block_after_cleared_stays_cleared(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.mutate_run_meta(
        lambda m: m.update({"g_listen_cleared": True, "g_listen_pending": False})
    )
    patch_merged_config(monkeypatch, _cfg("block"))
    _plant_critic(ctx)
    _set_g_listen_pending_after_remaster(ctx)
    assert _pending(ctx) is False
    assert check_g_listen_pending(ctx) is False


def test_hx5_refused_low_gain_warn_does_not_rearm(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = ctx.final_path("mastering", "listen_delight_remutate.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"status": "refused_low_gain"}), encoding="utf-8")
    patch_merged_config(monkeypatch, _cfg("warn"))
    _plant_critic(ctx)
    _set_g_listen_pending_after_remaster(ctx)
    assert _pending(ctx) is False


def test_hx5_check_still_true_from_critic_when_pending_unset(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_merged_config(monkeypatch, _cfg("block"))
    _plant_critic(ctx)
    assert _pending(ctx) is False
    assert check_g_listen_pending(ctx) is True


def test_hx5_budget_exhausted_does_not_ok_another_remaster(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.thrash_hardening import (
        JUNCTION_REMASTER_GEN_CAP,
        junction_remaster_budget_ok,
    )

    gen = "1"
    ctx.write_json(
        "operator/junction_remaster_budget.json",
        {"by_generation": {gen: JUNCTION_REMASTER_GEN_CAP}},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening._junction_seating_generation",
        lambda _ctx: 1,
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.junction_oscillation_halted",
        lambda _ctx: False,
    )
    ok, used = junction_remaster_budget_ok(ctx)
    assert ok is False
    assert used >= JUNCTION_REMASTER_GEN_CAP


def test_hx5_full_auto_skip_after_rearm(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.automation_run import is_full_auto_run
    from interview_mux.gates import clear_g_listen

    patch_merged_config(monkeypatch, _cfg("block_mix"))
    _plant_critic(ctx)
    ctx.mutate_run_meta(lambda m: m.update({"full_auto": True, "run_mode": "full-auto"}))
    _set_g_listen_pending_after_remaster(ctx)
    assert _pending(ctx) is True
    meta = ctx.read_json("run_meta.json")
    assert is_full_auto_run(meta) is True
    assert check_g_listen_pending(ctx) is True
    clear_g_listen(ctx, skipped=True)
    assert _pending(ctx) is False
    assert check_g_listen_pending(ctx) is False
