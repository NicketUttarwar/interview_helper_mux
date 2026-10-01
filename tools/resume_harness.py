#!/usr/bin/env python3
"""Resume harness: prove the engine survives being rewound or killed at any stage.

  python tools/resume_harness.py --source exec_064_... --preset boundaries
  python tools/resume_harness.py --source exec_064_... --rewind vo_synthesize,mix
  python tools/resume_harness.py --source exec_064_... --crash mmaudio_sfx
  python tools/resume_harness.py --source exec_064_... --preset crash --json report.json

Every defect in ISSUES entries 94, 96, 98, 102 and 104 lived on a resume path:
a stage re-entered after a refused commit, a run resumed after ranking had
changed the selection, an engine restarted after a code fix. Straight runs
never walk those paths; this tool does, on purpose.

Each case clones a completed run into a fresh execution, then either

* rewinds it (``clear_from`` at a stage, the same call delivery uses when it
  invalidates analysis) and drives the engine to completion again, or
* starts the engine, kills the whole process tree the moment the named stage
  reports running (a crash, not a clean stop), and restarts it, as many times
  as ``--kills`` asks.

The harness is the operator at both gates, through the same functions the GUI
endpoints call. A case passes only when the run completes with the publish
outputs on disk, adds **zero** error-level lines to the run log, and leaves
no staged files behind for stages that are done. Anything else is a failure
with the first error line quoted, which is what to fix next.

Costs real model calls for every stage after the rewind point. On the
6-minute clip a rewind from ranking is about 40 minutes; the ``boundaries``
preset is an evening. Run one case first.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("PYTHONUTF8", "1")

#: Rewind points that sit on an authority or freeze boundary: each one is a
#: place a defect was found or a place the ownership table changes hands.
BOUNDARY_STAGES: tuple[str, ...] = (
    "gap_framing_compose",
    "full_master_ranking",
    "air_contract_sanitize",
    "sound_design_plan",
    "vo_synthesize",
    "edl",
    "music_palette_compose",
    "mix",
    "master_finalize",
)

#: Crash points: long stages with subprocess children and expensive outputs.
CRASH_STAGES: tuple[str, ...] = (
    "gap_framing_compose",
    "vo_synthesize",
    "mmaudio_sfx",
    "mix",
)

PRESETS: dict[str, dict[str, tuple[str, ...]]] = {
    "boundaries": {"rewind": BOUNDARY_STAGES},
    "crash": {"crash": CRASH_STAGES},
    "quick": {"rewind": ("master_finalize",), "crash": ("mix",)},
}


@dataclass
class CaseResult:
    kind: str
    stage: str
    run_id: str = ""
    ok: bool = False
    seconds: float = 0.0
    stages_done: int = 0
    error_lines_added: int = 0
    first_error: str = ""
    stale_staging: list[str] = field(default_factory=list)
    kills: int = 0
    gates_signed: list[str] = field(default_factory=list)
    engine_exit: int | None = None
    note: str = ""


# ---------------------------------------------------------------------------
# run directory helpers


def _clone_run(source_run_id: str) -> Any:
    """Copy a completed run into a fresh execution directory."""
    from interview_mux.run_context import RunContext

    src = RunContext(source_run_id, create=False)
    dst = RunContext(create=True)
    src_dir, dst_dir = Path(src.run_dir), Path(dst.run_dir)
    for item in src_dir.iterdir():
        if item.name in {".pending_writes", "gui_job.json", ".run.lock", ".archived"}:
            continue
        target = dst_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
    # The clone must not carry the source's engine ownership or driver claim.
    try:
        dst.mutate_run_meta(lambda m: m.pop("orchestrator", None))
    except Exception:
        pass
    claim = dst_dir / "operator" / "driver_claim.json"
    if claim.is_file():
        claim.unlink()
    return dst


def _order_for(stage: str) -> list[str]:
    from interview_mux.pipeline import effective_delivery_order
    from interview_mux.v2.config import ANALYSIS_ORDER

    if stage in ANALYSIS_ORDER:
        return list(ANALYSIS_ORDER)
    order = list(effective_delivery_order())
    if stage not in order:
        raise SystemExit(f"unknown stage: {stage}")
    return order


def _rewind(ctx: Any, stage: str) -> None:
    """Invalidate ``stage`` and everything after it, the way delivery does."""
    from interview_mux.gates import clear_g_publish  # noqa: F401  (import check)

    order = _order_for(stage)
    ctx.clear_from(stage, order)
    # The final sign-off belongs to the new pass.
    ctx.mutate_run_meta(
        lambda m: [m.pop(k, None) for k in ("g_publish_cleared", "g_publish_skipped", "g_publish_pending")]
    )
    marker = Path(ctx.run_dir) / ".stage_done" / "podcast_publish"
    if marker.is_file():
        marker.unlink()


def _error_lines(run_dir: Path) -> list[str]:
    log = run_dir / "gui_log.jsonl"
    if not log.is_file():
        return []
    out: list[str] = []
    with open(log, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"level": "error"' in line:
                try:
                    doc = json.loads(line)
                    out.append(f"[{doc.get('stage')}] {str(doc.get('message') or '')[:220]}")
                except ValueError:
                    out.append(line.strip()[:240])
    return out


def _stale_staging(run_dir: Path) -> list[str]:
    """Staged files left behind for stages that are done."""
    root = run_dir / ".pending_writes"
    done = run_dir / ".stage_done"
    if not root.is_dir():
        return []
    stale: list[str] = []
    for stage_dir in sorted(root.iterdir()):
        if not stage_dir.is_dir() or not (done / stage_dir.name).is_file():
            continue
        for p in stage_dir.rglob("*"):
            if p.is_file() and p.name != ".write.lock":
                stale.append(f"{stage_dir.name}/{p.relative_to(stage_dir).as_posix()}")
    return stale


def _complete(run_dir: Path) -> bool:
    """Done means the package stage ran again on this pass (ISSUES 111)."""
    marker = run_dir / ".stage_done" / "podcast_publish"
    pkg = run_dir / "publish" / "package_ready.json"
    master = run_dir / "master" / "master.wav"
    if not (marker.is_file() and pkg.is_file() and master.is_file()):
        return False
    return pkg.stat().st_mtime >= master.stat().st_mtime


# ---------------------------------------------------------------------------
# engine driver


def _engine_cmd(run_id: str, mode: str) -> list[str]:
    return [sys.executable, "-u", "-m", "interview_mux", "orchestrate", "--mode", mode, "--run-id", run_id]


def _spawn(run_id: str, mode: str, log_path: Path) -> subprocess.Popen[bytes]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env.setdefault("MUX_STUB_LLM", "0")
    fh = open(log_path, "ab")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    return subprocess.Popen(
        _engine_cmd(run_id, mode), cwd=str(ROOT), env=env, stdout=fh, stderr=subprocess.STDOUT,
        creationflags=flags,
    )


def _kill_tree(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.kill()
    try:
        proc.wait(timeout=30)
    except Exception:
        pass


def _job(run_dir: Path) -> dict[str, Any]:
    try:
        return json.loads((run_dir / "gui_job.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sign_off(ctx: Any, job: dict[str, Any], signed: list[str], *, final: str) -> None:
    """Act as the operator at the two human gates, through the GUI's functions."""
    status = str(job.get("status") or "")
    stage = str(job.get("stage") or "")
    if status != "gate":
        return
    if stage == "transcript_review" and "transcript_review" not in signed:
        from interview_mux.gates import check_transcript_review_pending
        from interview_mux.stages.transcript_review import mark_transcript_review_complete

        if check_transcript_review_pending(ctx):
            mark_transcript_review_complete(ctx)
        signed.append("transcript_review")
    elif stage == "g_publish" and "g_publish" not in signed:
        from interview_mux.gates import clear_g_publish

        clear_g_publish(ctx, skipped=(final == "skip"))
        signed.append("g_publish")


