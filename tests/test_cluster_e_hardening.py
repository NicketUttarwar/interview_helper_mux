"""Wave 2 Cluster E — pack denylist, primary IDs, feel max-2, soft vs waivers, seed pin.

Catalog: SYN-PACK-01, PSM-LLM-NO-PRIMARY, SYN-RETRY-01, CFG-01, H010-DISPATCH-01.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from interview_mux.homunculus.registry import ToolSpec
from interview_mux.junction_snip_qa import critical_residuals_may_soften
from interview_mux.llm_interaction_registry import (
    NON_LLM_SCHEMA_STAGES,
    STAGE_PRIMARY_IDS,
    llm_bound_schema_stages,
)
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS
from interview_mux.run_context import RunContext
from interview_mux.volley_packet_lint import lint_llm_user_payload, strip_forbidden_metadata
from run_fixtures import mark_done_raw


def _ctx_010() -> RunContext:
    ctx = RunContext(create=True)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "pipeline_mode": "full_auto"},
    )
    return ctx


def test_e01_llm_conductor_view_strips_denylist_keys() -> None:
    """SYN-PACK-01: LLM conductor messages never contain forbidden stamp keys."""
    from interview_mux.homunculus.packer import pack_conductor_context, pack_conductor_context_views

    ctx = _ctx_010()
    mark_done_raw(ctx, "source_topology_build")
    ctx.write_json(
        "understanding/source_topology.json",
        {"speakers": [{"speaker_id": "spk_1", "role": "interviewee"}]},
    )
    views = pack_conductor_context_views(ctx)
    host = views["host_prereq_view"]
    llm = views["llm_conductor_view"]
    host_rows = host["delivery_analysis_prereqs"]
    assert any("stage_done" in row for row in host_rows)
    assert any("artifact_exists" in row for row in host_rows)

    blob = pack_conductor_context(ctx)
    payload = json.loads(blob)
    cleaned = lint_llm_user_payload(payload, require_tape=False)
    assert cleaned == strip_forbidden_metadata(payload)

    def _walk_keys(obj: Any, found: set[str]) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                found.add(str(k))
                _walk_keys(v, found)
        elif isinstance(obj, list):
            for x in obj:
                _walk_keys(x, found)

    keys: set[str] = set()
    _walk_keys(llm, keys)
    forbidden = {"stage_done", "artifact_exists", "exists", "run_meta"}
    assert not (keys & forbidden), f"LLM view leaked {keys & forbidden}"
    assert "stage_done" not in blob
    assert "artifact_exists" not in blob


def test_e01_artifact_exists_on_denylist() -> None:
    cleaned = strip_forbidden_metadata(
        {"artifact_exists": True, "ready_bool": True, "segments": ["hi"]}
    )
    assert "artifact_exists" not in cleaned
    assert cleaned.get("ready_bool") is True


def test_e02_llm_bound_schemas_subset_of_primary_ids() -> None:
    """PSM-LLM-NO-PRIMARY: every LLM-bound schema stage has a STAGE_PRIMARY_IDS entry."""
    bound = llm_bound_schema_stages()
    missing = sorted(bound - set(STAGE_PRIMARY_IDS))
    assert not missing, f"missing STAGE_PRIMARY_IDS for {missing}"
    assert "mmaudio_sfx" in NON_LLM_SCHEMA_STAGES
    assert "mmaudio_sfx" in STAGE_ARTIFACT_SCHEMAS
    assert "mmaudio_sfx" not in STAGE_PRIMARY_IDS
    for sk in (
        "air_script_compose",
        "air_script_seams",
        "master_transcript_build",
        "synthetic_framing_plan",
    ):
        assert sk in STAGE_PRIMARY_IDS


def test_e03_feel_ladder_respects_llm_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SYN-RETRY-01: feel ladder ≤ v2.llm_max_attempts (2)."""
    from interview_mux.homunculus.budget import LimitExhausted
    from interview_mux.junction_snip_qa import run_junction_feel_audit

    ctx = _ctx_010()
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.build_feel_audit_context",
        lambda *_a, **_k: {"junctions": []},
    )
    monkeypatch.setattr(
        "interview_mux.v2.config.v2_cfg",
        lambda: {"llm_max_attempts": 2},
    )
    calls: list[str] = []

    def _env(*_a: object, **kwargs: object) -> dict:
        calls.append(str(kwargs.get("explicit_tier") or ""))
        return {
            "artifacts": {
                "junction_feel_audit": {
                    "verdict": "unavailable",
                    "findings": [],
                    "directives": [],
                }
            }
        }

    monkeypatch.setattr("interview_mux.stages.llm_runner.run_prompt_envelope", _env)
    audit = run_junction_feel_audit(ctx, {"findings": []})
    assert len(calls) <= 2
    assert calls[-1] == "flagship" or len(calls) == 1
    assert audit["verdict"] == "unavailable"

    # LimitExhausted still stops at first burn (no extra retries).
    calls.clear()

    def _raise(*_a: object, **_k: object) -> dict:
        calls.append("x")
        raise LimitExhausted(
            "junction_feel_audit", "max_invokes_per_identity", {"used": 1, "cap": 1}
        )

    monkeypatch.setattr("interview_mux.stages.llm_runner.run_prompt_envelope", _raise)
    run_junction_feel_audit(ctx, {"findings": []})
    assert len(calls) == 1


def test_e04_soft_vs_quality_waivers_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    """CFG-01: soft on / waivers off → no soften; waivers on → soften allowed."""
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    monkeypatch.delenv("INTERVIEW_MUX_E2E_QUALITY_WAIVERS", raising=False)
    assert critical_residuals_may_soften() is False
    assert critical_residuals_may_soften(meta={"e2e_quality_waivers": False}) is False

    monkeypatch.setenv("INTERVIEW_MUX_E2E_QUALITY_WAIVERS", "1")
    assert critical_residuals_may_soften() is True
    monkeypatch.delenv("INTERVIEW_MUX_E2E_QUALITY_WAIVERS", raising=False)
    assert critical_residuals_may_soften(meta={"e2e_quality_waivers": True}) is True


def test_e05_dispatch_seed_pin_before_stage_burn(monkeypatch: pytest.MonkeyPatch) -> None:
    """H010-DISPATCH-01: illegal seed → {ok:false,pin,reason} before check_dispatch."""
    from interview_mux.homunculus import loop as loop_mod

    ctx = _ctx_010()
    dispatched: list[str] = []
    budget_checks: list[str] = []

    monkeypatch.setattr(
        "interview_mux.homunculus.runtime._seed_prereq_block",
        lambda _ctx, stage: "ingest" if stage == "mix" else None,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.filter_delivery_candidates",
        lambda _ctx, remaining: list(remaining),
    )
    monkeypatch.setattr(
        loop_mod,
        "dispatch_stage",
        lambda *_a, **_k: dispatched.append("burned"),
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.budget.check_dispatch",
        lambda *_a, **_k: budget_checks.append("dispatch"),
    )

    spec = ToolSpec(
        name="run_stage_mix",
        identity="mix",
        kind="stage",
        description="mix",
        parameters={"type": "object", "properties": {}},
    )
    result = loop_mod._dispatch_tool(ctx, spec, {})
    assert result["ok"] is False
    assert result["pin"] == "ingest"
    assert result["reason"] == "seed_prereq"
    assert dispatched == []
    assert budget_checks == []
