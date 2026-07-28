#!/usr/bin/env python3
"""Remux exec_1123: un-skip G1 VO, synthesize gap+transition VO, complete SFX, rebuild EDL/mix/master."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RUN_ID = "exec_1123_1311e28fffa1_20260727T200034Z"


def main() -> int:
    from interview_mux.run_context import RunContext
    from interview_mux.s2s_runner import synthesize_line
    from interview_mux.sfx_prompt_review import set_prompt_review_approved
    from interview_mux.stages.assembly import run_edl, run_mix
    from interview_mux.stages.mastering import run_master_finalize
    from interview_mux.stages.sfx_mmaudio import run_sfx_generation

    ctx = RunContext(RUN_ID, create=False)

    def _clear_skip(meta: dict) -> None:
        meta.pop("g1_vo_skipped_optional", None)
        meta.pop("g1_skip_applied_line_ids", None)

    ctx.mutate_run_meta(_clear_skip)
    gr = ctx.read_json("understanding/gap_report.json")
    for line in gr.get("interviewer_lines") or []:
        if isinstance(line, dict):
            line.pop("skipped_optional", None)
            if line.get("delivery") == "synthesize":
                line["blocking"] = True
    ctx.write_json("understanding/gap_report.json", gr)
    print(f"cleared skip on {len(gr.get('interviewer_lines') or [])} lines")

    ok = 0
    err = 0
    for line in gr.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        if str(line.get("delivery") or "").lower() != "synthesize":
            continue
        lid = line.get("line_id")
        try:
            out = synthesize_line(ctx, line, mode="synthesize")
            print(f"  VO ok {lid}: {out}")
            ok += 1
        except Exception as exc:
            print(f"  VO FAIL {lid}: {exc}")
            err += 1
    print(f"VO synthesize done ok={ok} err={err}")
    if err:
        return 1

    if ctx.artifact_exists("sound_design/sfx_prompts.json"):
        set_prompt_review_approved(ctx, approved=True, approved_by="remux_1123")
        print("sfx prompts approved")

    # Clear refine-only regen filter so ALL SDP assets generate.
    def _clear_regen(meta: dict) -> None:
        meta.pop("sfx_regen_asset_ids", None)

    ctx.mutate_run_meta(_clear_regen)

    done = ctx.path(".stage_done", "mmaudio_sfx")
    if done.is_file():
        done.unlink()
    try:
        run_sfx_generation(ctx, profile="podcast")
        print("sfx generation complete")
    except Exception as exc:
        print(f"sfx generation: {exc}")
        return 1

    for sid in ("edl", "mix", "master_finalize", "assembly_preview"):
        p = ctx.path(".stage_done", sid)
        if p.is_file():
            p.unlink()

    try:
        run_edl(ctx)
        print("edl rebuilt")
    except Exception as exc:
        print(f"edl failed: {exc}")
        return 1

    edl = ctx.read_json("master/edl.json")
    vo_n = sum(1 for c in edl.get("clips") or [] if c.get("type") == "vo_pickup")
    tr_n = sum(
        1
        for c in edl.get("clips") or []
        if c.get("type") == "transition" and int(c.get("duration_ms") or 0) > 0
    )
    print(f"edl vo_pickup={vo_n} spoken_transitions={tr_n}")

    try:
        run_mix(ctx)
        print("mix done")
    except Exception as exc:
        print(f"mix failed: {exc}")
        return 1

    try:
        run_master_finalize(ctx)
        print("master finalized")
    except Exception as exc:
        print(f"master finalize failed: {exc}")
        return 1

    master = ctx.path("master", "master.wav")
    print(f"master exists={master.is_file()} size={master.stat().st_size if master.is_file() else 0}")
    return 0 if master.is_file() and vo_n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
