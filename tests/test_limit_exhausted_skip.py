"""Skip LLM retry storms when a homunculus identity is already exhausted."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.homunculus.budget import LimitExhausted
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_limit_skip", create=True)
    init_run_meta_for_test(run)
    return run


def test_seam_adjudicate_returns_none_when_exhausted(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.segment_fuse import _llm_adjudicate_batch

    monkeypatch.setattr(
        "interview_mux.homunculus.budget.identity_exhausted", lambda *_a, **_k: True
    )

    def _boom(*_a: object, **_k: object) -> dict:
        raise AssertionError("seam LLM must not run when identity is exhausted")

    monkeypatch.setattr("interview_mux.stages.llm_runner.run_prompt_envelope", _boom)
    monkeypatch.setattr(
        "interview_mux.stages.llm_runner.load_system_prompt", lambda *_a, **_k: "sys"
    )
    out = _llm_adjudicate_batch(ctx, [{"pair_id": "p1", "left_id": "a", "right_id": "b"}])
    assert out is None


def test_seam_adjudicate_stops_on_limit_exhausted(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.segment_fuse import _llm_adjudicate_batch

    monkeypatch.setattr(
        "interview_mux.homunculus.budget.identity_exhausted", lambda *_a, **_k: False
    )
    calls = {"n": 0}

    def _raise(*_a: object, **_k: object) -> dict:
        calls["n"] += 1
        raise LimitExhausted(
            "connector_seam_adjudicate",
            "max_invokes_per_identity",
            {"used": 3, "cap": 3},
        )

    monkeypatch.setattr("interview_mux.stages.llm_runner.run_prompt_envelope", _raise)
    monkeypatch.setattr(
        "interview_mux.stages.llm_runner.load_system_prompt", lambda *_a, **_k: "sys"
    )
    out = _llm_adjudicate_batch(ctx, [{"pair_id": "p1", "left_id": "a", "right_id": "b"}])
    assert out is None
    assert calls["n"] == 1


def test_junction_feel_stops_retries_on_limit_exhausted(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.junction_snip_qa import run_junction_feel_audit

    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.build_feel_audit_context",
        lambda *_a, **_k: {"junctions": []},
    )
    calls = {"n": 0}

    def _raise(*_a: object, **_k: object) -> dict:
        calls["n"] += 1
        raise LimitExhausted(
            "junction_feel_audit", "max_invokes_per_identity", {"used": 3, "cap": 3}
        )

    monkeypatch.setattr("interview_mux.stages.llm_runner.run_prompt_envelope", _raise)
    audit = run_junction_feel_audit(ctx, {"findings": []})
    assert audit["verdict"] == "unavailable"
    assert calls["n"] == 1
