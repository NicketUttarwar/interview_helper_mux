"""Simulate downstream consumer readiness at producer commit time."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_dependency_graph import downstream_consumers
from interview_mux.config import merged_config
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.stage_contract import load_contract
from interview_mux.sufficiency_engine import BlockingTier, SufficiencyFinding, evaluate


def downstream_probe_enabled(cfg: dict[str, Any] | None = None) -> bool:
    analysis = (cfg or merged_config()).get("analysis") or {}
    raw = analysis.get("downstream_probe") or {}
    return bool(raw.get("enabled", True))


def probe_consumers(
    ctx: Any,
    producer_stage: str,
    artifact: dict[str, Any],
    *,
    staged: bool = False,
) -> list[SufficiencyFinding]:
    if not downstream_probe_enabled():
        return []
    findings: list[SufficiencyFinding] = []
    producer_rel = STAGE_ARTIFACT_DISK_PATHS.get(producer_stage)
    consumers = downstream_consumers(producer_stage, ctx=ctx)
    for consumer in consumers[:12]:
        c_contract = load_contract(consumer)
        if not c_contract:
            continue
        for inp in c_contract.inputs:
            if inp.path != producer_rel:
                continue
            if inp.hard and not ctx.artifact_exists(inp.path):
                findings.append(
                    SufficiencyFinding(
                        inp.path,
                        "consumer_requires",
                        BlockingTier.PROGRESSION,
                        f"consumer {consumer} requires {inp.path}",
                        "micro_gap_fill",
                    )
                )
        cons_artifact = artifact if producer_rel else None
        if cons_artifact:
            for f in evaluate(consumer, cons_artifact, ctx):
                if f.blocking and f.path in str(producer_rel):
                    findings.append(f)
    return findings


def simulate_consumer_preflight(consumer_stage: str, ctx: Any) -> list[str]:
    from interview_mux.llm_preflight import run_preflight

    try:
        return list(run_preflight(consumer_stage, ctx) or [])
    except Exception as exc:
        return [str(exc)]


__all__ = ["downstream_probe_enabled", "probe_consumers", "simulate_consumer_preflight"]
