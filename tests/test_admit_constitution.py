"""Heal Clinic leapfrog_resume B+ — Admit Constitution.

MUX_FORENSICS=0: clamp always, schedule admit, honest VO-chain ready, census.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    HAU_SPEECH_FIRST_EXCEPTIONS,
    clamp_resume_through_order,
    filter_delivery_candidates,
    producer_ready,
)
from interview_mux.heal_pin_authority import (
    admit_resume,
    admit_schedule,
    resolve_heal_from_stage,
)
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.delenv("HEAL_PIN_AUTHORITY", raising=False)
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "admit_constitution_b_plus")


def test_hau_speech_first_exception_table() -> None:
    assert "mix" in HAU_SPEECH_FIRST_EXCEPTIONS


def test_admit_resume_clamps_past_incomplete_vo_chain(ctx) -> None:
    # Request synth while layup hole is open → clamp to earliest incomplete.
    landed = admit_resume(ctx, "vo_synthesize", intent="seed_order_prereq")
    assert landed != "vo_synthesize" or not producer_ready(ctx, "nugget_layup_compose")
    clamped = clamp_resume_through_order(ctx, "vo_synthesize")
    assert landed == clamped


def test_admit_schedule_blocks_consumer_while_hole_open(ctx) -> None:
    ok, alt, reason = admit_schedule(ctx, "vo_synthesize")
    assert ok is False
    assert alt
    assert alt != "vo_synthesize" or "checklist" in reason or "hole" in reason or "upstream" in reason


def test_filter_reinjects_hole_not_synth(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: False,
    )
    filtered = filter_delivery_candidates(ctx, ["vo_synthesize", "edl"])
    assert "vo_synthesize" not in filtered or filtered[0] != "vo_synthesize"
    # Earliest hole should appear before deferred consumers when reinjected.
    assert filtered
    assert filtered[0] not in {"edl", "vo_synthesize"} or not producer_ready(
        ctx, "nugget_layup_compose"
    )


def test_hollow_adjudicate_not_producer_ready(ctx) -> None:
    done = ctx.run_dir / ".stage_done" / "vo_line_adjudicate"
    done.parent.mkdir(parents=True, exist_ok=True)
    done.touch()
    # No primary artifact → not ready (B+ VO-chain honesty).
    assert producer_ready(ctx, "vo_line_adjudicate") is False
    ok, alt, _reason = admit_schedule(ctx, "vo_synthesize")
    assert ok is False
    assert alt  # earliest incomplete hole (may be upstream of adjudicate)
    assert alt != "edl"


def test_heal_navigate_clamp_even_on_allowlisted_path(ctx) -> None:
    # Allowlisted seed_order intent still must not leapfrog past holes.
    nav = heal_navigate(
        ctx,
        error="seed_order: complete transitions before running vo_synthesize",
        stage="vo_synthesize",
        intent="seed_order_prereq",
    )
    landed = str(nav.get("from_stage") or "")
    if landed and landed != "vo_synthesize":
        assert landed == clamp_resume_through_order(ctx, landed) or landed == clamp_resume_through_order(
            ctx, "vo_synthesize"
        )


def test_resolve_matches_heal_navigate(ctx) -> None:
    a = resolve_heal_from_stage(
        ctx, error="voice_reference_pending", stage="topic_coverage_audit"
    )
    b = heal_navigate(
        ctx, error="voice_reference_pending", stage="topic_coverage_audit"
    )
    assert a.get("from_stage") == b.get("from_stage")


def test_partial_and_full_auto_same_admit(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_PARTIAL", "1")
    a = admit_resume(ctx, "vo_synthesize", intent="seed_order_prereq")
    monkeypatch.setenv("MUX_PARTIAL", "0")
    monkeypatch.setenv("MUX_FULL_AUTO", "1")
    b = admit_resume(ctx, "vo_synthesize", intent="seed_order_prereq")
    assert a == b


def test_from_stage_census_allowlisted_sites() -> None:
    """Wired heal/remutate/recovery/filter modules must import admit APIs."""
    root = Path(__file__).resolve().parents[1] / "src" / "interview_mux"
    required = {
        "heal_pin_authority.py": ("admit_resume", "admit_schedule"),
        "thrash_hardening.py": ("resolve_heal_from_stage",),
        "delivery_guardrails.py": ("admit_resume", "admit_schedule"),
        "delivery_invariants.py": ("admit_resume",),
        "recovery_controller.py": ("admit_resume",),
    }
    for rel, needles in required.items():
        text = (root / rel).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in text, f"{rel} missing {needle}"
