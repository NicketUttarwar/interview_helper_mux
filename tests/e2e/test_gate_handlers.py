"""Tests for E2E gate handler helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from e2e_runner.gate_handlers import build_execute_body, resolve_blocking
from e2e_runner.stall_detector import StallDetector
from e2e_runner.wav_stub import minimal_wav_bytes


def test_build_execute_body_from_hint():
    body = build_execute_body({"mode": "flow1", "from_stage": "topic_coverage_audit"})
    assert body == {"mode": "flow1", "from_stage": "topic_coverage_audit"}


def test_minimal_wav_is_valid_riff():
    data = minimal_wav_bytes()
    assert data[:4] == b"RIFF"
    assert b"WAVE" in data


def test_resolve_blocking_transcript_review():
    api = MagicMock()
    run = {
        "stages": [{"id": "transcript_review", "status": "action_required"}],
        "journey": {"preclean_checkpoints": [], "milestones": {}},
        "log_tail": [],
    }
    actions = resolve_blocking(api, "exec_001", run)
    api.complete_transcript_review.assert_called_once()
    assert "transcript_review_complete" in actions


def test_dismiss_all_unacknowledged_preclean_checkpoints():
    api = MagicMock()
    run = {
        "meta": {"audio_preclean": {"offered_at": ["before_ingest"]}},
        "journey": {
            "preclean_checkpoints": [
                "before_ingest",
                "after_g0",
                "before_sfx_spend",
                "before_flow_mix",
                "before_master_export",
            ],
            "recommended_preclean": "before_flow_mix",
            "milestones": {},
        },
        "stages": [],
        "log_tail": [],
    }
    actions = resolve_blocking(api, "exec_001", run)
    dismissed = {a.split(":", 1)[1] for a in actions if a.startswith("preclean_dismiss:")}
    assert "before_ingest" not in dismissed
    assert dismissed == {
        "after_g0",
        "before_sfx_spend",
        "before_flow_mix",
        "before_master_export",
    }


def test_stall_detector_resets_on_fingerprint_change():
    det = StallDetector(gate_timeout_s=1.0, idle_timeout_s=1.0)
    det.observe(("a", "prepare", "x", "idle", ""), job_running=False)
    det.observe(("a", "understand", "x", "idle", ""), job_running=False)
    stuck, _ = det.is_stuck(job_running=False)
    assert not stuck
