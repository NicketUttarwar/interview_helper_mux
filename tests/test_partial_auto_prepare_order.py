"""Partial-auto reaches G0 without running audio_preclean first."""

from __future__ import annotations

from interview_mux.automation_run import PARTIAL_AUTO_PREPARE_UNTIL_G0


def test_partial_auto_prepare_until_g0_excludes_preclean() -> None:
    assert "audio_preclean" not in PARTIAL_AUTO_PREPARE_UNTIL_G0
    assert PARTIAL_AUTO_PREPARE_UNTIL_G0 == (
        "ingest",
        "transcribe",
        "transcript_review_build",
    )
