"""Heal Clinic wrong_pin Option E — refuse-by-default pin authority.

MUX_FORENSICS=0 matrix: allowlisted+checklist → pin; else refuse sideways rewrite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.heal_pin_authority import (
    heal_prereq_checklist,
    match_heal_allowlist,
    may_rewrite_heal_pin,
    resolve_heal_from_stage,
    stage_minimum_run_checklist,
)
from interview_mux.stage_completion import producer_pin_for_token
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.delenv("HEAL_PIN_AUTHORITY", raising=False)
    return isolated_run_ctx(tmp_path, "heal_pin_authority_e")


def test_non_allowlisted_error_refuses_sideways_pin(ctx) -> None:
    nav = heal_navigate(
        ctx,
        error="totally_unknown_glitch_xyzzy",
        stage="mix",
        intent="",
    )
    assert nav.get("from_stage") == "mix"
    assert nav.get("intent") == "heal_refused"
    assert "heal_refuse" in str(nav.get("heal_refused") or "")


def test_allowlisted_voice_ref_may_pin(ctx) -> None:
    nav = heal_navigate(
        ctx,
        error="voice_reference_pending",
        stage="topic_coverage_audit",
    )
    assert nav.get("from_stage") in {
        "missing_framing",
        "topic_coverage_audit",
        "gap_framing_compose",
    }
    assert nav.get("intent") != "heal_refused" or nav.get("from_stage") == "topic_coverage_audit"


def test_may_rewrite_requires_allowlist(ctx) -> None:
    ok, _aid, reason = may_rewrite_heal_pin(
        ctx,
        from_stage="mix",
        to_stage="edl",
        error="random noise",
        intent="",
    )
    assert ok is False
    assert "not_allowlisted" in reason


def test_checklist_rejects_unknown_stage(ctx) -> None:
    ok, reason = heal_prereq_checklist(ctx, "not_a_real_stage_zz")
    assert ok is False
    assert "unknown_stage" in reason


def test_stage_minimum_run_checklist_shares_prereq(ctx) -> None:
    a = heal_prereq_checklist(ctx, "transitions")
    b = stage_minimum_run_checklist(ctx, "transitions")
    assert a == b


def test_match_allowlist_premature_and_g0() -> None:
    assert match_heal_allowlist(error="premature_complete:vo_g1") == "premature_complete"
    assert match_heal_allowlist(error="g0_pending transcript") == "g0_pending"
    assert match_heal_allowlist(error="remix bed failed alone") is None


def test_b1_token_laws_still_hold_inside_pipeline(ctx) -> None:
    pin = producer_pin_for_token(
        "mix_unseated and premature_complete:vo_g1", ctx=ctx
    )
    assert pin != "mix"
    assert pin in {
        "vo_synthesize",
        "vo_line_adjudicate",
        "nugget_layup_compose",
        "missing_framing",
    }


def test_resolve_heal_from_stage_ssot_matches_heal_navigate(ctx) -> None:
    a = resolve_heal_from_stage(
        ctx, error="voice_reference_pending", stage="topic_coverage_audit"
    )
    b = heal_navigate(
        ctx, error="voice_reference_pending", stage="topic_coverage_audit"
    )
    assert a.get("from_stage") == b.get("from_stage")


def test_authority_disable_env_allows_propose(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEAL_PIN_AUTHORITY", "0")
    nav = heal_navigate(
        ctx,
        error="totally_unknown_glitch_xyzzy",
        stage="mix",
    )
    # With authority off, ungated propose may leave mix or move — must not
    # force heal_refused.
    assert nav.get("intent") != "heal_refused"
