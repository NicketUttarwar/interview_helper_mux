"""Invalidation epochs, and the seal-time assertion that backstops precision.

Plan `.cursor/plans/solver_brain_020.plan.md` §5.4 rail 2. Precision invalidation
(`artifact_dependency_graph.transitive_invalidate`) can only introduce one new
failure mode: **under-invalidation** — a stage that should have been re-run is
left alone, and `master/master.wav` ends up built from stale parts. That failure
is silent by nature, so it needs a loud detector at the ship gate rather than an
argument that it is unlikely.

Two halves:

* `record_invalidation()` bumps a monotone counter every time the run actually
  invalidates something, and remembers `master.wav`'s mtime **at that moment**.
* `epoch_failures()` runs inside `master_qc.verify_master` and fails when the
  master file has not changed since an invalidation that touched the stages which
  build it. No wall clock is compared: the witness is "the master file is byte-for
  byte the same file that existed before we tore up its inputs".

The check is deliberately one-directional. It never claims a master is *good*; it
only refuses one that provably predates its own inputs' invalidation.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

EPOCH_REL = "operator/invalidation_epoch.json"
MASTER_REL = "master/master.wav"

# Invalidating any of these tears up something `master.wav` is built from, so a
# master that predates such an event is stale. Kept deliberately small: each
# entry must be a stage whose re-run demonstrably rewrites the EDL or the audio,
# because every entry is a potential false ship-gate failure.
MASTER_PATH_STAGES: frozenset[str] = frozenset(
    {"edl", "mix", "junction_snip_qa", "master_finalize"}
)

_ENV_EPOCH = "MUX_MASTER_EPOCH_ASSERT"
_MAX_EVENTS = 20


def epoch_assert_enabled() -> bool:
    """Default ON. `MUX_MASTER_EPOCH_ASSERT=0` disables the seal-time assertion."""
    raw = os.environ.get(_ENV_EPOCH)
    if raw is None or not str(raw).strip():
        return True
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _mtime_ns(path: Path) -> int | None:
    try:
        return int(path.stat().st_mtime_ns)
    except OSError:
        return None


def read_epoch(run_dir: Any) -> dict[str, Any]:
    path = Path(run_dir) / EPOCH_REL
    if not path.is_file():
        return {}
    try:
        from interview_mux.file_store import read_json as fs_read_json

        doc = fs_read_json(path)
    except Exception:
        return {}
    return doc if isinstance(doc, dict) else {}


def current_epoch(run_dir: Any) -> int:
    return int(read_epoch(run_dir).get("epoch") or 0)


def record_invalidation(
    ctx: Any, from_stage: str, stages: Iterable[str], *, mode: str = "blanket"
) -> int | None:
    """Bump the epoch for one real invalidation. Never raises, never blocks.

    Refuses to write without an ownership ALLOW row, for the same reason the
    conformance recorder does: an observer must not be the reason a run gains a
    write it has no authority for.
    """
    try:
        touched = sorted({str(s) for s in stages if s})
    except Exception:
        return None
    try:
        from interview_mux.artifact_ownership import write_permitted

        ok, _reason = write_permitted(ctx, EPOCH_REL, None, role="ops", verb="persist")
        if not ok:
            return None
    except Exception:
        return None
    try:
        from interview_mux.file_store import write_json as fs_write_json

        run_dir = Path(ctx.run_dir)
        doc = read_epoch(run_dir)
        epoch = int(doc.get("epoch") or 0) + 1
        event = {
            "epoch": epoch,
            "from_stage": str(from_stage),
            "stages": touched,
            "mode": str(mode),
            "master_path": bool(MASTER_PATH_STAGES & set(touched) or from_stage in MASTER_PATH_STAGES),
            "master_wav_mtime_ns": _mtime_ns(run_dir / MASTER_REL),
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        events = [e for e in (doc.get("events") or []) if isinstance(e, dict)]
        events.append(event)
        dest = run_dir / EPOCH_REL
        dest.parent.mkdir(parents=True, exist_ok=True)
        fs_write_json(
            dest,
            {
                "version": 1,
                "epoch": epoch,
                "updated_at": event["at"],
                "last_event": event,
                "events": events[-_MAX_EVENTS:],
            },
        )
        return epoch
    except Exception:
        return None


def last_master_path_event(run_dir: Any) -> dict[str, Any] | None:
    """Most recent invalidation that touched a stage `master.wav` is built from."""
    doc = read_epoch(run_dir)
    events = [e for e in (doc.get("events") or []) if isinstance(e, dict)]
    for event in reversed(events):
        if event.get("master_path"):
            return event
    return None


def run_dir_for_master(master_path: Path) -> Path | None:
    """`<run>/master/master.wav` -> `<run>`. None when the path is not a master."""
    try:
        if master_path.parent.name != "master":
            return None
        return master_path.parent.parent
    except Exception:
        return None


def epoch_failures(master_path: Path) -> list[str]:
    """Ship-gate assertion: does this master predate its inputs' invalidation?

    Fails only on unambiguous evidence — an invalidation event that touched the
    master-building stages, and a `master.wav` whose mtime is *unchanged* since
    that event. Everything else (no epoch record, master absent, master rewritten
    afterwards, unreadable state) passes: this is a backstop, not a new gate, and
    a false failure here would stop a healthy run from shipping.
    """
    if not epoch_assert_enabled():
        return []
    try:
        run_dir = run_dir_for_master(master_path)
        if run_dir is None or not master_path.is_file():
            return []
        event = last_master_path_event(run_dir)
        if not event:
            return []
        recorded = event.get("master_wav_mtime_ns")
        if recorded is None:
            return []  # no master existed when we invalidated — nothing to be stale
        now = _mtime_ns(master_path)
        if now is None or now != int(recorded):
            return []
        return [
            f"Master predates invalidation epoch {event.get('epoch')}: "
            f"{event.get('from_stage')} invalidated "
            f"{', '.join(str(s) for s in (event.get('stages') or [])[:8])} "
            "and master.wav has not been rebuilt since."
        ]
    except Exception:
        return []


__all__ = [
    "EPOCH_REL",
    "MASTER_PATH_STAGES",
    "current_epoch",
    "epoch_assert_enabled",
    "epoch_failures",
    "last_master_path_event",
    "read_epoch",
    "record_invalidation",
    "run_dir_for_master",
]
