from __future__ import annotations

from interview_mux.llm_response_verify import verify_llm_response


def _valid_speaker_roles_envelope() -> dict:
    return {
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


def test_verify_speaker_roles_rejects_missing_speakers():
    payload = _valid_speaker_roles_envelope()
    payload["artifacts"] = {}
    result = verify_llm_response("OA-01", payload, stage_key="speaker_roles", task_kind="primary")
    assert not result.ok
    assert result.errors


def test_verify_content_context_rejects_invalid_jargon_glossary_item():
    payload = {
        "status": "complete",
        "artifacts": {
            "thesis": "A thesis about entrepreneurship.",
            "topics": [{"name": "Topic", "summary": "Summary text."}],
            "jargon_glossary": [{"term": "ESOP"}],
        },
        "memory_updates": {},
        "needs": [],
        "follow_up_investigations": [],
        "confidence": 0.8,
        "reasoning_summary": "ok",
    }
    result = verify_llm_response(
        "OA-01",
        payload,
        stage_key="content_context",
        task_kind="primary",
    )
    assert not result.ok
    assert any("plain_definition" in e.lower() or "jargon" in e.lower() for e in result.errors)


def test_verify_arbiter_rejects_invalid_verdict():
    payload = {
        "verdict": "maybe",
        "confidence": 0.5,
        "gaps": [],
        "shard_plan": [],
        "suggested_investigation": None,
        "reasoning_summary": "",
    }
    result = verify_llm_response("OM-02", payload)
    assert not result.ok
