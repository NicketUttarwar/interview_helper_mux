"""Issue bus — every catch is recorded; analysis is once per speaker-scoped signature."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.homunculus.ledger import append_ledger, count_problem
from interview_mux.run_context import RunContext

ISSUES_REL = "mastering/homunculus/issues.jsonl"
ANALYSES_DIR = "mastering/homunculus/analyses"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def problem_signature(
    kind: str,
    implicated: list[str] | None = None,
    speaker_id: str | None = None,
) -> str:
    key = kind + "|" + ",".join(sorted(implicated or [])) + "|" + str(speaker_id or "")
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def emit_issue(
    ctx: RunContext,
    *,
    kind: str,
    source: str,
    evidence: dict[str, Any] | None = None,
    stage_id: str | None = None,
    implicated: list[str] | None = None,
    speaker_id: str | None = None,
) -> dict[str, Any]:
    sig = problem_signature(kind, implicated, speaker_id=speaker_id)
    for existing in read_issues(ctx):
        if existing.get("problem_id") == sig:
            return existing
    issue_id = f"iss_{sig}"
    record = {
        "issue_id": issue_id,
        "problem_id": sig,
        "kind": kind,
        "source": source,
        "stage_id": stage_id,
        "implicated": list(implicated or []),
        "speaker_id": speaker_id,
        "evidence": evidence or {},
        "caught_at": _now(),
        "analyzed": False,
    }
    path = ctx.path(ISSUES_REL)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
    append_ledger(
        ctx,
        {
            "kind": "issue",
            "identity": f"issue:{kind}",
            "issue_id": issue_id,
            "problem_id": sig,
        },
    )
    return record


def read_issues(ctx: RunContext) -> list[dict[str, Any]]:
    path = ctx.path(ISSUES_REL)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def analyze_issue(
    ctx: RunContext,
    issue_id: str,
    *,
    quality_hypothesis: str,
    action: str,
    implicated_tools: list[str] | None = None,
    docs_cited: list[str] | None = None,
    style: str | None = None,
) -> dict[str, Any]:
    issue = next((i for i in read_issues(ctx) if i.get("issue_id") == issue_id), None)
    if issue is None:
        raise KeyError(issue_id)
    pid = str(issue.get("problem_id") or issue_id)
    if count_problem(ctx, pid) >= 1:
        raise RuntimeError(f"analyze_issue already ran for {pid}")
    from interview_mux.homunculus.budget import check_dispatch

    check_dispatch(
        ctx,
        identity="analyze_issue",
        kind="analyze_issue",
        problem_id=pid,
    )
    analysis = {
        "issue_id": issue_id,
        "problem_id": pid,
        "quality_hypothesis": quality_hypothesis,
        "action": action,
        "implicated_tools": list(implicated_tools or []),
        "docs_cited": list(docs_cited or []),
        "style": style,
        "speaker_id": issue.get("speaker_id"),
        "at": _now(),
    }
    ctx.write_json(f"{ANALYSES_DIR}/{issue_id}.json", analysis)
    if style or issue.get("speaker_id"):
        try:
            from interview_mux.homunculus.kb import record_style

            record_style(
                ctx,
                speaker_id=str(issue.get("speaker_id") or "unknown"),
                style=str(style or quality_hypothesis)[:240],
                source="analyze_issue",
            )
        except Exception:
            pass
    append_ledger(
        ctx,
        {
            "kind": "analyze_issue",
            "identity": "analyze_issue",
            "issue_id": issue_id,
            "problem_id": pid,
            "action": action,
        },
    )
    return analysis


def has_analysis(ctx: RunContext, issue_id: str) -> bool:
    return ctx.artifact_exists(f"{ANALYSES_DIR}/{issue_id}.json")


def is_homunculus_meta(ctx: RunContext) -> bool:
    if not ctx.artifact_exists("run_meta.json"):
        return False
    ver = str((ctx.read_json("run_meta.json") or {}).get("homunculus_version") or "0.0.0")
    return ver not in {"", "0.0.0"}


def ingest_catch(
    ctx: RunContext,
    *,
    kind: str,
    source: str,
    evidence: dict[str, Any] | None = None,
    stage_id: str | None = None,
    implicated: list[str] | None = None,
    speaker_id: str | None = None,
) -> dict[str, Any] | None:
    """0.1.0: record the catch. 0.0.0: no-op."""
    if not is_homunculus_meta(ctx):
        return None
    return emit_issue(
        ctx,
        kind=kind,
        source=source,
        evidence=evidence,
        stage_id=stage_id,
        implicated=implicated,
        speaker_id=speaker_id,
    )
