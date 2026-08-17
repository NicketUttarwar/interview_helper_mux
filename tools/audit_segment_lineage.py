#!/usr/bin/env python3
"""Audit segment ID lineage across all pipeline artifacts for a run or fixture chain."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from interview_mux.segment_lineage_audit import audit_run  # noqa: E402
from run_fixtures import isolated_run_ctx, patch_merged_config  # noqa: E402


def _run_fixture_audit() -> dict:
    from typing import Any
    from unittest.mock import patch

    from interview_mux.config import merged_config
    from progression_chain_sanity_helpers import FULL_PROGRESSION_CHAIN, run_progression_chain_sanity

    tmp = Path(tempfile.mkdtemp(prefix="lineage_audit_"))
    base = merged_config()
    cfg = {
        **base,
        "analysis": {
            **(base.get("analysis") or {}),
            "flow_hardening": {"enabled": True},
            "gap_vo": {
                **((base.get("analysis") or {}).get("gap_vo") or {}),
                "post_synthesis_qc": {
                    **(
                        ((base.get("analysis") or {}).get("gap_vo") or {}).get(
                            "post_synthesis_qc"
                        )
                        or {}
                    ),
                    "enabled": False,
                    "speech_qa_enabled": False,
                },
            },
        },
        "creative_delivery": {
            **(base.get("creative_delivery") or {}),
            "required": False,
        },
        "soundscape": {
            **(base.get("soundscape") or {}),
            "fail_closed": False,
        },
    }

    class _Patch:
        def __init__(self) -> None:
            self._patches: list[Any] = []

        def setattr(self, target: Any, name: str, value: Any) -> None:
            p = patch.object(target, name, value)
            p.start()
            self._patches.append(p)

        def stop(self) -> None:
            for p in reversed(self._patches):
                p.stop()

    mp = _Patch()
    try:
        patch_merged_config(mp, cfg)  # type: ignore[arg-type]
        ctx = isolated_run_ctx(tmp, "lineage_audit_fixture")
        sanity = run_progression_chain_sanity(ctx, chain=list(FULL_PROGRESSION_CHAIN))
        report = audit_run(ctx)
        report["progression_sanity_ok"] = sanity.get("ok", False)
        if not sanity.get("ok"):
            report["hard_failures"] = list(report.get("hard_failures") or []) + [
                f"progression_chain_sanity: {f}" for f in (sanity.get("failures") or [])[:4]
            ]
            report["ok"] = False
        return report
    finally:
        mp.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="Execution run id under ASSETS/executions/")
    parser.add_argument(
        "--run-dir",
        help="Absolute path to execution workspace (alternative to --run-id)",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Audit isolated fixture progression chain (CI mode)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    if args.fixture:
        report = _run_fixture_audit()
    elif args.run_dir:
        from interview_mux.run_context import RunContext

        ctx = RunContext(Path(args.run_dir))
        report = audit_run(ctx)
    elif args.run_id:
        from interview_mux.run_context import RunContext

        ctx = RunContext(args.run_id, create=False)
        report = audit_run(ctx)
    else:
        parser.error("Provide --fixture, --run-id, or --run-dir")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Segment lineage audit")
        print(f"  ok: {report.get('ok')}")
        print(f"  manifest segments: {report.get('manifest_segment_count')}")
        print(f"  selection segments: {report.get('selection_segment_count')}")
        for err in report.get("hard_failures") or []:
            print(f"  FAIL: {err}")
        for warn in report.get("warnings") or []:
            print(f"  WARN: {warn}")

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
