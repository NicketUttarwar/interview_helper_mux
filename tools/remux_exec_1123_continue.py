#!/usr/bin/env python3
"""Continue remux after VO already synthesized: force full SFX, rebuild EDL/mix/master."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RUN_ID = "exec_1123_1311e28fffa1_20260727T200034Z"


def main() -> int:
    from interview_mux.run_context import RunContext
    from interview_mux.sfx_prompt_review import set_prompt_review_approved
    from interview_mux.stages.assembly import run_edl, run_mix
    from interview_mux.stages.mastering import run_master_finalize
    from interview_mux.stages.sfx_mmaudio import run_sfx_generation

    ctx = RunContext(RUN_ID, create=False)
    set_prompt_review_approved(ctx, approved=True, approved_by="remux_1123_continue")

    def _clear_regen(meta: dict) -> None:
        meta.pop("sfx_regen_asset_ids", None)

    ctx.mutate_run_meta(_clear_regen)
    done = ctx.path(".stage_done", "mmaudio_sfx")
    if done.is_file():
        done.unlink()
    print("generating all SFX assets…", flush=True)
    run_sfx_generation(ctx, profile="podcast")
    assets = list(ctx.path("sound_design", "assets").glob("*.wav"))
    print(f"sfx assets on disk: {[p.name for p in assets]}", flush=True)

    for sid in ("edl", "mix", "master_finalize", "assembly_preview"):
        p = ctx.path(".stage_done", sid)
        if p.is_file():
            p.unlink()

    run_edl(ctx)
    edl = ctx.read_json("master/edl.json")
    vo_n = sum(1 for c in edl.get("clips") or [] if c.get("type") == "vo_pickup")
    tr_n = sum(
        1
        for c in edl.get("clips") or []
        if c.get("type") == "transition" and int(c.get("duration_ms") or 0) > 0
    )
    print(f"edl vo_pickup={vo_n} spoken_transitions={tr_n}", flush=True)
    run_mix(ctx)
    print("mix done", flush=True)
    run_master_finalize(ctx)
    master = ctx.path("master", "master.wav")
    print(
        f"master exists={master.is_file()} size={master.stat().st_size if master.is_file() else 0}",
        flush=True,
    )
    return 0 if master.is_file() and vo_n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
