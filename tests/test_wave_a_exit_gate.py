"""Wave A exit-gate smoke: Lock helpers exist and import cleanly."""

from __future__ import annotations


def test_incompleteness_resume_stage_importable():
    from interview_mux.stage_completion import incompleteness_resume_stage

    assert callable(incompleteness_resume_stage)


def test_maybe_auto_unstick_once_importable():
    from interview_mux.delivery_unstick import maybe_auto_unstick_once

    assert callable(maybe_auto_unstick_once)


def test_fail_closed_on_stub_importable():
    from interview_mux.musicgen_runner import fail_closed_on_stub

    assert callable(fail_closed_on_stub)
    # Default product path is fail-closed (omit, not stub ship).
    assert isinstance(fail_closed_on_stub(), bool)
