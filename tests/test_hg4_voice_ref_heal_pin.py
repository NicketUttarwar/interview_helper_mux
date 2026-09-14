"""HG-4: voice-ref heal pins missing_framing, never topic_coverage_audit.

Do not start a run. HG-1 sticky Yes and HG-5 high-gap compose stay open.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.heal_routing import classify_heal_error, resume_stage_for_error_class
from interview_mux.homunculus.agenda import remaining_stages, walk_seed_agenda
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    PRODUCER_PIN_TABLE,
    producer_pin_for_token,
    voice_ref_heal_resume_stage,
)
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hg4_voice_ref")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hg4_token_and_prose_pin_missing_framing_not_topic_coverage() -> None:
    assert PRODUCER_PIN_TABLE["voice_reference_pending"] == "missing_framing"
    assert producer_pin_for_token("voice_reference_pending") == "missing_framing"
    assert (
        producer_pin_for_token(
            "Voice reference gate: approve interviewer voice sample before gap framing LLM stages."
        )
        == "missing_framing"
    )
    assert (
        voice_ref_heal_resume_stage(
            error="Voice reference gate: approve interviewer voice sample.",
            stage="missing_framing",
        )
        == "missing_framing"
    )
    assert resume_stage_for_error_class("voice_reference_pending") == "missing_framing"


def test_hg4_heal_navigate_and_classify_pin_framing(ctx: RunContext) -> None:
    nav = heal_navigate(
        ctx,
        error="Voice reference gate: approve interviewer voice sample before gap framing LLM stages.",
        stage="missing_framing",
    )
    assert nav["from_stage"] == "missing_framing"
    assert nav["from_stage"] != "topic_coverage_audit"
    nav2 = heal_navigate(ctx, error="voice_reference_pending", stage="topic_coverage_audit")
    assert nav2["from_stage"] == "missing_framing"
    route = classify_heal_error(
        "Voice reference gate: approve interviewer voice sample.",
        ctx,
        stage="topic_coverage_audit",
    )
    assert route is not None
    assert route.from_stage == "missing_framing"


def test_hg4_delivery_remaining_empty_while_voice_ref_open(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.check_voice_reference_pending",
        lambda _c: True,
    )
    mark_done_raw(ctx, "missing_framing")
    rem = remaining_stages(ctx, "delivery")
    assert "topic_coverage_audit" not in rem
    assert rem == []


def test_hg4_walk_does_not_enter_topic_coverage(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.check_voice_reference_pending",
        lambda _c: True,
    )
    ran: list[str] = []
    monkeypatch.setattr(
        "interview_mux.pipeline.run_single_stage",
        lambda _ctx, sid: ran.append(sid),
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.prepare_delivery_guardrails",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.filter_delivery_candidates",
        lambda _ctx, stages: list(stages),
    )
    walk_seed_agenda(
        ctx,
        ["missing_framing", "topic_coverage_audit", "narrative_arc_plan"],
        reason="hg4",
    )
    assert "topic_coverage_audit" not in ran
    assert "narrative_arc_plan" not in ran
