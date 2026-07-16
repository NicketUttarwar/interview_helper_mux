"""Severity classification for artifact issue triage."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from interview_mux.model_registry import stage_severity
from interview_mux.null_field_policy import (
    critical_fields_for_stage,
    nullable_fields_for_stage,
)

Severity = Literal["critical", "important", "minor", "noise"]
IssueKind = Literal[
    "overlap",
    "schema",
    "lint",
    "cross_validate",
    "null",
    "enum",
    "coverage",
    "field_parity",
    "request_schema",
    "sufficiency",
    "downstream_blocked",
    "stale_artifact",
    "reuse_invalid",
    "other",
]


@dataclass
class ClassifiedIssue:
    message: str
    kind: IssueKind = "other"
    severity: Severity = "important"
    blocking: bool = True
    repair_strategy: str | None = None
    artifact_path: str | None = None
    json_path: str | None = None
    segment_id: str | None = None
    source: str = "unknown"
    evidence: dict[str, Any] = field(default_factory=dict)
    upstream_stage: str | None = None

    def to_dict(self, *, stage_key: str, issue_id: str) -> dict[str, Any]:
        return {
            "id": issue_id,
            "stage_key": stage_key,
            "artifact_path": self.artifact_path,
            "json_path": self.json_path,
            "segment_id": self.segment_id,
            "kind": self.kind,
            "severity": self.severity,
            "blocking": self.blocking,
            "message": self.message,
            "status": "open",
            "repair_strategy": self.repair_strategy,
            "options": [],
            "chosen": None,
            "auto_applied": None,
            "created_at": None,
            "resolved_at": None,
            "source": self.source,
            "evidence": self.evidence,
            "suggested_upstream_stage": self.upstream_stage,
            "recovery_actions": [],
        }


_SEGMENT_ID_RE = re.compile(r"\b(seg_\d+)\b", re.I)


def _extract_segment_id(message: str) -> str | None:
    m = _SEGMENT_ID_RE.search(message)
    return m.group(1) if m else None


def _editorial_tier(stage_key: str) -> str:
    return stage_severity(stage_key)


def classify_lint_message(stage_key: str, message: str, *, artifact_path: str | None = None) -> ClassifiedIssue:
    low = message.lower()
    seg_id = _extract_segment_id(message)
    issue = ClassifiedIssue(
        message=message,
        kind="lint",
        artifact_path=artifact_path,
        segment_id=seg_id,
        source="lint",
    )

    if "duplicate segment_id" in low:
        issue.kind = "overlap"
        issue.severity = "critical"
        issue.repair_strategy = "merge_overlap"
        return issue

    if "manifest times not monotonic" in low or "zero-length segment" in low or "zero-length boundary" in low:
        issue.kind = "overlap"
        issue.severity = "critical"
        issue.repair_strategy = "merge_overlap"
        return issue

    if "segment_coverage_ratio" in low:
        issue.kind = "coverage"
        issue.severity = "important"
        issue.repair_strategy = "fabricate_missing_segments"
        return issue

    if "all segments typed interviewee_answer" in low:
        issue.kind = "enum"
        issue.severity = "important"
        issue.repair_strategy = "infer_segment_types"
        return issue

    if "all speakers unknown" in low:
        issue.kind = "enum"
        issue.severity = "important"
        issue.repair_strategy = "infer_enum"
        issue.upstream_stage = "speaker_roles"
        return issue

    if "generic theme" in low or "topic without evidence" in low:
        issue.severity = "minor"
        issue.repair_strategy = "drop_row"
        return issue

    if "confidence_gte_min" in low:
        issue.severity = "minor"
        issue.blocking = False
        issue.repair_strategy = "accept_auto_repair"
        return issue

    if "envelope_status_complete" in low:
        issue.severity = "noise"
        issue.blocking = False
        issue.repair_strategy = None
        return issue

    if "topic_tags" in low and "null" in low:
        issue.kind = "null"
        issue.severity = "minor"
        issue.repair_strategy = "default_value"
        return issue

    if "schema" in low or "not of type" in low:
        issue.kind = "schema"
        issue.severity = "minor"
        issue.repair_strategy = "default_value"
        return issue

    if "key_claim without evidence" in low:
        issue.severity = "minor"
        issue.repair_strategy = "drop_row"
        return issue

    if "thesis empty" in low:
        issue.severity = "important"
        issue.repair_strategy = "llm_pick"
        return issue

    tier = _editorial_tier(stage_key)
    issue.severity = "critical" if tier == "high" else "important"
    return issue


def classify_cross_validate_message(
    stage_key: str,
    message: str,
    *,
    artifact_path: str | None = None,
) -> ClassifiedIssue:
    low = message.lower()
    seg_id = _extract_segment_id(message)
    issue = ClassifiedIssue(
        message=message,
        kind="cross_validate",
        severity="critical",
        blocking=True,
        artifact_path=artifact_path,
        segment_id=seg_id,
        source="cross_validate",
    )

    if "duplicate segment_id" in low:
        issue.kind = "overlap"
        issue.repair_strategy = "merge_overlap"
    elif "not monotonic" in low or "overlap" in low:
        issue.kind = "overlap"
        issue.repair_strategy = "merge_overlap"
        if stage_key == "segment_classification":
            issue.upstream_stage = "boundary_detection"
    elif "not in manifest" in low:
        issue.repair_strategy = "drop_orphan_ref"
        if "boundary" in low:
            issue.upstream_stage = "boundary_detection"
        elif stage_key != "segment_classification":
            issue.upstream_stage = "segment_classification"
    else:
        issue.repair_strategy = "llm_pick"
    return issue


def classify_field_parity_message(
    stage_key: str,
    message: str,
    *,
    artifact_path: str | None = None,
) -> ClassifiedIssue:
    seg_id = _extract_segment_id(message)
    low = message.lower()
    repair = "hydrate_from_boundaries"
    if "speaker" in low:
        repair = "repair_speaker_role"
    elif "missing manifest" in low or "missing segment_id" in low:
        repair = "fabricate_missing_segment"
    return ClassifiedIssue(
        message=message,
        kind="field_parity",
        severity="critical",
        blocking=True,
        repair_strategy=repair,
        artifact_path=artifact_path or "segments/manifest.json",
        segment_id=seg_id,
        source="field_parity",
        upstream_stage="boundary_detection" if stage_key == "segment_classification" else None,
    )


def classify_schema_error(stage_key: str, error: str, *, artifact_path: str | None = None) -> ClassifiedIssue:
    low = error.lower()
    path_part = error.split(":")[0] if ":" in error else error
    issue = ClassifiedIssue(
        message=error,
        kind="schema",
        artifact_path=artifact_path,
        json_path=path_part,
        source="schema",
    )

    if "topic_tags" in low and "null" in low:
        issue.severity = "minor"
        issue.repair_strategy = "default_value"
        issue.blocking = False
        return issue

    if "flags" in low:
        issue.severity = "minor"
        issue.repair_strategy = "default_value"
        return issue

    if "null" in low:
        for pat in nullable_fields_for_stage(stage_key):
            if pat.replace("[]", "") in path_part.replace("[", ".").replace("]", ""):
                issue.severity = "minor"
                issue.kind = "null"
                issue.repair_strategy = "default_value"
                issue.blocking = False
                return issue
        for pat in critical_fields_for_stage(stage_key):
            if pat.replace("[]", "") in path_part:
                issue.severity = "critical"
                issue.kind = "null"
                issue.repair_strategy = "llm_pick"
                return issue
        issue.severity = "important"
        issue.kind = "null"
        issue.repair_strategy = "default_value"
        return issue

    issue.severity = "important"
    issue.repair_strategy = "default_value"
    return issue


def classify_sufficiency_finding(
    stage_key: str,
    finding: Any,
    *,
    artifact_path: str | None = None,
) -> ClassifiedIssue:
    blocking = bool(getattr(finding, "blocking", True))
    tier = getattr(getattr(finding, "blocking_tier", None), "value", "progression")
    issue = ClassifiedIssue(
        message=str(getattr(finding, "message", finding)),
        kind="sufficiency",
        severity="critical" if blocking else "minor",
        blocking=blocking,
        artifact_path=artifact_path,
        json_path=str(getattr(finding, "path", "")),
        source="sufficiency",
        repair_strategy=str(getattr(finding, "remediation", "micro_gap_fill")),
        evidence={"blocking_tier": tier},
    )
    return issue


def repair_priority(issue: ClassifiedIssue) -> int:
    order = {
        "default_value": 0,
        "drop_orphan_ref": 1,
        "drop_row": 2,
        "infer_enum": 3,
        "fabricate_missing_segments": 4,
        "fabricate_evaluation": 4,
        "infer_segment_types": 5,
        "merge_overlap": 6,
        "llm_pick": 7,
    }
    return order.get(issue.repair_strategy or "", 8)


def should_auto_repair(issue: ClassifiedIssue) -> bool:
    return issue.severity in ("minor", "noise") and bool(issue.repair_strategy)


def should_llm_options(issue: ClassifiedIssue) -> bool:
    return issue.severity in ("important", "critical") and issue.repair_strategy in (
        "llm_pick",
        "merge_overlap",
        "infer_segment_types",
        "fabricate_missing_segments",
    )
