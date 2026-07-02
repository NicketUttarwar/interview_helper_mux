"""Decision tree for permissive LLM field normalization — action + downstream path."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from interview_mux.field_necessity_registry import FieldAction, classify_field_path
from interview_mux.null_field_policy import null_policy_cfg


class DownstreamAction(str, Enum):
    """Automated recovery step after a normalization decision."""

    OMIT_AND_ACKNOWLEDGE = "omit_and_acknowledge"
    FABRICATE_BENIGN = "fabricate_benign"
    VOLLEY_RETRY = "volley_retry"
    MICRO_GAP_FILL = "micro_gap_fill"
    FULL_STAGE_RERUN = "full_stage_rerun"
    OPERATOR_GATE = "operator_gate"


@dataclass(frozen=True)
class NormalizationDecision:
    action: FieldAction
    downstream: DownstreamAction
    reason: str
    permissive: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "downstream": self.downstream.value,
            "reason": self.reason,
            "permissive": self.permissive,
        }


def _permissive_enabled(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("permissive_mode", True))


def _auto_fabricate_unknown(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("auto_fabricate_unknown_optional", True))


def resolve_normalization_decision(
    stage_key: str | None,
    path: str,
    *,
    prefer_omit: bool = True,
    error_kind: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> NormalizationDecision:
    """
    Map a field path (null or schema error) to an action and automated downstream step.

    Decision tree (permissive default):
    1. Commentary / nullable → OMIT + acknowledge
    2. Fabricatable / unknown optional → FABRICATE benign default
    3. Critical or never-fabricate evidentiary → BLOCK → volley_retry or micro_gap_fill
       (operator_gate only when hard_stop_on_critical_null and retries exhausted — caller)
    """
    policy = cfg or null_policy_cfg()
    permissive = _permissive_enabled(policy)
    action = classify_field_path(stage_key, path, prefer_omit=prefer_omit, permissive=permissive)

    if action == FieldAction.OMIT:
        return NormalizationDecision(
            action=FieldAction.OMIT,
            downstream=DownstreamAction.OMIT_AND_ACKNOWLEDGE,
            reason="nullable or commentary field — strip and record acknowledgment",
            permissive=True,
        )

    if action == FieldAction.FABRICATE:
        return NormalizationDecision(
            action=FieldAction.FABRICATE,
            downstream=DownstreamAction.FABRICATE_BENIGN,
            reason="low-risk optional field — apply benign automated default",
            permissive=True,
        )

    # BLOCK — evidentiary / critical
    if error_kind == "critical_null" or (error_kind == "null" and _is_critical_path(stage_key, path)):
        downstream = DownstreamAction.MICRO_GAP_FILL
        reason = "critical field null — targeted gap-fill before operator"
    elif error_kind == "schema":
        downstream = DownstreamAction.VOLLEY_RETRY
        reason = "schema mismatch on evidentiary field — volley retry with feedback"
    else:
        downstream = DownstreamAction.VOLLEY_RETRY
        reason = "evidentiary field needs model correction — volley retry"

    if permissive and _auto_fabricate_unknown(policy) and not _is_evidentiary_path(path):
        return NormalizationDecision(
            action=FieldAction.FABRICATE,
            downstream=DownstreamAction.FABRICATE_BENIGN,
            reason="permissive downgrade: non-evidentiary path auto-fabricated",
            permissive=True,
        )

    return NormalizationDecision(
        action=FieldAction.BLOCK,
        downstream=downstream,
        reason=reason,
        permissive=False,
    )


def summarize_decisions(decisions: list[NormalizationDecision]) -> dict[str, Any]:
    """Aggregate decision counts for _meta.normalization_summary."""
    counts: dict[str, int] = {}
    downstreams: dict[str, int] = {}
    for d in decisions:
        counts[d.action.value] = counts.get(d.action.value, 0) + 1
        downstreams[d.downstream.value] = downstreams.get(d.downstream.value, 0) + 1
    return {
        "action_counts": counts,
        "downstream_counts": downstreams,
        "permissive_applied": any(d.permissive for d in decisions),
    }


def _is_critical_path(stage_key: str | None, path: str) -> bool:
    from interview_mux.field_necessity_registry import _is_critical  # noqa: PLC0415

    sk = stage_key or ""
    return _is_critical(sk, path)


def _is_evidentiary_path(path: str) -> bool:
    from interview_mux.field_necessity_registry import _is_never_fabricate  # noqa: PLC0415

    return _is_never_fabricate(path)
