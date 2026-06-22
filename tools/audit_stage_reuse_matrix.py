#!/usr/bin/env python3
"""Audit stage reuse matrix: registry vs _STAGE_REUSE_OUTPUTS vs reuse_policy."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.stage_execution_reuse import _STAGE_REUSE_OUTPUTS  # noqa: E402
from interview_mux.web.stages import STAGE_BY_ID, reuse_policy_for  # noqa: E402


def main() -> int:
    errors: list[str] = []
    for sid, info in sorted(STAGE_BY_ID.items()):
        policy = reuse_policy_for(sid)
        has_outputs = sid in _STAGE_REUSE_OUTPUTS
        if policy == "eligible" and not has_outputs:
            errors.append(f"{sid}: reuse_policy=eligible but missing _STAGE_REUSE_OUTPUTS")
        if policy == "eligible" and has_outputs and not _STAGE_REUSE_OUTPUTS[sid]:
            errors.append(f"{sid}: reuse_policy=eligible but empty _STAGE_REUSE_OUTPUTS")
        if has_outputs and policy not in ("eligible", "gate", "on_demand"):
            errors.append(f"{sid}: has reuse outputs but policy={policy}")
        if info.phase == "gate" and policy not in ("gate", "none"):
            pass  # gates may still copy artifacts
    if errors:
        print("Reuse matrix audit FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK — {len(STAGE_BY_ID)} stages, {len(_STAGE_REUSE_OUTPUTS)} reuse output entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
