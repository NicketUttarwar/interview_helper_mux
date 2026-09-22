#!/usr/bin/env python3
"""Audit artifact ownership — fingerprints, foreign pending VO, and unknown write-sites.

Fail-closed cutover: literal write_json / write_committed_json targets under
src/interview_mux that lack a catalog row are reported as unknown_path_write_site
unless classified operational_unregistered (operator/* / .stage_done/*).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _collect_literal_write_paths(src_root: Path) -> set[str]:
    """AST-scan write_json / write_committed_json string first args."""
    found: set[str] = set()
    for path in src_root.rglob("*.py"):
        if "tests" in path.parts or ".venv" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = ""
            if isinstance(fn, ast.Attribute):
                name = fn.attr
            elif isinstance(fn, ast.Name):
                name = fn.id
            if name not in {
                "write_json",
                "write_committed_json",
                "write_json_validated",
                "write_validated_artifact",
            }:
                continue
            if not node.args:
                continue
            arg0 = node.args[0]
            # ctx.write_json("rel", ...) vs write_validated_artifact(ctx, "rel", ...)
            lit = None
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                lit = arg0.value
            elif len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                if isinstance(node.args[1].value, str):
                    lit = node.args[1].value
            if not lit or "/" not in lit and not lit.endswith(".json"):
                # allow root json like analysis_complete.json
                if lit and lit.endswith(".json"):
                    found.add(lit.replace("\\", "/"))
                continue
            found.add(str(lit).replace("\\", "/"))
    return found


def _sidecar_kind_folder_globs() -> list[str]:
    """A-5: KIND_FOLDERS → transcripts/{speech,vo,transition}/*.json catalog globs."""
    from interview_mux.asset_transcripts import KIND_FOLDERS

    return [f"transcripts/{folder}/*.json" for folder in KIND_FOLDERS.values()]


def _audit_sidecar_kind_folders(findings: list[dict]) -> None:
    """Hard-fail when dynamic sidecar helpers lack ALLOW rows (not blanket **)."""
    from interview_mux.artifact_ownership import row_for_path

    for glob_path in _sidecar_kind_folder_globs():
        # Concrete sample under each folder must resolve via catalog globs.
        sample = glob_path.replace("*.json", "_audit_sample.json")
        if row_for_path(sample) is None and row_for_path(glob_path) is None:
            findings.append(
                {
                    "kind": "missing_sidecar_allow",
                    "path": glob_path,
                }
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execution-id", default="", help="exec_* id under ASSETS/executions")
    ap.add_argument("--run-dir", default="", help="Absolute path to an execution folder")
    ap.add_argument(
        "--write-sites-only",
        action="store_true",
        help="Only scan source write sites vs catalog (no execution folder required)",
    )
    ap.add_argument(
        "--allow-unknown-write-sites",
        action="store_true",
        help="Report unknown write sites but exit 0 (dry-run / canary)",
    )
    args = ap.parse_args()

    from interview_mux.artifact_ownership import (
        owners_of,
        row_for_path,
        matrix_version,
    )

    findings: list[dict] = []

    # Catalog vs live write-site literals
    src_root = _repo_root() / "src" / "interview_mux"
    for rel in sorted(_collect_literal_write_paths(src_root)):
        if rel.startswith("operator/") or rel.startswith(".stage_done/"):
            continue
        if "*" in rel:
            continue
        if row_for_path(rel) is None:
            findings.append(
                {
                    "kind": "unknown_path_write_site",
                    "path": rel,
                }
            )

    _audit_sidecar_kind_folders(findings)

    if args.write_sites_only:
        print(
            json.dumps(
                {
                    "matrix_version": matrix_version(),
                    "findings": findings,
                    "unknown_write_sites": sum(
                        1 for f in findings if f["kind"] == "unknown_path_write_site"
                    ),
                    "missing_sidecar_allow": sum(
                        1 for f in findings if f["kind"] == "missing_sidecar_allow"
                    ),
                },
                indent=2,
            )
        )
        missing_sidecar = any(f["kind"] == "missing_sidecar_allow" for f in findings)
        if missing_sidecar:
            return 1
        if findings and not args.allow_unknown_write_sites:
            return 1
        return 0

    from interview_mux.run_context import RunContext

    if args.run_dir:
        run_dir = Path(args.run_dir)
        ctx = RunContext(run_dir.name, create=False)
    elif args.execution_id:
        ctx = RunContext(args.execution_id, create=False)
        run_dir = ctx.run_dir
    else:
        print("Provide --execution-id, --run-dir, or --write-sites-only", file=sys.stderr)
        return 2

    run_dir = ctx.run_dir

    # Fingerprint producer_stage vs ALLOW
    for path in run_dir.rglob("*.json"):
        if ".pending_writes" in path.parts or ".stage_done" in path.parts:
            continue
        try:
            rel = str(path.relative_to(run_dir)).replace("\\", "/")
        except ValueError:
            continue
        if not row_for_path(rel):
            # Committed unknown path on disk — still a finding under fail-closed cutover.
            if not rel.startswith("operator/") and rel.endswith(".json"):
                findings.append({"kind": "unknown_path_on_disk", "path": rel})
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
        producer = str(
            meta.get("producer_stage")
            or meta.get("authoritative_producer")
            or ""
        ).strip()
        if not producer:
            continue
        allowed = owners_of(rel)
        if allowed and producer not in allowed and producer not in {"ops", "homunculus"}:
            findings.append(
                {
                    "kind": "fingerprint_not_on_allow",
                    "path": rel,
                    "producer_stage": producer,
                    "owners": list(allowed),
                }
            )

    # Pending foreign VO
    pending = run_dir / ".pending_writes"
    if pending.is_dir():
        for stage_dir in pending.iterdir():
            if not stage_dir.is_dir():
                continue
            sid = stage_dir.name
            vo = stage_dir / "vo_pickup"
            if vo.is_dir() and sid not in {"vo_synthesize", "vo_ingest", "audio_preclean"}:
                findings.append(
                    {
                        "kind": "foreign_vo_pending",
                        "stage": sid,
                        "path": "vo_pickup/",
                    }
                )

    print(json.dumps({"matrix_version": matrix_version(), "findings": findings}, indent=2))
    hard = [
        f
        for f in findings
        if f["kind"]
        in {
            "fingerprint_not_on_allow",
            "foreign_vo_pending",
            "unknown_path_write_site",
            "unknown_path_on_disk",
        }
    ]
    if hard and not (
        args.allow_unknown_write_sites
        and all(f["kind"].startswith("unknown_path") for f in hard)
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
