"""Speaker roles flagship promote tests."""

from __future__ import annotations

from unittest.mock import patch

from interview_mux.llm_stage_routing import _try_flagship_uptier_promote
from run_fixtures import isolated_run_ctx


def test_flagship_promote_accepts_clean_speaker_roles(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "flagship_promote")
    envelope = {
        "status": "blocked",
        "confidence": 0.7,
        "artifacts": {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.85},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ]
        },
        "_llm_meta": {"model_tier": "flagship"},
    }
    arbiter = {"verdict": "retry_uptier", "confidence": 0.7}
    with patch("interview_mux.llm_stage_routing.deterministic_lint", return_value=[]):
        ok = _try_flagship_uptier_promote(ctx, "speaker_roles", envelope, arbiter, [])
    assert ok is True
    assert arbiter["verdict"] == "accept"
    assert envelope["status"] == "complete"
