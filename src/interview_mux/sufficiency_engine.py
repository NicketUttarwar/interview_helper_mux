"""Semantic sufficiency evaluation — meaningful data, not just schema presence."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from interview_mux.config import merged_config
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.stage_contract import SufficiencyRule, evaluate_when, load_contract

_GENERIC_THEMES = frozenset(
    {"leadership", "innovation", "success", "journey", "passion", "vision", "impact"}
)


class BlockingTier(str, Enum):
    PROGRESSION = "progression"
    SPEND = "spend"
    ADVISORY = "advisory"
    INVESTIGATION = "investigation"


@dataclass
class SufficiencyFinding:
    path: str
    rule: str
    blocking_tier: BlockingTier
    message: str
    remediation: str = "micro_gap_fill"
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.blocking_tier in (BlockingTier.PROGRESSION, BlockingTier.SPEND)


def sufficiency_enabled(cfg: dict[str, Any] | None = None) -> bool:
    analysis = (cfg or merged_config()).get("analysis") or {}
    raw = analysis.get("sufficiency") or {}
    return bool(raw.get("enabled", True))


def _tier_from_str(label: str) -> BlockingTier:
    try:
        return BlockingTier(label)
    except ValueError:
        return BlockingTier.PROGRESSION


def _non_empty_str(val: Any, min_length: int = 1) -> bool:
    return isinstance(val, str) and len(val.strip()) >= min_length


def _get_path_value(artifact: dict[str, Any], path: str) -> Any:
    if path.endswith("[]"):
        return artifact.get(path[:-2])
    if "[]" in path:
        base, rest = path.split("[].", 1)
        rows = artifact.get(base)
        if not isinstance(rows, list):
            return None
        return [(r.get(rest) if isinstance(r, dict) else None) for r in rows]
    return artifact.get(path)


def _claim_has_evidence(claim: dict[str, Any]) -> bool:
    if claim.get("approx_time_range"):
        return True
    for key in ("segment_ids", "evidence_segment_ids"):
        ids = claim.get(key)
        if isinstance(ids, list) and ids:
            return True
    return False


def _default_rules_for_stage(stage_key: str) -> list[SufficiencyRule]:
    """Built-in rules when contract YAML has no sufficiency block."""
    rules: list[SufficiencyRule] = []
    if stage_key in ("content_context", "content_brief_reanchor"):
        rules.extend(
            [
                SufficiencyRule(path="thesis", rule="non_empty_string", min_length=8),
                SufficiencyRule(path="topics", rule="min_rows", min_count=1),
            ]
        )
    if stage_key == "speaker_roles":
        rules.append(SufficiencyRule(path="speakers", rule="min_rows", min_count=1))
    if stage_key == "boundary_detection":
        rules.append(SufficiencyRule(path="boundaries", rule="min_rows", min_count=1))
    if stage_key == "segment_classification":
        rules.append(SufficiencyRule(path="segments", rule="min_rows", min_count=1))
    return rules


def evaluate_rule(
    rule: SufficiencyRule,
    artifact: dict[str, Any],
    ctx: Any,
    *,
    stage_key: str,
) -> SufficiencyFinding | None:
    if not evaluate_when(rule.when, ctx):
        return None
    tier = _tier_from_str(rule.blocking)
    min_len = int(rule.min_length or 1)
    min_count = int(rule.min_count or 1)

    if rule.rule == "present":
        val = _get_path_value(artifact, rule.path)
        if val is None:
            return SufficiencyFinding(rule.path, rule.rule, tier, f"{rule.path} missing", rule.remediation)

    elif rule.rule == "non_empty_string":
        val = _get_path_value(artifact, rule.path)
        if not _non_empty_str(val, min_len):
            return SufficiencyFinding(
                rule.path,
                rule.rule,
                tier,
                f"{rule.path} empty or shorter than {min_len}",
                rule.remediation,
                {"length": len(str(val or "").strip()), "min_length": min_len},
            )

    elif rule.rule == "min_rows":
        val = _get_path_value(artifact, rule.path.rstrip("[]"))
        if not isinstance(val, list) or len(val) < min_count:
            return SufficiencyFinding(
                rule.path,
                rule.rule,
                tier,
                f"{rule.path} needs at least {min_count} rows",
                rule.remediation,
                {"count": len(val) if isinstance(val, list) else 0},
            )

    elif rule.rule == "row_field_non_empty":
        base = rule.path.split("[].")[0]
        field_name = rule.path.split("[].", 1)[-1]
        rows = artifact.get(base) or []
        if isinstance(rows, list):
            for i, row in enumerate(rows):
                if isinstance(row, dict) and not _non_empty_str(row.get(field_name), min_len):
                    return SufficiencyFinding(
                        f"{base}[{i}].{field_name}",
                        rule.rule,
                        tier,
                        f"{base}[{i}].{field_name} empty",
                        rule.remediation,
                    )

    elif rule.rule == "evidence_anchor":
        rows = artifact.get("key_claims") or []
        if isinstance(rows, list):
            for i, row in enumerate(rows):
                if isinstance(row, dict) and not _claim_has_evidence(row):
                    return SufficiencyFinding(
                        f"key_claims[{i}]",
                        rule.rule,
                        tier,
                        "key_claim without evidence anchor",
                        rule.remediation,
                    )

    elif rule.rule == "not_generic":
        rows = artifact.get("topics") or []
        if isinstance(rows, list):
            for i, row in enumerate(rows):
                if isinstance(row, dict):
                    name = str(row.get("name") or "").strip().lower()
                    if name in _GENERIC_THEMES:
                        return SufficiencyFinding(
                            f"topics[{i}].name",
                            rule.rule,
                            BlockingTier.ADVISORY,
                            f"generic theme: {name}",
                            rule.remediation,
                        )

    elif rule.rule == "speakers_not_all_unknown":
        speakers = artifact.get("speakers") or []
        if speakers and all(
            isinstance(s, dict) and str(s.get("role", "")).strip().lower() == "unknown"
            for s in speakers
        ):
            return SufficiencyFinding(
                "speakers",
                rule.rule,
                tier,
                "all speakers unknown roles",
                "volley_retry",
            )

    return None


def evaluate(
    stage_key: str,
    artifact: dict[str, Any] | None,
    ctx: Any,
    *,
    contract=None,
) -> list[SufficiencyFinding]:
    if not sufficiency_enabled():
        return []
    if not artifact:
        rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key, "(root)")
        return [
            SufficiencyFinding(
                rel,
                "present",
                BlockingTier.PROGRESSION,
                "artifact missing",
                "full_stage_rerun",
            )
        ]
    c = contract or load_contract(stage_key)
    rules = list(c.sufficiency) if c and c.sufficiency else _default_rules_for_stage(stage_key)
    findings: list[SufficiencyFinding] = []
    for rule in rules:
        finding = evaluate_rule(rule, artifact, ctx, stage_key=stage_key)
        if finding:
            findings.append(finding)
    return findings


def findings_to_gap_paths(findings: list[SufficiencyFinding]) -> list[str]:
    return [f.path for f in findings if f.blocking]


__all__ = [
    "BlockingTier",
    "SufficiencyFinding",
    "evaluate",
    "evaluate_rule",
    "findings_to_gap_paths",
    "sufficiency_enabled",
]
