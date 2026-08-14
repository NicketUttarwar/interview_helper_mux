#!/usr/bin/env python3
"""Synthesize any G1 VO lines whose pickup WAV is missing or script-hash stale."""

from __future__ import annotations

import shutil
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    run_id = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not run_id:
        for name in ("full_auto_current_run.txt", "baba_current_run.txt"):
            pointer = ROOT / "ASSETS" / name
            if pointer.is_file():
                run_id = pointer.read_text(encoding="utf-8").strip()
                if run_id:
                    break
        else:
            run_id = ""
    if not run_id:
        print("usage: _g1_resynth_missing.py <run_id>", flush=True)
        return 2

    from interview_mux import s2s_runner
    from interview_mux.gates import check_g1_vo
    from interview_mux.run_context import RunContext
    from interview_mux.stages.assembly import resolve_vo_pickup_path

    ctx = RunContext(run_id)
    for rounds in range(1, 4):
        missing = check_g1_vo(ctx)
        print(f"=== round {rounds} missing={len(missing)} {missing} ===", flush=True)
        if not missing:
            break
        gr = ctx.read_json("understanding/gap_report.json")
        by_id = {
            str(L.get("line_id")): L
            for L in (gr.get("interviewer_lines") or [])
            if isinstance(L, dict)
        }
        for lid in missing:
            line = by_id.get(lid)
            if not line:
                print(f"no line {lid}", flush=True)
                continue
            if resolve_vo_pickup_path(ctx, line) is not None:
                print(f"skip {lid}", flush=True)
                continue
            print(f"synth {lid} ...", flush=True)
            t0 = time.time()
            try:
                s2s_runner.synthesize_line(ctx, line, mode="synthesize")
                print(f"ok {lid} in {time.time() - t0:.1f}s", flush=True)
            except Exception as exc:
                print(f"FAIL {lid}: {exc}", flush=True)
                traceback.print_exc()
        synth = ctx.final_path("vo_pickup") / "synthesized"
        dest = ctx.final_path("vo_pickup")
        if synth.is_dir():
            for wav in synth.glob("*.wav"):
                shutil.copy2(wav, dest / wav.name)
    print("DONE missing", check_g1_vo(ctx), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
