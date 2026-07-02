from __future__ import annotations

from interview_mux.remediation_orchestrator import RemediationTrigger, remediate
from interview_mux.sufficiency_engine import BlockingTier, SufficiencyFinding


class _GuardCtx:
    def artifact_exists(self, rel: str) -> bool:
        return False

    def write_json(self, rel: str, data, **kwargs):
        return None


def test_request_schema_recompose():
    res = remediate(_GuardCtx(), "content_context", RemediationTrigger.REQUEST_SCHEMA, [])
    assert res.ok and res.strategy == "recompose_schema"


def test_sufficiency_triggers_micro_gap_plan():
    finding = SufficiencyFinding("thesis", "non_empty_string", BlockingTier.PROGRESSION, "thesis empty")
    res = remediate(
        _GuardCtx(),
        "content_context",
        RemediationTrigger.ACCEPTANCE_FAIL,
        [finding],
        existing={"thesis": ""},
    )
    assert res.strategy in ("micro_gap_fill", "volley_retry")


def test_downstream_probe_propagation():
    res = remediate(_GuardCtx(), "boundary_detection", RemediationTrigger.DOWNSTREAM_PROBE_FAIL, ["blocked"])
    assert res.strategy == "propagation"
