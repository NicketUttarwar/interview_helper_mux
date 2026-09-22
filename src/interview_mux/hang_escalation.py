"""Shared hang-budget / fidelity-step primitives for local heavy runners.

Per-runner accept/QA stays runner-specific (MUST-NOT unify accept-usable).
Shared: work-scaled timeout math, hang-vs-abort classification, fidelity rung lists.
"""

from __future__ import annotations

from typing import Any


# MusicGen / MMAudio fidelity ladders (largest → smallest).
MUSICGEN_FIDELITY_RUNGS: tuple[str, ...] = ("large", "medium", "small")
MMAUDIO_FIDELITY_RUNGS: tuple[str, ...] = (
    "large_44k_v2",
    "large_44k",
    "medium_44k",
    "small_44k",
    "small_16k",
)


def budget_for_work(
    *,
    base_timeout_sec: float,
    work_units: float,
    ref_units: float = 1.0,
    max_timeout_sec: float = 2400.0,
    min_timeout_sec: float = 30.0,
) -> int:
    """Scale hang budget by work size with hard floor/cap."""
    base = max(float(min_timeout_sec), float(base_timeout_sec))
    ref = max(1e-6, float(ref_units))
    scale = max(1.0, float(work_units) / ref)
    capped = min(float(max_timeout_sec), max(base, base * scale))
    return int(capped)


def next_fidelity_rung(
    current: str,
    rungs: tuple[str, ...] | list[str],
) -> str | None:
    """Return the next lower fidelity rung, or None when at the bottom."""
    cur = str(current or "").strip().lower()
    ordered = [str(r).strip().lower() for r in rungs]
    if not cur or cur not in ordered:
        return ordered[1] if len(ordered) > 1 else None
    idx = ordered.index(cur)
    if idx + 1 >= len(ordered):
        return None
    return ordered[idx + 1]


def hang_pin_key(*, runtime: str, asset_id: str = "", fidelity: str = "") -> str:
    """Stable key so the same (model, duration, seed, cand) is not re-armed."""
    parts = [str(runtime or "").strip(), str(fidelity or "").strip(), str(asset_id or "").strip()]
    return ":".join(p for p in parts if p)


def classify_hang_vs_abort(
    *,
    returncode: int | None,
    stderr: str = "",
) -> str:
    """Return ``hang``, ``abort``, or ``other``."""
    err = str(stderr or "")
    try:
        rc = int(returncode) if returncode is not None else 0
    except (TypeError, ValueError):
        rc = 0
    if rc == -9 and "timeout after" in err:
        return "hang"
    if "timed out" in err.lower() or "timeout after" in err:
        return "hang"
    from interview_mux.heavy_task_policy import is_heavy_kill_returncode

    if is_heavy_kill_returncode(rc) and "timeout after" not in err:
        return "abort"
    return "other"


def kill_process_tree(proc: Any, *, timeout_sec: float = 5.0) -> None:
    """Best-effort kill of a hung Popen before releasing GPU lock."""
    if proc is None:
        return
    try:
        if getattr(proc, "poll", None) and proc.poll() is not None:
            return
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        try:
            proc.terminate()
        except Exception:
            return
    try:
        proc.wait(timeout=float(timeout_sec))
    except Exception:
        pass
