"""The in-process orchestrator: two human gates, one engine (gui-gates-only)."""

from __future__ import annotations

import os

import pytest

from run_fixtures import isolated_run_ctx

from interview_mux import orchestrator as orch


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    c = isolated_run_ctx(tmp_path, "exec_orchestrator")
    monkeypatch.setattr("interview_mux.driver_singleton.claim_driver_run", lambda c, **k: {})
    monkeypatch.setattr("interview_mux.driver_singleton.release_driver_run", lambda c: True)
    monkeypatch.setattr(orch, "_write_pointer", lambda rid: None)
    return c


class _Phases:
    """Scripted run_analysis / run_delivery with a call log."""

    def __init__(self, analysis: list, delivery: list) -> None:
        self.analysis = list(analysis)
        self.delivery = list(delivery)
        self.calls: list[tuple[str, dict]] = []

    def _next(self, name: str, script: list, kwargs: dict) -> None:
        self.calls.append((name, kwargs))
        step = script.pop(0) if script else None
        if isinstance(step, BaseException):
            raise step

    def run_analysis(self, ctx, **kwargs) -> None:
        self._next("analysis", self.analysis, kwargs)

    def run_delivery(self, ctx, **kwargs) -> None:
        self._next("delivery", self.delivery, kwargs)


def _wire(monkeypatch, phases: _Phases, *, complete, gates=None) -> None:
    monkeypatch.setattr("interview_mux.pipeline.run_analysis", phases.run_analysis)
    monkeypatch.setattr("interview_mux.pipeline.run_delivery", phases.run_delivery)
    monkeypatch.setattr("interview_mux.execution_status.pipeline_complete", complete)
    monkeypatch.setattr(orch, "clear_operator_gates", gates or (lambda c, **k: []))


def test_full_auto_runs_both_phases_and_never_waits(ctx, monkeypatch) -> None:
    phases = _Phases(analysis=[None], delivery=[None])
    _wire(monkeypatch, phases, complete=lambda c: True)
    slept: list[float] = []
    o = orch.Orchestrator(ctx, mode="full-auto", log=lambda s: None, sleep=slept.append)
    assert o.run() == 0
    assert [n for n, _ in phases.calls] == ["analysis", "delivery"]
    # Full-auto: delivery runs to the end, no until_stage, no gate wait.
    assert phases.calls[1][1].get("until_stage") is None
    assert slept == []
    meta = ctx.read_json("run_meta.json")
    assert meta["orchestrator"]["active"] is False
    assert ctx.read_json("gui_job.json")["status"] == "done"


def test_partial_waits_at_g0_and_before_publish(ctx, monkeypatch) -> None:
    state = {"g0_pending": True, "signed": False}
    monkeypatch.setattr(
        "interview_mux.gates.check_transcript_review_pending", lambda c: state["g0_pending"]
    )
    monkeypatch.setattr(
        "interview_mux.v2.config.effective_delivery_order",
        lambda: ("edl", "mix", "master_finalize", "episode_cover_generate", "podcast_publish"),
    )
    phases = _Phases(
        analysis=[SystemExit("transcript review pending"), None],
        delivery=[None, None],
    )
    published = {"done": False}
    _wire(monkeypatch, phases, complete=lambda c: published["done"])

    def _sleep(_s: float) -> None:
        # The operator acts while the engine polls without the run lock.
        if state["g0_pending"]:
            state["g0_pending"] = False
            return
        if not state["signed"]:
            state["signed"] = True
            ctx.mutate_run_meta(lambda m: m.__setitem__("g_publish_cleared", True))
            published["done"] = True

    o = orch.Orchestrator(ctx, mode="partially-accelerated", log=lambda s: None, sleep=_sleep)
    assert o.run() == 0
    names = [n for n, _ in phases.calls]
    assert names == ["analysis", "analysis", "delivery", "delivery"]
    # First delivery stops one stage short of podcast_publish; the second,
    # after sign-off, runs to the end.
    assert phases.calls[2][1]["until_stage"] == "episode_cover_generate"
    assert phases.calls[3][1].get("until_stage") is None


