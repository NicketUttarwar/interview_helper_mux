#!/usr/bin/env python3
"""Live progress for a pipeline run: how far it got, and what it is stuck on.

    python tools/run_monitor.py                 # newest run, one snapshot
    python tools/run_monitor.py --watch         # refresh until interrupted
    python tools/run_monitor.py --run-id exec_018_20260927T195709Z

Reads only artifacts already on disk (``.stage_done`` markers, ``gui_log.jsonl``,
``run_meta.json``), so it never interferes with the run it is watching and is
safe to leave open. Nothing here writes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("PYTHONUTF8", "1")


def stage_order() -> tuple[list[str], list[str]]:
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    return list(ANALYSIS_ORDER), list(DELIVERY_ORDER)


def executions_root() -> Path:
    from interview_mux.config import merged_config

    cfg = merged_config()
    raw = str(cfg.get("executions_root") or "ASSETS/executions")
    p = Path(raw)
    return p if p.is_absolute() else (ROOT / p)


def newest_run(root: Path) -> Path | None:
    runs = [d for d in root.glob("exec_*") if d.is_dir()]
    if not runs:
        return None
    return max(runs, key=lambda d: d.stat().st_mtime)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def _tail_log(path: Path, keep: int) -> list[dict]:
    if not path.is_file():
        return []
    try:
        # Runs produce large logs; read the tail rather than the whole file.
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > 400_000:
                fh.seek(-400_000, os.SEEK_END)
                fh.readline()  # discard a partial line
            raw = fh.read().decode("utf-8", errors="replace")
    except Exception:
        return []
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except Exception:
            continue
        if isinstance(doc, dict):
            rows.append(doc)
    return rows[-keep:]


def _bar(done: int, total: int, width: int = 40) -> str:
    if total <= 0:
        return ""
    filled = int(width * done / total)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _age(iso: str) -> str:
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return ""
    secs = (datetime.now(timezone.utc) - then).total_seconds()
    if secs < 0:
        return ""
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else (f"{m}m{s:02d}s" if m else f"{s}s")


def snapshot(run_dir: Path) -> str:
    analysis, delivery = stage_order()
    all_stages = analysis + delivery
    done_dir = run_dir / ".stage_done"
    done = {p.name for p in done_dir.glob("*")} if done_dir.is_dir() else set()

    meta = _read_json(run_dir / "run_meta.json")
    out: list[str] = []
    out.append("=" * 78)
    out.append(f"run      : {run_dir.name}")
    src = str(
        meta.get("input_audio_path")
        or meta.get("source_audio")
        or meta.get("input_audio")
        or "?"
    )
    profile = str(meta.get("source_profile") or "")
    out.append(
        f"source   : {Path(src).name if src != '?' else '?'}"
        + (f"  ({profile})" if profile else "")
    )
    started = str(meta.get("created_at") or meta.get("started_at") or "")
    if started:
        out.append(f"elapsed  : {_age(started)} (since {started[:19]})")

    a_done = sum(1 for s in analysis if s in done)
    d_done = sum(1 for s in delivery if s in done)
    total_done = a_done + d_done
    out.append("")
    out.append(f"progress : {total_done} of {len(all_stages)} stages  {_bar(total_done, len(all_stages))}")
    out.append(f"  analysis {a_done:>2} of {len(analysis)}   delivery {d_done:>2} of {len(delivery)}")

    # The frontier: first incomplete stage in pipeline order is what it is on.
    pending = [s for s in all_stages if s not in done]
    if pending:
        out.append(f"  next    : {pending[0]}")
    else:
        out.append("  next    : (all stages marked complete)")

    # Gates carry .stage_done markers too but are not pipeline stages, so they
    # are counted separately rather than making the N of 72 disagree with the
    # driver's own "stages marked complete" line.
    extra = sorted(done - set(all_stages))
    if extra:
        out.append(f"  gates   : {', '.join(extra)}")

    rows = _tail_log(run_dir / "gui_log.jsonl", 400)
    bad = [
        r for r in rows
        if str(r.get("level", "")).lower() in {"error", "warn", "warning"}
        or "HARD STOP" in str(r.get("message", ""))
    ]
    if bad:
        out.append("")
        out.append("recent problems:")
        for r in bad[-6:]:
            lvl = str(r.get("level", ""))[:5]
            stage = str(r.get("stage", "") or "")[:28]
            msg = " ".join(str(r.get("message", "")).split())[:150]
            out.append(f"  [{lvl:<5}] {stage:<28} {msg}")

    if rows:
        out.append("")
        out.append("last activity:")
        for r in rows[-5:]:
            stage = str(r.get("stage", "") or "")[:28]
            msg = " ".join(str(r.get("message", "")).split())[:150]
            out.append(f"  {stage:<28} {msg}")

    out.append("=" * 78)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default=None, help="defaults to the most recent run")
    ap.add_argument("--watch", action="store_true", help="refresh until interrupted")
    ap.add_argument("--interval", type=float, default=10.0, help="seconds between refreshes")
    args = ap.parse_args()

    root = executions_root()
    if not root.is_dir():
        print(f"no executions root at {root}", file=sys.stderr)
        return 1

    while True:
        run_dir = (root / args.run_id) if args.run_id else newest_run(root)
        if run_dir is None or not run_dir.is_dir():
            print(f"no run found under {root}", file=sys.stderr)
            return 1
        text = snapshot(run_dir)
        if args.watch:
            # Cheaper and less jarring than a full clear on every tick.
            print("\033[2J\033[H", end="")
        print(text, flush=True)
        if not args.watch:
            return 0
        try:
            time.sleep(max(2.0, args.interval))
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
