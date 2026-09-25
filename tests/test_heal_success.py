"""Heal Clinic heal_validate_stage_fail B+ — Heal Success Constitution.

MUX_FORENSICS=0 matrix for finalize_heal_success / flush gates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.heal_success import (
    RECOVER_PLAYBOOK_ALLOW,
    SAME_STAGE_RETRY_ALLOW,
    SOFT_PRE_FLUSH_ALLOW,
    finalize_heal_success,
    heal_fail_predicate_clear,
    may_mark_after_flush,
    may_soft_pre_flush_pass,
)
from interview_mux.stage_completion import heal_or_raise
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "heal_success_b_plus")


def test_exception_tables() -> None:
    assert "generate_sdp_theme_wavs" in RECOVER_PLAYBOOK_ALLOW
    assert "vo_audibility_drift" in SAME_STAGE_RETRY_ALLOW
    assert SOFT_PRE_FLUSH_ALLOW == frozenset()


def test_v1_unlisted_playbook_refused(ctx) -> None:
    out = finalize_heal_success(
        ctx,
        failed_stage="mix",
        resume_stage="mmaudio_sfx",
        playbook_id="not_a_real_playbook_zz",
        artifacts=["sound_design/assets/x.wav"],
    )
    assert out.ok is False
    assert out.recovered is False
    assert "playbook_not_allowlisted" in out.reason


def test_v1_sdp_missing_artifacts_predicate_false(ctx) -> None:
    assert (
        heal_fail_predicate_clear(
            ctx,
            "sdp_theme_wavs_missing",
            artifacts=["missing:theme_underscore"],
        )
        is False
    )


def test_v2_pending_artifacts_not_clear(ctx) -> None:
    assert (
        heal_fail_predicate_clear(
            ctx, "pending_write_barrier", artifacts=["pending:edl"]
        )
        is False
    )


def test_v3_retry_acceptance_refuses_mark(ctx) -> None:
    ok, reason = may_mark_after_flush(
        ctx, "edl", resilience_action="retry", acceptance_ok=False
    )
    assert ok is False
    assert "retry" in reason


def test_v4_soft_pre_flush_default_refused() -> None:
    assert may_soft_pre_flush_pass("edl", soft_reason="empty") is False


def test_finalize_resume_producer_when_predicate_clear(ctx) -> None:
    out = finalize_heal_success(
        ctx,
        failed_stage="mix",
        resume_stage="mmaudio_sfx",
        playbook_id="ensure_mmaudio_qa",
        error_class="mmaudio_qa_missing",
        artifacts=["sound_design/mmaudio_qa.json"],
    )
    assert out.ok is True
    assert out.recovered is True
    assert out.resume_stage


def test_v10_heal_or_raise_hollow_raises(ctx) -> None:
    mark_done_raw(ctx, "master_finalize")
    with pytest.raises(RuntimeError):
        heal_or_raise(ctx, "master_finalize")


def test_v8_partial_full_auto_parity(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    kwargs = dict(
        failed_stage="mix",
        resume_stage="mmaudio_sfx",
        playbook_id="ensure_mmaudio_qa",
        artifacts=["sound_design/mmaudio_qa.json"],
    )
    monkeypatch.setenv("MUX_PARTIAL", "1")
    a = finalize_heal_success(ctx, **kwargs)
    monkeypatch.setenv("MUX_PARTIAL", "0")
    monkeypatch.setenv("MUX_FULL_AUTO", "1")
    b = finalize_heal_success(ctx, **kwargs)
    assert a.ok == b.ok
    assert a.recovered == b.recovered


def test_census_and_caller_wiring() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src" / "interview_mux"
    assert "finalize_heal_success" in (src / "recovery_controller.py").read_text(
        encoding="utf-8"
    )
    assert "may_mark_after_flush" in (src / "write_staging.py").read_text(
        encoding="utf-8"
    )
    assert "may_soft_pre_flush_pass" in (src / "stage_resilience.py").read_text(
        encoding="utf-8"
    )
    assert "admit_resume" in (src / "pipeline.py").read_text(encoding="utf-8")
    xv = (src / "artifact_cross_validate.py").read_text(encoding="utf-8")
    assert "V11" in xv or "soft cross-validate" in xv.lower()