def test_partial_never_signs_off_g0_itself(ctx, monkeypatch) -> None:
    marked: list[str] = []
    monkeypatch.setattr("interview_mux.gates.check_transcript_review_pending", lambda c: True)
    monkeypatch.setattr(
        "interview_mux.stages.transcript_review.mark_transcript_review_complete",
        lambda c: marked.append("g0"),
    )
    # The other consent gates are not pending in this fixture; only G0 matters.
    for name in (
        "check_gap_framing_decision_pending",
        "check_gap_delivery_pending",
        "check_voice_reference_pending",
        "check_clone_consent_pending",
    ):
        monkeypatch.setattr(f"interview_mux.gap_vo_gates.{name}", lambda c: False)
    monkeypatch.setattr("interview_mux.gates.check_timeline_optimizer_pending", lambda c: False)
    monkeypatch.setattr(
        "interview_mux.timeline_optimizer.state.load_optimizer_state", lambda c: {}
    )
    ctx.write_json("transcript/review_queue.json", {"chunks": []}, skip_handoff=True)
    assert orch.clear_operator_gates(ctx, sign_off_g0=False) == []
    assert marked == []
    assert orch.clear_operator_gates(ctx, sign_off_g0=True) == ["transcript_review"]
    assert marked == ["g0"]


def test_a_failure_naming_its_remedy_is_dispatched_once(ctx, monkeypatch) -> None:
    # Two identical failures with no progress, then the remedy lands and the
    # next pass succeeds. The first retry is the plain re-entry; only a retry
    # that fails again without progress dispatches the named stage.
    phases = _Phases(
        analysis=[None],
        delivery=[
            RuntimeError("Delivery incomplete; resume=mix"),
            RuntimeError("Delivery incomplete; resume=mix"),
            None,
        ],
    )
    dispatched: list[str] = []

    def _single(c, stage: str) -> None:
        dispatched.append(stage)
        c._mark_done_raw = True
        c.mark_done(stage)
        c._mark_done_raw = False

    monkeypatch.setattr("interview_mux.pipeline.run_single_stage", _single)
    _wire(monkeypatch, phases, complete=lambda c: True)
    lines: list[str] = []
    o = orch.Orchestrator(ctx, mode="full-auto", log=lines.append, sleep=lambda s: None)
    assert o.run() == 0, "\n".join(lines)
    assert dispatched == ["mix"], "\n".join(lines)
    assert [n for n, _ in phases.calls] == ["analysis", "delivery", "delivery", "delivery"], (
        "\n".join(lines)
    )


def test_gate_timeout_stops_a_partial_run_cleanly(ctx, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.gates.check_transcript_review_pending", lambda c: True)
    phases = _Phases(analysis=[SystemExit("transcript review pending")], delivery=[])
    _wire(monkeypatch, phases, complete=lambda c: False)
    clock = {"t": 0.0}
    monkeypatch.setattr(orch.time, "monotonic", lambda: clock["t"])

    def _sleep(s: float) -> None:
        clock["t"] += 100.0

    o = orch.Orchestrator(
        ctx, mode="partially-accelerated", gate_timeout_sec=60, log=lambda s: None, sleep=_sleep
    )
    assert o.run() == 1
    assert ctx.read_json("gui_job.json")["status"] == "error"
    assert ctx.read_json("run_meta.json")["orchestrator"]["active"] is False


def test_orchestrator_owns_run_only_while_its_process_lives(ctx) -> None:
    assert orch.orchestrator_owns_run(ctx) is None
    ctx.mutate_run_meta(
        lambda m: m.__setitem__("orchestrator", {"active": True, "pid": os.getpid()})
    )
    assert orch.orchestrator_owns_run(ctx)["pid"] == os.getpid()
    ctx.mutate_run_meta(lambda m: m.__setitem__("orchestrator", {"active": True, "pid": 2**22}))
    assert orch.orchestrator_owns_run(ctx) is None
    ctx.mutate_run_meta(lambda m: m.__setitem__("orchestrator", {"active": False, "pid": os.getpid()}))
    assert orch.orchestrator_owns_run(ctx) is None


def test_resume_hint_reads_the_three_remedy_shapes() -> None:
    assert orch.resume_hint("Delivery incomplete; resume=mix") == "mix"
    assert orch.resume_hint("seed order: complete air_contract_sanitize before running x") == (
        "air_contract_sanitize"
    )
    assert orch.resume_hint("recut/fuse/omit at junction_snip_qa first") == "junction_snip_qa"
    assert orch.resume_hint("nothing here") is None
