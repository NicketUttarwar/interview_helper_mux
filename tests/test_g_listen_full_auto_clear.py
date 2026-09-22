"""Full-auto G-Listen auto-clear (master_finalize + mix) — Stage Clinic Wave 2.

Shared helper ``maybe_auto_clear_g_listen_for_full_auto``; Partial keeps block.
No mix render / local heavy ML.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from interview_mux.config import merged_config
from interview_mux.gates import (
    check_g_listen_pending,
    maybe_auto_clear_g_listen_for_full_auto,
    require_g_listen_clear,
)
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


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "g_listen_fa")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_default_g_listen_mode_is_warn() -> None:
    """P0-2: fleet default is advisory warn (not block)."""
    from interview_mux.config import merged_config

    mode = str((merged_config().get("sound_design") or {}).get("g_listen_mode") or "")
    assert mode == "warn"


def test_require_g_listen_clear_warn_does_not_stall(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defaults / warn mode: pending G-Listen logs but does not SystemExit."""
    patch_merged_config(monkeypatch, _cfg("warn"))
    _plant_critic(ctx)
    ctx.mutate_run_meta(
        lambda m: m.update(
            {
                "partial_auto": True,
                "run_mode": "partially-accelerated",
                "g_listen_pending": True,
            }
        )
    )
    require_g_listen_clear(ctx, stage="master_finalize")
    assert check_g_listen_pending(ctx) is True


def test_full_auto_require_g_listen_clear_does_not_stall(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MF-B2: Full-auto + g_listen_mode=block auto-clears at finalize gate."""
    patch_merged_config(monkeypatch, _cfg("block"))
    _plant_critic(ctx)
    ctx.mutate_run_meta(
        lambda m: m.update(
            {
                "full_auto": True,
                "run_mode": "full-auto",
                "g_listen_pending": True,
            }
        )
    )
    assert check_g_listen_pending(ctx) is True
    require_g_listen_clear(ctx, stage="master_finalize")
    assert check_g_listen_pending(ctx) is False
    meta = ctx.read_json("run_meta.json")
    assert meta.get("g_listen_cleared") is True
    assert meta.get("g_listen_pending") is False


def test_partial_require_g_listen_clear_still_blocks(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Partial + explicit block mode still stalls finalize until clear."""
    patch_merged_config(monkeypatch, _cfg("block"))
    _plant_critic(ctx)
    ctx.mutate_run_meta(
        lambda m: m.update(
            {
                "partial_auto": True,
                "run_mode": "partially-accelerated",
                "g_listen_pending": True,
            }
        )
    )
    with pytest.raises(SystemExit, match="G-Listen pending"):
        require_g_listen_clear(ctx, stage="master_finalize")
    assert check_g_listen_pending(ctx) is True


def test_full_auto_helper_after_remaster_arm(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MIX-B3 / remaster: junction may still arm; product helper clears Full-auto."""
    patch_merged_config(monkeypatch, _cfg("block"))
    _plant_critic(ctx)
    ctx.mutate_run_meta(lambda m: m.update({"full_auto": True, "run_mode": "full-auto"}))
    _set_g_listen_pending_after_remaster(ctx)
    assert ctx.read_json("run_meta.json").get("g_listen_pending") is True
    assert (
        maybe_auto_clear_g_listen_for_full_auto(
            ctx, stage="mix", reason="full_auto_after_successful_mix"
        )
        is True
    )
    assert check_g_listen_pending(ctx) is False


def test_partial_helper_noop_keeps_pending(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_merged_config(monkeypatch, _cfg("block"))
    _plant_critic(ctx)
    ctx.mutate_run_meta(
        lambda m: m.update(
            {
                "partial_auto": True,
                "run_mode": "partially-accelerated",
                "g_listen_pending": True,
            }
        )
    )
    assert (
        maybe_auto_clear_g_listen_for_full_auto(
            ctx, stage="mix", reason="full_auto_after_successful_mix"
        )
        is False
    )
    assert check_g_listen_pending(ctx) is True


def test_hx5_full_auto_finalize_clears_after_rearm(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remaster re-arm + Full-auto finalize gate: no permanent stall (product path)."""
    patch_merged_config(monkeypatch, _cfg("block_mix"))
    _plant_critic(ctx)
    ctx.mutate_run_meta(lambda m: m.update({"full_auto": True, "run_mode": "full-auto"}))
    _set_g_listen_pending_after_remaster(ctx)
    assert check_g_listen_pending(ctx) is True
    require_g_listen_clear(ctx, stage="master_finalize")
    assert check_g_listen_pending(ctx) is False