def drive(
    ctx: Any,
    *,
    mode: str,
    log_path: Path,
    final: str,
    kill_at: str | None = None,
    kills: int = 1,
    poll: float = 5.0,
    timeout_sec: float = 3 * 3600,
) -> tuple[int | None, int, list[str]]:
    """Run the engine to completion; kill it at ``kill_at`` up to ``kills`` times."""
    run_dir = Path(ctx.run_dir)
    signed: list[str] = []
    killed = 0
    started = time.monotonic()
    proc = _spawn(ctx.run_id, mode, log_path)
    last_exit: int | None = None
    try:
        while True:
            if time.monotonic() - started > timeout_sec:
                _kill_tree(proc)
                return None, killed, signed
            job = _job(run_dir)
            _sign_off(ctx, job, signed, final=final)
            if (
                kill_at
                and killed < kills
                and str(job.get("status") or "") == "running"
                and str(job.get("stage") or job.get("current_stage") or "") == kill_at
            ):
                print(f"      crash: killing engine during {kill_at} (kill {killed + 1}/{kills})", flush=True)
                _kill_tree(proc)
                killed += 1
                time.sleep(3)
                proc = _spawn(ctx.run_id, mode, log_path)
                continue
            rc = proc.poll()
            if rc is not None:
                last_exit = rc
                if _complete(run_dir):
                    return rc, killed, signed
                # The engine stops on a gate timeout or a stop; if a gate is
                # open, sign it and restart, otherwise the case failed.
                job = _job(run_dir)
                if str(job.get("status") or "") == "gate":
                    _sign_off(ctx, job, signed, final=final)
                    proc = _spawn(ctx.run_id, mode, log_path)
                    continue
                return rc, killed, signed
            time.sleep(poll)
    finally:
        _kill_tree(proc)


