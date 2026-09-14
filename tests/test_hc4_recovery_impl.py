"""HC-4: recovery dispatch must run impl(resume_stage), not the consumer host.

Do not start a run. HV-2 pin stays. Depth cap 2 stays.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from interview_mux.homunculus.runtime import dispatch_stage
from interview_mux.run_context import RunContext
from interview_mux.stage_input_checks import StageInputError, StageInputIssue
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hc4_recovery")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _quiet_dispatch_rails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime._seed_prereq_block",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.upstream_stale_blockers",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.mix_epoch_block",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.vo_synthesize_stability_block",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime.check_dispatch",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime.check_audio_serialize",
        lambda *_a, **_k: None,
    )


def test_hc4_recovery_impl_receives_resume_stage(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_dispatch_rails(monkeypatch)
    ran: list[str] = []

    def _issues(_ctx: RunContext, stage: str):
        if stage == "mix":
            return [StageInputIssue(message="VO coverage not rendered", kind="prerequisite")]
        return []

    monkeypatch.setattr(
        "interview_mux.stage_input_checks.collect_stage_input_issues",
        _issues,
    )
    monkeypatch.setattr(
        "interview_mux.recovery_controller.handle_stage_failure",
        lambda *_a, **_k: SimpleNamespace(status="recovered", resume_stage="vo_synthesize"),
    )
    dispatch_stage(ctx, "mix", lambda sid: ran.append(sid), source="test")
    assert ran == ["vo_synthesize"]


def test_hc4_resume_host_failure_does_not_run_consumer(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_dispatch_rails(monkeypatch)
    ran: list[str] = []

    def _issues(_ctx: RunContext, stage: str):
        if stage == "mix":
            return [StageInputIssue(message="missing WAV", kind="prerequisite")]
        return []

    def _impl(sid: str) -> None:
        ran.append(sid)
        if sid == "vo_synthesize":
            raise RuntimeError("resume host cannot run")

    monkeypatch.setattr(
        "interview_mux.stage_input_checks.collect_stage_input_issues",
        _issues,
    )
    monkeypatch.setattr(
        "interview_mux.recovery_controller.handle_stage_failure",
        lambda *_a, **_k: SimpleNamespace(status="recovered", resume_stage="vo_synthesize"),
    )
    with pytest.raises(StageInputError) as excinfo:
        dispatch_stage(ctx, "mix", _impl, source="test")
    assert excinfo.value.stage_id == "mix"
    assert ran == ["vo_synthesize"]
    assert "mix" not in ran[1:]


def test_hc4_depth_two_raises_without_third_hop(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_dispatch_rails(monkeypatch)
    hops: list[str] = []

    def _issues(_ctx: RunContext, stage: str):
        hops.append(stage)
        return [StageInputIssue(message=f"{stage} blocked", kind="prerequisite")]

    monkeypatch.setattr(
        "interview_mux.stage_input_checks.collect_stage_input_issues",
        _issues,
    )

    def _heal(_ctx, stage, _exc):
        nxt = {"mix": "vo_synthesize", "vo_synthesize": "master_finalize"}.get(
            stage, "transcribe"
        )
        return SimpleNamespace(status="recovered", resume_stage=nxt)

    monkeypatch.setattr(
        "interview_mux.recovery_controller.handle_stage_failure",
        _heal,
    )
    ran: list[str] = []
    with pytest.raises(StageInputError):
        dispatch_stage(ctx, "mix", lambda sid: ran.append(sid), source="test")
    assert hops == ["mix", "vo_synthesize", "master_finalize"]
    assert ran == []


def test_hc4_empty_resume_raises_without_impl(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_dispatch_rails(monkeypatch)
    monkeypatch.setattr(
        "interview_mux.stage_input_checks.collect_stage_input_issues",
        lambda *_a, **_k: [StageInputIssue(message="blocked", kind="prerequisite")],
    )
    monkeypatch.setattr(
        "interview_mux.recovery_controller.handle_stage_failure",
        lambda *_a, **_k: SimpleNamespace(status="recovered", resume_stage="   "),
    )
    ran: list[str] = []
    with pytest.raises(StageInputError):
        dispatch_stage(ctx, "mix", lambda sid: ran.append(sid), source="test")
    assert ran == []
