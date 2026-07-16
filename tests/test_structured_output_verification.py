from __future__ import annotations

import json
from pathlib import Path

from interview_mux.llm_response_verify import verify_llm_response
from interview_mux.local_structured_output import resolve_lx_interaction
from interview_mux.openai_structured_output import min_example_for_arbiter

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "local_llm"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_verify_arbiter_accepts_valid_verdict():
    payload = min_example_for_arbiter()
    result = verify_llm_response("OM-02", payload)
    assert result.ok
    assert result.schema_name == "arbiter_verdict"


def test_verify_arbiter_accepts_null_investigation_fields():
    payload = {
        "verdict": "accept",
        "confidence": 0.85,
        "gaps": [],
        "shard_plan": [],
        "suggested_investigation": {
            "kind": None,
            "question": None,
            "blocking": None,
        },
        "reasoning_summary": "Speaker roles evidenced.",
    }
    result = verify_llm_response("OM-02", payload)
    assert result.ok


def test_verify_local_framer_accepts_valid():
    parsed = {
        "escalate": True,
        "confidence": 0.8,
        "reason": "P0 stage",
        "volley_turns": [{"role": "assistant", "content": "summary"}],
    }
    result = verify_llm_response("LX-01", parsed)
    assert result.ok
    assert result.schema_name == "local_framer"


def test_resolve_lx_interaction_maps_caps_to_schemas():
    assert resolve_lx_interaction("LX-01") == "local_framer"
    assert resolve_lx_interaction("LX-01a") == "local_framer"
    assert resolve_lx_interaction("LX-02") == "itr_clarification"
    assert resolve_lx_interaction("LX-02a") == "itr_clarification"
    assert resolve_lx_interaction("LX-03") == "local_digest_compress"
    assert resolve_lx_interaction("LX-04") == "local_escalate_advisory"
    assert resolve_lx_interaction("LX-05") == "local_shard_prep"
    assert (
        resolve_lx_interaction(
            "LX-04",
            task_kind="local_escalate_advisory",
            stage_key="content_context",
        )
        == "local_escalate_advisory"
    )


def test_verify_lx03_digest_compress_accepts_fixture():
    parsed = _load_fixture("compressor_ok.json")
    result = verify_llm_response(
        "LX-03",
        parsed,
        stage_key="content_context",
        task_kind="local_digest_compress",
    )
    assert result.ok
    assert result.schema_name == "local_digest_compress"


def test_verify_lx04_escalate_advisory_accepts_fixture():
    parsed = _load_fixture("escalate_advisory_ok.json")
    result = verify_llm_response(
        "LX-04",
        parsed,
        stage_key="content_context",
        task_kind="local_escalate_advisory",
    )
    assert result.ok
    assert result.schema_name == "local_escalate_advisory"


def test_verify_lx05_shard_prep_accepts_fixture():
    parsed = _load_fixture("shard_prep_ok.json")
    result = verify_llm_response(
        "LX-05",
        parsed,
        stage_key="content_context",
        task_kind="local_shard_prep",
    )
    assert result.ok
    assert result.schema_name == "local_shard_prep"


def test_verify_lx04_payload_rejected_as_framer():
    """Guard: advisory JSON must not pass when mis-routed to LX-01 framer schema."""
    parsed = _load_fixture("escalate_advisory_ok.json")
    result = verify_llm_response("LX-01", parsed)
    assert not result.ok
    assert any("escalate" in e or "volley_turns" in e for e in result.errors)


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
