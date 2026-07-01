from __future__ import annotations

from interview_mux.llm_response_verify import verify_llm_response
from interview_mux.openai_structured_output import min_example_for_arbiter


def test_verify_arbiter_accepts_valid_verdict():
    payload = min_example_for_arbiter()
    result = verify_llm_response("OM-02", payload)
    assert result.ok
    assert result.schema_name == "arbiter_verdict"


def test_verify_local_framer_accepts_valid():
    parsed = {
        "escalate": True,
        "confidence": 0.8,
        "reason": "P0 stage",
        "volley_turns": [{"role": "assistant", "content": "summary"}],
    }
    result = verify_llm_response("LX-01", parsed)
    assert result.ok


def test_verify_speaker_roles_envelope():
    parsed = {
        "status": "complete",
        "artifacts": {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9},
            ],
        },
        "memory_updates": {},
        "needs": [],
        "follow_up_investigations": [],
        "confidence": 0.9,
        "reasoning_summary": "ok",
    }
    result = verify_llm_response("OA-01", parsed, stage_key="speaker_roles", task_kind="primary")
    assert result.ok
