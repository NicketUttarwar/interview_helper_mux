#!/usr/bin/env python3
"""Migrate legacy three-flow exec_* runs to single-flow layout (master/, renamed stage markers)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_STAGE_MARKER_RENAMES = {
    "sound_design_plan_flow1": "sound_design_plan",
    "edl_flow1": "edl",
    "mmaudio_sfx_flow1": "mmaudio_sfx",
    "mix_flow1": "mix",
    "master_flow1": "master_finalize",
}


def _rewrite_sdp_flow_plans(plan: dict) -> dict:
    fp = plan.get("flow_plans")
    if not isinstance(fp, dict):
        return plan
    if "podcast" not in fp and "flow1" in fp:
        fp["podcast"] = fp.pop("flow1")
    fp.pop("flow2", None)
    plan["flow_plans"] = fp
    return plan


def migrate_run(run_dir: Path, *, dry_run: bool = False) -> list[str]:
    actions: list[str] = []
    legacy_master = run_dir / "flow_1_master"
    master = run_dir / "master"
    if legacy_master.is_dir() and not master.exists():
        actions.append(f"mv {legacy_master.name}/ → master/")
        if not dry_run:
            legacy_master.rename(master)

    done_dir = run_dir / ".stage_done"
    if done_dir.is_dir():
        for old, new in _STAGE_MARKER_RENAMES.items():
            old_p = done_dir / old
            new_p = done_dir / new
            if old_p.is_file() and not new_p.exists():
                actions.append(f"rename .stage_done/{old} → {new}")
                if not dry_run:
                    old_p.rename(new_p)

    meta_path = run_dir / "run_meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        changed = False
        for key in ("selected_flow", "flow_intent", "selected_at", "flow_intent_at"):
            if key in meta:
                meta.pop(key, None)
                changed = True
        if changed:
            actions.append("strip selected_flow/flow_intent from run_meta.json")
            if not dry_run:
                meta["updated_at"] = datetime.now(timezone.utc).isoformat()
                meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    sdp_path = run_dir / "understanding" / "sound_design_plan.json"
    if sdp_path.is_file():
        plan = json.loads(sdp_path.read_text(encoding="utf-8"))
        before = json.dumps(plan.get("flow_plans", {}), sort_keys=True)
        plan = _rewrite_sdp_flow_plans(plan)
        after = json.dumps(plan.get("flow_plans", {}), sort_keys=True)
        if before != after:
            actions.append("rewrite flow_plans.flow1 → podcast; drop flow2")
            if not dry_run:
                sdp_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    flow_sel = run_dir / "operator" / "flow_selection.json"
    if flow_sel.is_file():
        actions.append("remove operator/flow_selection.json")
        if not dry_run:
            flow_sel.unlink()

    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Path to exec_* run directory")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        print(f"Not a directory: {run_dir}", file=sys.stderr)
        return 1
    actions = migrate_run(run_dir, dry_run=args.dry_run)
    if not actions:
        print("Nothing to migrate.")
        return 0
    prefix = "[dry-run] " if args.dry_run else ""
    for a in actions:
        print(f"{prefix}{a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