# ---------------------------------------------------------------------------
# cases


def run_case(
    kind: str,
    stage: str,
    *,
    source: str,
    mode: str,
    final: str,
    kills: int,
    log_dir: Path,
) -> CaseResult:
    res = CaseResult(kind=kind, stage=stage)
    t0 = time.perf_counter()
    ctx = _clone_run(source)
    res.run_id = ctx.run_id
    run_dir = Path(ctx.run_dir)
    log_path = log_dir / f"{kind}_{stage}_{ctx.run_id}.log"
    print(f"--- {kind} {stage}: {ctx.run_id}", flush=True)
    try:
        if kind == "rewind":
            _rewind(ctx, stage)
            kill_at = None
        else:
            # A crash case starts from the rewind point too, so the kill lands
            # on a stage that actually runs rather than one already done.
            _rewind(ctx, stage)
            kill_at = stage
        before = len(_error_lines(run_dir))
        rc, killed, signed = drive(
            ctx, mode=mode, log_path=log_path, final=final, kill_at=kill_at, kills=kills
        )
        res.engine_exit = rc
        res.kills = killed
        res.gates_signed = signed
        errors = _error_lines(run_dir)
        res.error_lines_added = max(0, len(errors) - before)
        if res.error_lines_added:
            res.first_error = errors[before]
        res.stale_staging = _stale_staging(run_dir)
        res.stages_done = len(list((run_dir / ".stage_done").glob("*")))
        res.ok = _complete(run_dir) and res.error_lines_added == 0 and not res.stale_staging
        if not _complete(run_dir):
            res.note = "did not complete"
    except Exception as exc:  # noqa: BLE001 - the harness reports, never dies
        res.note = f"{type(exc).__name__}: {str(exc)[:300]}"
    res.seconds = round(time.perf_counter() - t0, 1)
    flag = "ok  " if res.ok else "FAIL"
    print(
        f"    {flag} {res.seconds:8.1f}s done={res.stages_done} errors+={res.error_lines_added}"
        f" stale={len(res.stale_staging)} kills={res.kills} gates={res.gates_signed}",
        flush=True,
    )
    if res.first_error:
        print(f"      first error: {res.first_error}", flush=True)
    if res.note:
        print(f"      note: {res.note}", flush=True)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="a completed run id to clone")
    ap.add_argument("--rewind", default="", help="comma-separated stages to rewind to and resume from")
    ap.add_argument("--crash", default="", help="comma-separated stages to kill the engine during")
    ap.add_argument("--preset", choices=sorted(PRESETS), default=None)
    ap.add_argument("--mode", default="partially-accelerated", choices=["partially-accelerated", "full-auto"])
    ap.add_argument("--final", default="skip", choices=["skip", "continue"], help="final sign-off answer")
    ap.add_argument("--kills", type=int, default=1, help="crash cases: how many times to kill the engine")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--log-dir", default=str(ROOT / "ASSETS" / "resume_harness"))
    args = ap.parse_args()

    rewind = [s for s in args.rewind.split(",") if s.strip()]
    crash = [s for s in args.crash.split(",") if s.strip()]
    if args.preset:
        rewind += list(PRESETS[args.preset].get("rewind", ()))
        crash += list(PRESETS[args.preset].get("crash", ()))
    if not rewind and not crash:
        ap.error("nothing to do: pass --rewind, --crash or --preset")
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    from interview_mux.run_context import RunContext

    src = RunContext(args.source, create=False)
    if not _complete(Path(src.run_dir)):
        ap.error(f"{args.source} is not a completed run (no podcast_publish marker / publish outputs)")

    print(f"source : {args.source}  mode={args.mode}  final={args.final}")
    print(f"cases  : rewind={rewind} crash={crash} kills={args.kills}")
    print("-" * 78)
    results: list[CaseResult] = []
    for stage in rewind:
        results.append(run_case("rewind", stage, source=args.source, mode=args.mode, final=args.final, kills=0, log_dir=log_dir))
    for stage in crash:
        results.append(run_case("crash", stage, source=args.source, mode=args.mode, final=args.final, kills=args.kills, log_dir=log_dir))
    print("-" * 78)
    passed = sum(1 for r in results if r.ok)
    print(f"{passed}/{len(results)} cases passed")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"source": args.source, "mode": args.mode, "cases": [asdict(r) for r in results]}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"report: {args.json_out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
