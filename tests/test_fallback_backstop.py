"""Refusal feedback is fed to the model once; a declared fallback keeps the old version at the cap (ISSUES 124)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux import fallback_backstop as fb
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "backstop")


def test_refusal_reasons_are_fed_back_once_per_distinct_set(ctx) -> None:
    doc = fb.note_refusal(ctx, "sound_design_plan", ["asset count 8 exceeds cap 7", "heal_success:pre_flush_soft_refused"])
    assert doc["reasons"] == ["asset count 8 exceeds cap 7"]
    assert fb.take_refusal_feedback(ctx, "sound_design_plan") == ["asset count 8 exceeds cap 7"]
    # The same reason set is not fed twice.
    assert fb.take_refusal_feedback(ctx, "sound_design_plan") == []
    # A new refusal with the same reasons stays consumed; a different set is fed.
    fb.note_refusal(ctx, "sound_design_plan", ["asset count 8 exceeds cap 7"])
    assert fb.take_refusal_feedback(ctx, "sound_design_plan") == []
    fb.note_refusal(ctx, "sound_design_plan", ["creative delivery missing music role:theme_outro"])
    assert fb.take_refusal_feedback(ctx, "sound_design_plan") == ["creative delivery missing music role:theme_outro"]
    fb.clear_refusal_feedback(ctx, "sound_design_plan")
    assert fb.take_refusal_feedback(ctx, "sound_design_plan") == []


def test_feedback_note_names_the_reasons() -> None:
    note = fb.feedback_note(["fewer prompts than SDP assets"])
    assert "PREVIOUS ATTEMPT REFUSED" in note and "fewer prompts than SDP assets" in note


def test_the_barrier_records_its_reasons(ctx, monkeypatch) -> None:
    from interview_mux import write_staging as ws

    class _Decision:
        action = "halt"
        acceptance_ok = False
        reasons = ["fewer prompts than SDP assets", "heal_success:pre_flush_soft_refused"]

    monkeypatch.setattr("interview_mux.stage_resilience.validate_staged_before_flush", lambda c, s: _Decision())
    monkeypatch.setattr("interview_mux.stage_resilience.record_resilience_event", lambda *a, **k: None)
    monkeypatch.setattr("interview_mux.operator_action_trace.begin_action", lambda *a, **k: "t")
    monkeypatch.setattr("interview_mux.operator_action_trace.end_action", lambda *a, **k: None)
    with pytest.raises(ws.WriteApprovalBlockedError):
        ws.approve_stage_writes(ctx, "sfx_prompt_craft")
    assert fb.take_refusal_feedback(ctx, "sfx_prompt_craft") == ["fewer prompts than SDP assets"]


def test_the_runner_appends_the_feedback_to_the_user_turn() -> None:
    import interview_mux.llm_simple as m

    src = Path(m.__file__).read_text(encoding="utf-8")
    assert "take_refusal_feedback(ctx, stage_key)" in src
    assert "user_content = user_payload + refusal_note + retry_note" in src


def test_declared_fallback_keeps_an_acceptable_old_version(ctx, monkeypatch) -> None:
    monkeypatch.setattr(fb, "prior_committed_artifact", lambda c, s: "understanding/sound_design_plan.json")
    marks: list[str] = []

    def _heal(c, stage, *, force=False):
        marks.append(stage)
        m = c.final_path(".stage_done", stage)
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text("")
        return {"marked": True}

    monkeypatch.setattr("interview_mux.stage_completion.heal_or_refuse_mark", _heal)
    decision = fb.apply_declared_fallback(ctx, "sound_design_plan", "LLM stage incomplete: status=partial")
    assert decision and decision["fallback"] == "keep_prior_committed_artifact"
    assert marks == ["sound_design_plan"]
    rows = [json.loads(l) for l in (ctx.run_dir / fb.DECISIONS_REL).read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["stage"] == "sound_design_plan"


def test_no_old_version_means_no_fallback(ctx, monkeypatch) -> None:
    monkeypatch.setattr(fb, "prior_committed_artifact", lambda c, s: None)
    assert fb.apply_declared_fallback(ctx, "sound_design_plan", "x") is None
    assert not (ctx.run_dir / fb.DECISIONS_REL).exists()


def test_the_walk_consults_the_fallback_before_halting() -> None:
    import interview_mux.homunculus.agenda as agenda

    src = Path(agenda.__file__).read_text(encoding="utf-8")
    body = src[src.find("def note_identical_stage_error") :]
    assert body.find("apply_declared_fallback(") < body.find('meta["needs_operator"] = True')


def test_transient_openai_errors_are_retried_with_backoff() -> None:
    import openai

    from interview_mux.stages.llm_runner import create_with_transient_retry

    calls = {"n": 0}
    waits: list[float] = []

    def _call():
        calls["n"] += 1
        if calls["n"] < 3:
            raise openai.APIConnectionError(request=None)  # type: ignore[arg-type]
        return "ok"

    assert create_with_transient_retry(_call, stage="x", sleep=waits.append) == "ok"
    assert calls["n"] == 3
    assert waits == [2.0, 4.0]


def test_non_transient_errors_are_not_retried() -> None:
    from interview_mux.stages.llm_runner import create_with_transient_retry

    calls = {"n": 0}

    def _call():
        calls["n"] += 1
        raise ValueError("bad request")

    with pytest.raises(ValueError):
        create_with_transient_retry(_call, stage="x", sleep=lambda s: None)
    assert calls["n"] == 1


def test_an_optional_stage_without_an_old_version_is_skipped_through_its_stub(ctx, monkeypatch) -> None:
    monkeypatch.setattr(fb, "prior_committed_artifact", lambda c, s: None)
    stubbed: list[str] = []
    monkeypatch.setitem(fb.OPTIONAL_STAGE_SKIP_STUBS, "delivery_brief_build", lambda c, s: stubbed.append(s))
    monkeypatch.setattr(fb, "_mark_through_heal", lambda c, s: True)
    decision = fb.apply_declared_fallback(ctx, "delivery_brief_build", "LLM stage failed twice")
    assert decision and decision["fallback"] == "skip_stub"
    assert stubbed == ["delivery_brief_build"]


def test_a_required_stage_without_an_old_version_still_halts(ctx, monkeypatch) -> None:
    monkeypatch.setattr(fb, "prior_committed_artifact", lambda c, s: None)
    assert "full_master_ranking" not in fb.OPTIONAL_STAGE_SKIP_STUBS
    assert fb.apply_declared_fallback(ctx, "full_master_ranking", "x") is None
