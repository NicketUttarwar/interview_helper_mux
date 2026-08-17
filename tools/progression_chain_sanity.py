#!/usr/bin/env python3
"""Run cross-stage progression sanity (stage 11 / segment_classification → flow text stages)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from interview_mux.config import merged_config  # noqa: E402
from progression_chain_sanity_helpers import (  # noqa: E402
    FULL_PROGRESSION_CHAIN,
    PROGRESSION_ANALYSIS_STAGES,
    PROGRESSION_FLOW_STAGES,
    run_progression_chain_sanity,
)
from run_fixtures import isolated_run_ctx, patch_merged_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        choices=("analysis", "full"),
        default="full",
        help="analysis = segment_classification..optimal_questions; full includes flow fixture stages",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    import tempfile
    from typing import Any
    from unittest.mock import patch

    tmp = Path(tempfile.mkdtemp(prefix="progression_sanity_"))
    base = merged_config()
    cfg = {
        **base,
        "journey_ui": {
            **(base.get("journey_ui") or {}),
            "require_write_approval_per_stage": True,
        },
        "analysis": {
            **(base.get("analysis") or {}),
            "artifact_issue_triage": {"enabled": True},
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
        # Fixture plans are intentionally sparse — disable live density gates.
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

        ctx = isolated_run_ctx(tmp, "progression_sanity_cli")
        chain = (
            list(PROGRESSION_ANALYSIS_STAGES)
            if args.scope == "analysis"
            else list(FULL_PROGRESSION_CHAIN)
        )
        report = run_progression_chain_sanity(ctx, chain=chain, include_write_approval_regression=True)
    finally:
        mp.stop()


    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Progression chain sanity — scope={args.scope}")
        print(f"Chain length: {len(chain)}")
        for stage_id, info in report["stages"].items():
            status = "OK" if info.get("ok", True) and not info.get("failures") else "FAIL"
            if info.get("skipped") or info.get("skipped_commit"):
                status = "SKIP"
            print(f"  [{status}] {stage_id}")
            for f in info.get("failures") or []:
                print(f"         - {f}")
            for f in info.get("downstream_input_failures") or []:
                print(f"         - downstream: {f}")
        if report.get("write_approval_regression"):
            wa = report["write_approval_regression"]
            print(f"Write-approval regression: {'OK' if not wa else 'FAIL'}")
            for f in wa:
                print(f"         - {f}")
        print(f"Overall: {'PASS' if report['ok'] else 'FAIL'}")
        if report["failures"]:
            print("\nFailures:")
            for f in report["failures"]:
                print(f"  - {f}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
