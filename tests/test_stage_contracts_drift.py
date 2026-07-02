from __future__ import annotations

from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS, STAGE_ARTIFACT_SCHEMAS
from interview_mux.stage_contract import all_contract_stage_ids, load_contract


def test_all_llm_stages_have_contracts():
    missing = [s for s in STAGE_ARTIFACT_SCHEMAS if s not in all_contract_stage_ids()]
    assert not missing, f"missing contracts: {missing}"


def test_llm_contracts_have_outputs_and_sufficiency():
    for sid in STAGE_ARTIFACT_SCHEMAS:
        c = load_contract(sid)
        assert c is not None, sid
        if sid in STAGE_ARTIFACT_DISK_PATHS:
            assert c.outputs, sid
        assert c.sufficiency, sid


def test_key_stages_have_enriched_sufficiency():
    for sid in ("speaker_roles", "content_context", "boundary_detection"):
        c = load_contract(sid)
        assert c and len(c.sufficiency) >= 1
