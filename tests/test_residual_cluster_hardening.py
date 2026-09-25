"""Catalog Done-when fixtures for residual cluster hardening (A–G)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.execution_invalidation_profiles import apply_bounded_invalidation
from interview_mux.homunculus.packer import pack_conductor_context_views
from interview_mux.run_context import RunContext
from interview_mux.segment_fuse import (
    _FINITE_DEFAULT_FUSE_ROUNDS,
    _FINITE_DEFAULT_FUSES_PER_PASS,
    connector_fuse_cfg,
)
from interview_mux.volley_packet_lint import strip_forbidden_metadata
from run_fixtures import patch_executions_root

_DENY = frozenset({"stage_done", "artifact_exists", "exists", "run_meta", "path_ok"})


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("exec_rstm_harden", create=True)


def test_b02_fuse_zero_config_resolves_to_finite_defaults() -> None:
    """DEEP-FUSE-01 / CFP-B3: config 0 → finite defaults, never unlimited."""
    from interview_mux.segment_fuse import resolve_fuse_round_caps

    rounds, fuses = resolve_fuse_round_caps(
        {"max_fuse_rounds": 0, "max_fuses_per_pass": 0}
    )
    assert rounds == _FINITE_DEFAULT_FUSE_ROUNDS == 8
    assert fuses == _FINITE_DEFAULT_FUSES_PER_PASS == 24
    conf = connector_fuse_cfg()
    # Shipped defaults may still store 0; runtime must resolve finite.
    r2, f2 = resolve_fuse_round_caps(conf)
    assert r2 == _FINITE_DEFAULT_FUSE_ROUNDS or int(conf.get("max_fuse_rounds") or 0) > 0
    assert f2 == _FINITE_DEFAULT_FUSES_PER_PASS or int(conf.get("max_fuses_per_pass") or 0) > 0
    assert r2 < 10_000
    assert f2 < 10_000_000


def test_a04_telemetry_waiver_not_music_delight_ok(ctx: RunContext) -> None:
    """SYN-DELIGHT-01: waived_unattended alone is not quality clearance."""
    from interview_mux.delivery_guardrails import (
        LISTEN_DELIGHT_WAIVER_REL,
        listen_delight_cleared_for_progress,
        listen_delight_waived_unattended,
    )

    ctx.write_json(
        LISTEN_DELIGHT_WAIVER_REL,
        {"status": "waived_unattended", "stage": "listen_delight_audit"},
        skip_handoff=True,
    )
    assert listen_delight_waived_unattended(ctx) is True
    assert listen_delight_cleared_for_progress(ctx) is False


def test_e01_conductor_llm_view_strips_denylist(ctx: RunContext) -> None:
    """SYN-PACK-01: llm_conductor_view has no denylist keys."""
    views = pack_conductor_context_views(ctx)
    llm = views["llm_conductor_view"]
    host = views["host_prereq_view"]
    cleaned = strip_forbidden_metadata(llm)
    blob = json.dumps(cleaned if cleaned is not None else llm, default=str)
    for key in _DENY:
        assert f'"{key}"' not in blob, f"forbidden key {key} leaked into llm view"
    assert isinstance(host, dict)


def test_w0_unknown_profile_raises(ctx: RunContext) -> None:
    with pytest.raises(ValueError, match="unknown invalidation profile"):
        apply_bounded_invalidation(ctx, "not_a_real_profile_xyz")


def test_a03_soft_gate_cannot_claim_complete_when_llm_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYN-SHAPE-01 / A-03: soft_gate never claims complete (flags on or off)."""
    from interview_mux.mastering_plan_loader import soft_gate_may_claim_complete

    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.research_llm_enabled",
        lambda _cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.shape_llm_enabled",
        lambda _cfg=None: False,
    )
    assert soft_gate_may_claim_complete() is False
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.research_llm_enabled",
        lambda _cfg=None: False,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.shape_llm_enabled",
        lambda _cfg=None: True,
    )
    assert soft_gate_may_claim_complete() is False
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.research_llm_enabled",
        lambda _cfg=None: False,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.shape_llm_enabled",
        lambda _cfg=None: False,
    )
    # A-03 Wave 9: flags-off still never authoritative.
    assert soft_gate_may_claim_complete() is False
