"""Table-driven playbook registry shape tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.heal_routing import PLAYBOOK_REGISTRY, PlaybookSpec
from interview_mux.publishability_boundary import PublishabilityViolation, violation_playbook
from interview_mux.recovery_controller import CLASSIFIED_PLAYBOOKS, classify_error_class
from interview_mux.listen_delight_remutate import plan_listen_delight_remutate
from run_fixtures import isolated_run_ctx


_PUBLISHABILITY_CLASSES = (
    "never_touch_zeroed_keep",
    "vo_audibility_drift",
    "opening_orientation_inaudible",
    "pending_write_barrier",
    "musicgen_theme_failed",
    "incomplete_cut_unresolved",
    "selection_edl_order_drift",
)


def test_playbook_registry_covers_publishability_classes() -> None:
    for error_class in _PUBLISHABILITY_CLASSES:
        spec = PLAYBOOK_REGISTRY.get(error_class)
        assert spec is not None, error_class
        assert isinstance(spec, PlaybookSpec)
        assert spec.resume_stage
        assert spec.action


def test_violation_playbook_resume_stages() -> None:
    expectations = {
        "never_touch_zeroed_keep": "edl",
        "vo_audibility_drift": "edl",
        "opening_orientation_inaudible": "edl",
        "selection_edl_order_drift": "edl",
        "pending_write_barrier": "junction_snip_qa",
        "incomplete_cut_unresolved": "junction_snip_qa",
        "musicgen_theme_failed": "music_palette_compose",
    }
    for error_class, resume in expectations.items():
        spec = violation_playbook(
            PublishabilityViolation(
                error_class=error_class,
                code="test",
                detail="test",
            )
        )
        assert spec.resume_stage == resume


def test_classified_playbooks_include_publishability_classes() -> None:
    for error_class in _PUBLISHABILITY_CLASSES:
        assert error_class in CLASSIFIED_PLAYBOOKS


def test_publishability_blocked_classifies(tmp_path: Path) -> None:
    from interview_mux.publishability_boundary import PublishabilityBlocked, PublishabilityReport

    report = PublishabilityReport(checkpoint="post_edl", ok=False, violations=[])
    exc = PublishabilityBlocked(report, error_class="vo_audibility_drift")
    assert classify_error_class("edl", exc) == "vo_audibility_drift"


def test_cut_integrity_remutate_resumes_edl_after_assembly(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "heal_cut_integrity_edl")
    (ctx.run_dir / ".stage_done" / "edl").write_text("done\n", encoding="utf-8")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "assembly_preview.wav").write_bytes(b"RIFF")
    plan = plan_listen_delight_remutate(ctx, failed_dimensions=["cut_integrity"])
    assert plan["from_stage"] == "edl"
    assert plan["from_stages"][0] == "edl"
    assert "mix" in plan["from_stages"]
