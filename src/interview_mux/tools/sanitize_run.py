"""CLI: python -m interview_mux.tools.sanitize_run"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


_ARTIFACT_ALIASES = {
    "selection": "master/selection.json",
    "gap": "understanding/gap_report.json",
    "gap_report": "understanding/gap_report.json",
    "transitions": "master/transitions.json",
    "edl": "master/edl.json",
    "vo": "mastering/vo_synthesize.json",
    "vo_synthesize": "mastering/vo_synthesize.json",
    "synthesis_report": "vo_pickup/synthesis_report.json",
    "bind": "vo_pickup/synthesis_report.json",
    "layup": "understanding/nugget_layup_plan.json",
    "sdp": "understanding/sound_design_plan.json",
    "sound_design_plan": "understanding/sound_design_plan.json",
    "air": "mastering/mastering_plan.json",
    "air_contract": "mastering/mastering_plan.json",
    "omit": "understanding/omit_ledger.json",
}


def _commit_result(ctx: Any, rel: str, result: Any) -> None:
    from interview_mux.artifact_sanitize.halt import resume_stage_for_artifact

    if rel == "master/selection.json":
        from interview_mux.air_order_boundary import commit_selection_mutation

        commit_selection_mutation(
            ctx,
            result.doc,
            producer="artifact_sanitize.selection",
            stage_key="selection_order_sanitize",
            checkpoint_mode="detect",
        )
        print("committed master/selection.json")
        try:
            ctx.mark_done("selection_order_sanitize")
        except Exception:
            pass
        return

    if rel == "understanding/gap_report.json":
        ctx.write_json(rel, result.doc, skip_handoff=True, stage_key="gap_report_sanitize")
        print(f"committed {rel}")
        try:
            ctx.mark_done("gap_report_sanitize")
        except Exception:
            pass
        return

    if rel in {"mastering/mastering_plan.json", "understanding/omit_ledger.json"}:
        from interview_mux.artifact_sanitize.air_script import commit_air_contract

        commit_air_contract(ctx, reason="sanitize_run")
        print("committed air contract (plan + gap flags + omit)")
        try:
            ctx.mark_done("air_contract_sanitize")
        except Exception:
            pass
        return

    if rel == "understanding/nugget_layup_plan.json":
        ctx.write_json(rel, result.doc, skip_handoff=True, stage_key="nugget_layup_compose")
        print(f"committed {rel}")
        return

    if rel == "master/transitions.json":
        from interview_mux.transition_vo import persist_transitions_doc

        persist_transitions_doc(
            ctx, result.doc, stage_key="transitions", skip_handoff=True
        )
        print(f"committed {rel}")
        return

    if rel == "master/edl.json":
        from interview_mux.artifact_sanitize.edl import persist_edl_and_ledger

        persist_edl_and_ledger(ctx, result.doc, source="sanitize_run")
        print("committed master/edl.json + assembly_ledger")
        return

    if rel in {
        "mastering/vo_synthesize.json",
        "vo_pickup/synthesis_report.json",
        "understanding/sound_design_plan.json",
    }:
        ctx.write_json(rel, result.doc, skip_handoff=True, stage_key="sanitize_run")
        print(f"committed {rel}")
        stage = resume_stage_for_artifact(rel)
        try:
            if stage:
                ctx.mark_done(stage)
        except Exception:
            pass
        return

    ctx.write_json(rel, result.doc, skip_handoff=True, stage_key="sanitize_run")
    print(f"committed {rel}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Sanitize a baseline artifact for a run")
    p.add_argument("--run-id", required=True)
    p.add_argument("--artifact", default="selection")
    p.add_argument("--commit", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    from interview_mux.artifact_sanitize.registry import sanitize_artifact
    from interview_mux.run_context import RunContext

    rel = _ARTIFACT_ALIASES.get(str(args.artifact).strip().lower(), str(args.artifact))
    ctx = RunContext(args.run_id, create=False)

    # Air contract is a multi-artifact commit helper.
    if args.commit and rel in {
        "mastering/mastering_plan.json",
        "understanding/omit_ledger.json",
    }:
        from interview_mux.artifact_sanitize.air_script import commit_air_contract

        result = commit_air_contract(ctx, reason="sanitize_run")
    else:
        result = sanitize_artifact(ctx, rel, mode="cli", stage_key="sanitize_run")

    if args.json:
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "errors": result.errors,
                    "actions": result.actions,
                    "metrics": result.metrics,
                    "artifact": getattr(result, "artifact_rel", rel) or rel,
                },
                indent=2,
            )
        )
    else:
        print(f"artifact={rel} ok={result.ok} actions={len(result.actions or [])}")
        for a in (result.actions or [])[:20]:
            print(f"  - {a}")
        for e in result.errors or []:
            print(f"  ERROR: {e}")

    if args.commit and result.ok:
        if rel not in {
            "mastering/mastering_plan.json",
            "understanding/omit_ledger.json",
        }:
            _commit_result(ctx, rel, result)
        else:
            print("committed air contract (plan + gap flags + omit)")
            try:
                ctx.mark_done("air_contract_sanitize")
            except Exception:
                pass
    elif args.commit and not result.ok:
        print("refuse commit: sanitize not ok", file=sys.stderr)
        return 2
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
