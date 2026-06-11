#!/usr/bin/env python3
"""Export labeled LLM call records from a run for review and copy-paste."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.config import merged_config, repo_root
from interview_mux.llm_call_record import (
    list_calls_for_run,
    load_call_record,
    record_to_markdown,
    reconstruct_volley_from_calls,
)
from interview_mux.run_context import RunContext


def _stage_run_audit_appendix(run_dir: Path, stage_filter: str | None) -> str:
    """Summarize arbiter verdicts and deterministic lint from stage_runs attempts."""
    base = run_dir / "understanding" / "stage_runs"
    if not base.is_dir():
        return ""
    lines = ["# Stage run audit (arbiter + lint)", ""]
    count = 0
    for stage_dir in sorted(base.iterdir()):
        if not stage_dir.is_dir():
            continue
        if stage_filter and stage_dir.name != stage_filter:
            continue
        for attempt in sorted(stage_dir.glob("attempt_*.json")):
            try:
                doc = json.loads(attempt.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            arb = doc.get("arbiter_result") or {}
            lint = doc.get("deterministic_lint_errors") or []
            verdict = arb.get("verdict", "")
            lines.append(f"## {stage_dir.name} / {attempt.name}")
            lines.append(f"- arbiter_verdict: {verdict}")
            if lint:
                lines.append(f"- deterministic_lint: {'; '.join(str(x) for x in lint[:4])}")
            sig = doc.get("attempt_signature")
            if sig:
                lines.append(f"- attempt_signature: {sig}")
            lines.append("")
            count += 1
            if count >= 40:
                break
    return "\n".join(lines) if count else ""


def _resolve_run_dir(run_id: str) -> Path:
    ctx = RunContext(run_id, create=False)
    if not ctx.run_dir.is_dir():
        raise SystemExit(f"Run not found: {run_id}")
    return ctx.run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="exec_* or run_* id")
    parser.add_argument("--stage", help="Filter by stage_key")
    parser.add_argument("--attempt", type=int, help="Filter by attempt number")
    parser.add_argument("--importance", choices=("high", "medium", "low"))
    parser.add_argument("--label-contains", help="Substring match on label")
    parser.add_argument(
        "--format",
        choices=("markdown", "jsonl", "volley"),
        default="markdown",
    )
    parser.add_argument("-o", "--output", help="Write to file (default: stdout)")
    args = parser.parse_args()

    run_dir = _resolve_run_dir(args.run_id)
    rows = list_calls_for_run(run_dir)
    if args.stage:
        rows = [r for r in rows if r.get("stage_key") == args.stage]
    if args.attempt is not None:
        rows = [r for r in rows if r.get("attempt") == args.attempt]
    if args.importance:
        rows = [r for r in rows if r.get("importance") == args.importance]
    if args.label_contains:
        needle = args.label_contains
        rows = [r for r in rows if needle in (r.get("label") or "")]

    records = []
    for row in rows:
        path = run_dir / row["path"]
        if path.is_file():
            records.append(load_call_record(path))

    if args.format == "volley":
        out = json.dumps(reconstruct_volley_from_calls(records), indent=2, ensure_ascii=False)
    elif args.format == "jsonl":
        lines = [json.dumps(rec, ensure_ascii=False) for rec in records]
        out = "\n".join(lines) + ("\n" if lines else "")
    else:
        parts = [record_to_markdown(rec) for rec in records]
        audit = _stage_run_audit_appendix(run_dir, args.stage)
        if audit:
            parts.append(audit)
        out = "\n---\n\n".join(parts)

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {len(records)} record(s) to {args.output}")
    else:
        print(out)


if __name__ == "__main__":
    main()
