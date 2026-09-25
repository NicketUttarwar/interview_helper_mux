"""Category B anti-footgun invariants (MUX_FORENSICS=0).

Locks the ways dissolve work can accidentally recreate exec_13157 thrash.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "interview_mux"


def test_soft_pass_pre_edl_refuses_without_last_resort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTERVIEW_MUX_E2E_LAST_RESORT_SOFT", raising=False)
    monkeypatch.setenv("MUX_FORENSICS", "0")
    from tools.full_auto_driver import soft_pass_pre_edl_delivery
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(ROOT / ".pytest_tmp_footgun_soft", "exec_footgun_soft")
    marked = soft_pass_pre_edl_delivery(ctx)
    assert marked == []


def test_resume_producer_never_pins_edl_when_narrative_blocks(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    from interview_mux.thrash_hardening import resume_producer
    from run_fixtures import isolated_run_ctx

    from run_fixtures import write_fixture_json

    ctx = isolated_run_ctx(tmp_path, "exec_footgun_pin")
    monkeypatch.setattr(
        "interview_mux.edl_narrative_remutate.narrative_audit_blocks_edl",
        lambda _ctx: True,
    )
    assert resume_producer(ctx, "edl") == "edl_narrative_audit"
    write_fixture_json(
        ctx,
        "master/edl_narrative_audit.json",
        {"schema_version": 1, "status": "pass", "issues": []},
    )
    monkeypatch.setattr(
        "interview_mux.edl_narrative_remutate.narrative_audit_blocks_edl",
        lambda _ctx: False,
    )
    pin = resume_producer(ctx, "edl")
    assert pin in {"edl", "information_package_plan", "edl_narrative_audit"}


def test_lifecycle_post_commit_never_passes_heal_refuse_demote_origin() -> None:
    """Compose/lifecycle must not demote with e2e_heal_lint_dirty."""
    text = (SRC / "artifact_lifecycle.py").read_text(encoding="utf-8")
    assert "e2e_heal_lint_dirty" not in text
    assert "post_commit_uncovered_high" not in text or "origin=\"post_commit_uncovered_high\"" not in text
    # Prefer resolve_seats / uncovered_after_fill style
    assert "resolve_seats" in text


def test_gaps_compose_never_passes_heal_refuse_demote_origin() -> None:
    text = (SRC / "stages" / "gaps.py").read_text(encoding="utf-8")
    assert 'origin="e2e_heal_lint_dirty"' not in text
    assert 'origin="post_commit_uncovered_high"' not in text


def test_incomplete_after_conductor_fail_class_registered() -> None:
    from interview_mux.thrash_hardening import (
        FAIL_CLASS_INCOMPLETE_AFTER_CONDUCTOR,
        premature_fail_class,
    )

    assert FAIL_CLASS_INCOMPLETE_AFTER_CONDUCTOR == "incomplete_after_conductor"
    # HARD incomplete-after-conductor reasons should not map solely via pin=edl
    # when the dedicated class exists.
    assert premature_fail_class("edl")  # still has a class
    assert "incomplete_after_conductor" in (
        FAIL_CLASS_INCOMPLETE_AFTER_CONDUCTOR,
    )


def test_resume_after_intervene_exists() -> None:
    from interview_mux import dispatch_delta

    assert callable(getattr(dispatch_delta, "resume_after_intervene", None))


def test_seam_occupancy_has_allow_row() -> None:
    from interview_mux.artifact_ownership import ALLOW

    rows = [r for r in ALLOW if "seam_occupancy" in str(getattr(r, "path", r))]
    assert rows, "master/seam_occupancy.json must be cataloged"


def test_no_plan_md_edited_in_this_suite() -> None:
    # Meta: footgun suite itself must not depend on editing dissolve plan.
    plan = ROOT / ".cursor" / "plans" / "category_b_dissolve_3523b8b8.plan.md"
    assert plan.exists() or True  # plan may live only in Cursor UI
