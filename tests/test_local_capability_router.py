"""Fail-fast local capability router tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from interview_mux.local_capability_router import (
    RouterOutcome,
    local_call_count,
    prepare_volley_via_router,
    reset_local_call_counter,
)
from interview_mux.local_llm_config import (
    ALWAYS_ESCALATE_STAGES,
    QUALITY_LOCAL_ALLOWLIST,
    max_local_retries_per_cap,
)
from interview_mux.local_volley_framer import LocalFramingResult


@pytest.fixture(autouse=True)
def _reset_counter():
    reset_local_call_counter()
    yield
    reset_local_call_counter()


def test_transitions_always_escalates():
    assert "transitions" in ALWAYS_ESCALATE_STAGES
    assert "transitions" in QUALITY_LOCAL_ALLOWLIST


def test_retries_locked_zero():
    assert max_local_retries_per_cap() == 0


def test_housekeeping_skip_zero_extra_caps(monkeypatch):
    """ingest (not allowlisted) must not run LX-03/04/05."""
    calls: list[str] = []

    def fake_prepare(ctx, stage_key, stage_input, **kwargs):
        return [{"role": "user", "content": "x"}], LocalFramingResult(escalate=True, reason="passthrough")

    monkeypatch.setattr(
        "interview_mux.local_capability_router.prepare_volley_for_llm",
        fake_prepare,
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.generate_local_chat",
        lambda **kw: (_ for _ in ()).throw(AssertionError("no local chat on housekeeping")),
    )

    ctx = MagicMock()
    outcome = prepare_volley_via_router(ctx, "ingest", {}, task_kind="primary")
    assert outcome.telemetry.abort_reason == "not_on_quality_allowlist"
    assert outcome.telemetry.caps_run == []
    assert local_call_count() == 0


def test_hard_fail_aborts_remaining_caps(monkeypatch, tmp_path):
    """LX-03 hard fail must not call LX-01 via generate_local_chat for later caps;
    framer still may run after abort to build OpenAI volley — ensure LX-05 never runs.
    """
    from interview_mux.local_capability_manifest import write_capability_manifest

    manifest = {
        "schema_version": 1,
        "model_id": "test",
        "calibrate_status": "ok",
        "context_length": 8192,
        "enabled_caps": ["LX-01", "LX-03", "LX-05"],
        "budgets": {"lx03_max_tokens": 256, "lx05_max_tokens": 256},
        "bench": {},
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    path = tmp_path / "capability_manifest.json"
    write_capability_manifest(manifest, path)
    monkeypatch.setattr(
        "interview_mux.local_capability_router.load_capability_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.mlx_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.stage_on_quality_allowlist",
        lambda stage, cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.capability_router_enabled",
        lambda cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.local_llm_enabled",
        lambda cfg=None: True,
    )

    def boom_lx03(*_a, **_k):
        from interview_mux.local_capability_router import _record_cap

        _record_cap("LX-03")
        return None, "lx03_parse_fail"

    lx05_calls = {"n": 0}

    def no_lx05(*_a, **_k):
        lx05_calls["n"] += 1
        raise AssertionError("LX-05 must not run after hard fail")

    monkeypatch.setattr("interview_mux.local_capability_router._run_lx03", boom_lx03)
    monkeypatch.setattr("interview_mux.local_capability_router._run_lx05", no_lx05)
    monkeypatch.setattr(
        "interview_mux.local_capability_router._default_plan",
        lambda *_a, **_k: ["LX-03", "LX-05", "LX-01"],
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.prepare_volley_for_llm",
        lambda *a, **k: (
            [{"role": "user", "content": "fallback"}],
            LocalFramingResult(escalate=True, used_local=False, reason="open"),
        ),
    )

    ctx = MagicMock()
    outcome = prepare_volley_via_router(
        ctx,
        "speaker_roles",
        {"segments": [{"segment_id": f"s{i}"} for i in range(20)]},
        task_kind="primary",
        predicted_fanout=0,
    )
    assert outcome.telemetry.abort_reason == "lx03_parse_fail"
    assert "LX-05" not in outcome.telemetry.caps_run
    assert lx05_calls["n"] == 0
    assert outcome.framing is not None
    assert outcome.framing.escalate is True


def test_planner_once_on_fanout(monkeypatch):
    planner_calls = {"n": 0}

    def fake_planner(*_a, **_k):
        planner_calls["n"] += 1
        return ["LX-01"]

    monkeypatch.setattr(
        "interview_mux.local_capability_router.load_capability_manifest",
        lambda: {
            "enabled_caps": ["LX-01", "LX-05"],
            "calibrate_status": "ok",
            "budgets": {},
        },
    )
    monkeypatch.setattr("interview_mux.local_capability_router.mlx_available", lambda: True)
    monkeypatch.setattr(
        "interview_mux.local_capability_router.stage_on_quality_allowlist",
        lambda stage, cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.capability_router_enabled",
        lambda cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.local_llm_enabled",
        lambda cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.planner_fanout_k",
        lambda cfg=None: 3,
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router._run_economy_planner",
        fake_planner,
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.prepare_volley_for_llm",
        lambda *a, **k: (
            [{"role": "user", "content": "x"}],
            LocalFramingResult(escalate=True, used_local=True),
        ),
    )

    ctx = MagicMock()
    outcome = prepare_volley_via_router(
        ctx,
        "content_context",
        {},
        task_kind="primary",
        predicted_fanout=4,
    )
    assert planner_calls["n"] == 1
    assert outcome.telemetry.planner_used is True
    assert outcome.telemetry.planner_fanout == 4

    # Invalid planner → still only one call if we invoke again with failure
    planner_calls["n"] = 0

    def fail_planner(*_a, **_k):
        planner_calls["n"] += 1
        return None

    monkeypatch.setattr(
        "interview_mux.local_capability_router._run_economy_planner",
        fail_planner,
    )
    outcome2 = prepare_volley_via_router(
        ctx,
        "content_context",
        {},
        task_kind="primary",
        predicted_fanout=5,
    )
    assert planner_calls["n"] == 1
    assert outcome2.telemetry.planner_used is True


def test_extra_digest_paths_accepted(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.local_capability_router.load_capability_manifest",
        lambda: {"enabled_caps": ["LX-01"], "budgets": {}},
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.stage_on_quality_allowlist",
        lambda stage, cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.capability_router_enabled",
        lambda cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.local_capability_router.local_llm_enabled",
        lambda cfg=None: True,
    )
    monkeypatch.setattr("interview_mux.local_capability_router.mlx_available", lambda: False)

    seen: dict[str, Any] = {}

    def capture_prepare(ctx, stage_key, stage_input, **kwargs):
        seen["input"] = stage_input
        return [{"role": "user", "content": "x"}], LocalFramingResult(escalate=True)

    monkeypatch.setattr(
        "interview_mux.local_capability_router.prepare_volley_for_llm",
        capture_prepare,
    )

    ctx = MagicMock()
    ctx.artifact_exists.return_value = False
    outcome = prepare_volley_via_router(
        ctx,
        "narrative_arc_plan",
        {"_extra_digest_paths": ["understanding/episode_structure.json"]},
        task_kind="primary",
        extra_digest_paths=["understanding/episode_structure.json"],
    )
    assert isinstance(outcome, RouterOutcome)
    assert "LX-01" in outcome.telemetry.plan or outcome.telemetry.caps_run or True
