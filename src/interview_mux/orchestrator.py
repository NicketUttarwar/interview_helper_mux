"""One in-process engine for full-auto and partially-accelerated runs.

Stages run here, in this process, through the real entry points
``run_analysis`` and ``run_delivery``. The web server is left to the two
places a person is needed:

* **G0**, transcript review: the GUI page corrects the transcript and posts
  ``transcript-review/complete``, which stamps ``.stage_done/transcript_review``.
* **Final sign-off**, right before ``podcast_publish``: the GUI page plays the
  master, shows the cover, and posts ``g-publish/continue`` (or ``skip``), which
  stamps ``run_meta.g_publish_cleared`` (or ``g_publish_skipped``).

In ``partially-accelerated`` mode the engine waits at both. In ``full-auto``
mode it signs both off itself. Every other operator gate (framing decision,
gap VO delivery, voice reference, clone consent, timeline optimizer) is signed
off through its real sign-off function in both modes, the way the CLI smoke
driver did on every 72-of-72 run.

The loop is the one from ``tools/stub_pipeline_smoke.py --orchestrated``, the
only in-process re-entry loop the project had: re-enter a phase while gates
were cleared or stages progressed, dispatch a stage a failure names as its own
remedy, hop back to analysis when delivery invalidates an analysis stage, and
stop early on the same error with no progress.

The run directory lock is held only while a phase executes, never while
waiting at a gate, so the GUI's gate POSTs (which take the same lock) go
through. While this engine owns a run, ``POST /execute`` is deferred (see
``orchestrator_owns_run``), so the GUI's own "advance after gate" cannot start
a second walk inside the server.
"""

from __future__ import annotations

import json
import os
import re
import time
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

MODES: frozenset[str] = frozenset({"full-auto", "partially-accelerated"})
#: Cap phase re-entries so a gate that never clears cannot spin forever. A
#: one-hour source needed nine or more progressing delivery passes; the cap
#: only stops passes that keep making progress, stalls stop early.
MAX_GATE_RESUMES = 16
ORCHESTRATOR_META_KEY = "orchestrator"

_RESUME_RE = re.compile(r"resume[= ]+([a-z][a-z0-9_]+)")
_SEED_ORDER_RE = re.compile(r"seed order: complete ([A-Za-z0-9_]+) before")
_AT_FIRST_RE = re.compile(r"\bat ([a-z][a-z0-9_]+) first\b")


def resume_hint(error: str) -> str | None:
    """The stage a failure names as its own remedy, if any."""
    text = str(error or "")
    m = _RESUME_RE.search(text)
    if m:
        return m.group(1)
    m = _SEED_ORDER_RE.search(text)
    if m:
        return m.group(1)
    m = _AT_FIRST_RE.search(text)
    return m.group(1) if m else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pid_alive(pid: int) -> bool:
    try:
        from interview_mux.driver_singleton import _pid_alive as alive

        return bool(alive(pid))
    except Exception:
        return False


def _write_pointer(run_id: str) -> None:
    """Bind this run for the launcher's liveness probes.

    The dual-driver refusal in ``POST /api/runs`` reads this pointer.
    """
    try:
        from interview_mux.config import repo_root

        pointer = repo_root() / "ASSETS" / "full_auto_current_run.txt"
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(run_id + "\n", encoding="utf-8")
    except Exception:
        pass


def orchestrator_owns_run(ctx: RunContext) -> dict[str, Any] | None:
    """The live orchestrator stamp for this run, or None.

    ``POST /execute`` asks this before starting a walk inside the server: the
    GUI calls it after every gate it completes, and a second walk next to the
    engine is exactly the dual-driver problem the job API had.
    """
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    except Exception:
        return None
    row = meta.get(ORCHESTRATOR_META_KEY) if isinstance(meta, dict) else None
    if not isinstance(row, dict) or not row.get("active"):
        return None
    pid = int(row.get("pid") or 0)
    if pid and not _pid_alive(pid):
        return None
    return dict(row)


def final_signoff_pending(ctx: RunContext) -> bool:
    """True until the operator posted g-publish continue or skip."""
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    except Exception:
        return True
    if not isinstance(meta, dict):
        return True
    return not (meta.get("g_publish_cleared") or meta.get("g_publish_skipped"))


def clear_operator_gates(ctx: RunContext, *, sign_off_g0: bool) -> list[str]:
    """Sign off the human-in-the-loop gates the engine is allowed to.

    Signed off through the real sign-off functions rather than forged markers,
    so their side effects still run. G0 is only signed off in full-auto.
    """
    cleared: list[str] = []

    def _try(label: str, fn: Callable[[], bool]) -> None:
        try:
            if fn():
                cleared.append(label)
        except Exception as exc:  # noqa: BLE001 - the loop reports, never dies here
            cleared.append(f"{label}:FAILED({type(exc).__name__}: {str(exc)[:120]})")

    def _g0() -> bool:
        from interview_mux.gates import check_transcript_review_pending
        from interview_mux.stages.transcript_review import mark_transcript_review_complete

        if check_transcript_review_pending(ctx) and ctx.artifact_exists(
            "transcript/review_queue.json"
        ):
            mark_transcript_review_complete(ctx)
            return True
        return False

    if sign_off_g0:
        _try("transcript_review", _g0)

    def _gap_decision() -> bool:
        from interview_mux.gap_vo_gates import (
            check_gap_framing_decision_pending,
            set_gap_framing_enabled,
        )

        if check_gap_framing_decision_pending(ctx):
            set_gap_framing_enabled(ctx, True)
            return True
        return False

    _try("gap_framing_decision", _gap_decision)

    def _gap_delivery() -> bool:
        from interview_mux.gap_vo_gates import check_gap_delivery_pending, set_gap_vo_delivery

        if check_gap_delivery_pending(ctx):
            set_gap_vo_delivery(ctx, "chatterbox")
            return True
        return False

    _try("gap_vo_delivery", _gap_delivery)

    def _voice_ref() -> bool:
        from interview_mux.gap_vo_gates import (
            check_voice_reference_pending,
            mark_voice_reference_approved,
        )
        from interview_mux.source_topology import (
            ensure_speaker_sample_clips,
            pickup_eligible_speaker_id,
        )

        if not check_voice_reference_pending(ctx):
            return False
        sid = pickup_eligible_speaker_id(ctx)
        if not sid:
            return False
        # The GUI extracts the sample clips while showing them; nothing else does.
        ensure_speaker_sample_clips(ctx)
        mark_voice_reference_approved(ctx, sid)
        return True

    _try("voice_reference", _voice_ref)

    def _clone_consent() -> bool:
        from interview_mux.gap_vo_gates import check_clone_consent_pending
        from interview_mux.mastering_voice_clone import grant_consent
        from interview_mux.source_topology import pickup_eligible_speaker_id

        if not check_clone_consent_pending(ctx):
            return False
        sid = pickup_eligible_speaker_id(ctx)
        if not sid:
            return False
        grant_consent(
            ctx,
            speaker_id=sid,
            scopes=["bridges", "cold_open", "outro"],
            granted_by="orchestrator",
            disclosure="none",
        )
        return True

    _try("clone_consent", _clone_consent)

    def _optimizer() -> bool:
        from interview_mux.gates import (
            check_timeline_optimizer_pending,
            clear_timeline_optimizer_gate,
        )

        if not check_timeline_optimizer_pending(ctx):
            try:
                from interview_mux.timeline_optimizer.state import load_optimizer_state

                state = load_optimizer_state(ctx)
            except Exception:
                state = {}
            if not (state.get("status") == "running" and not state.get("operator_took_best")):
                return False
        clear_timeline_optimizer_gate(ctx, skipped=True)
        return True

    _try("timeline_optimizer", _optimizer)
    return cleared


class Orchestrator:
    """Drive one run to the ship bar. See the module docstring."""

    def __init__(
        self,
        ctx: RunContext,
        *,
        mode: str,
        poll_sec: float = 5.0,
        gate_timeout_sec: float = 0.0,
        log: Callable[[str], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if log is None:
            # The console log is a file; block-buffered prints vanish on a
            # hard kill, which is exactly when they are needed.
            def log(line: str) -> None:
                print(line, flush=True)
        if mode not in MODES:
            raise ValueError(f"mode must be one of {sorted(MODES)}, got {mode!r}")
        self.ctx = ctx
        self.mode = mode
        self.poll_sec = max(0.5, float(poll_sec))
        self.gate_timeout_sec = max(0.0, float(gate_timeout_sec))
        self.log = log
        self.sleep = sleep
        self.summary: list[dict[str, Any]] = []

    # ----- properties -------------------------------------------------------
    @property
    def partial(self) -> bool:
        return self.mode == "partially-accelerated"

    # ----- run bookkeeping --------------------------------------------------
    def _stamp(self, active: bool) -> None:
        def _mut(meta: dict[str, Any]) -> None:
            row = dict(meta.get(ORCHESTRATOR_META_KEY) or {})
            row.update({"active": active, "pid": os.getpid(), "mode": self.mode})
            row["started_at" if active else "ended_at"] = _utc_now()
            meta[ORCHESTRATOR_META_KEY] = row
            # The GUI reads this flag in both modes as "a driver owns the run":
            # an explicit False makes it offer the manual Run button next to a
            # stage the engine is executing (ISSUES 82). True while the engine
            # lives, False once it has finished.
            meta["partial_auto_driver_active"] = bool(active)

        try:
            self.ctx.mutate_run_meta(_mut)
        except Exception as exc:  # noqa: BLE001
            self.log(f"orchestrator: run_meta stamp failed: {exc}")

    def _write_job(self, status: str, *, stage: str = "", message: str = "") -> None:
        """Progress for the GUI's job poll, same file the server's runner writes."""
        payload = {
            "run_id": self.ctx.run_id,
            "status": status,
            "mode": "orchestrator",
            "run_mode": self.mode,
            "stage": stage,
            "current_stage": stage,
            "message": message,
            "updated_at": _utc_now(),
        }
        try:
            self.ctx.write_json("gui_job.json", payload, skip_handoff=True)
        except Exception:
            pass

    def _done_count(self) -> int:
        dd = Path(self.ctx.run_dir) / ".stage_done"
        return len(list(dd.glob("*"))) if dd.is_dir() else 0

    # ----- gates ------------------------------------------------------------
    def _wait_for(self, predicate: Callable[[], bool], *, gate: str, message: str) -> bool:
        """Poll ``predicate`` without holding the run lock. False on timeout."""
        if predicate():
            return True
        self.log(f"gate {gate}: {message}")
        self._write_job("gate", stage=gate, message=message)
        started = time.monotonic()
        while not predicate():
            if self.gate_timeout_sec and time.monotonic() - started > self.gate_timeout_sec:
                self.log(f"gate {gate}: timed out after {self.gate_timeout_sec:.0f}s")
                return False
            self.sleep(self.poll_sec)
        self.log(f"gate {gate}: cleared by operator")
        return True

    def _g0_pending(self) -> bool:
        try:
            from interview_mux.gates import check_transcript_review_pending

            return bool(check_transcript_review_pending(self.ctx))
        except Exception:
            return False

    def _clear_gates(self) -> list[str]:
        cleared = clear_operator_gates(self.ctx, sign_off_g0=not self.partial)
        if self.partial and self._g0_pending():
            ok = self._wait_for(
                lambda: not self._g0_pending(),
                gate="transcript_review",
                message="Transcript review: correct the transcript in the GUI, then Complete review.",
            )
            if ok:
                cleared.append("transcript_review:operator")
        for name in cleared:
            self.log(f"      gate cleared: {name}")
        return cleared

    def _sign_off_publish_gate(self) -> None:
        """Stamp the G-Publish sign-off as prepared (full-auto only)."""
        if not final_signoff_pending(self.ctx):
            return
        try:
            from interview_mux.gates import clear_g_publish

            clear_g_publish(self.ctx, skipped=False)
            self.log("      gate cleared: g_publish (full-auto, package prepared)")
        except Exception as exc:  # noqa: BLE001 - reporting only
            self.log(f"      g_publish sign-off failed: {type(exc).__name__}: {str(exc)[:120]}")

    def _final_signoff(self) -> bool:
        """Partial mode: hold before podcast_publish until the operator signs off."""
        if not self.partial:
            return True
        if self.ctx.is_done("podcast_publish"):
            return True
        return self._wait_for(
            lambda: not final_signoff_pending(self.ctx),
            gate="g_publish",
            message="Final sign-off: listen to the master and check the cover, then Continue or Skip.",
        )

    # ----- phases -----------------------------------------------------------
    def _run_phase(self, fn: Callable[..., None], **kwargs: Any) -> dict[str, Any]:
        from interview_mux.run_lock import run_directory_lock

        row: dict[str, Any] = {"status": "ok"}
        t0 = time.perf_counter()
        try:
            with run_directory_lock(self.ctx.run_id):
                fn(self.ctx, **kwargs)
        except SystemExit as exc:
            row["status"] = "halt"
            row["error"] = f"SystemExit: {str(exc)[:500]}"
        except BaseException as exc:  # noqa: BLE001 - the loop decides, not the phase
            row["status"] = "fail"
            row["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
            row["traceback"] = traceback.format_exc()[-2500:]
        row["seconds"] = round(time.perf_counter() - t0, 2)
        return row

    def _delivery_until(self) -> str | None:
        """In partial mode, stop delivery one stage short of podcast_publish."""
        if not self.partial:
            return None
        from interview_mux.v2.config import effective_delivery_order

        order = list(effective_delivery_order())
        if "podcast_publish" not in order:
            return None
        idx = order.index("podcast_publish")
        return order[idx - 1] if idx > 0 else None

    def _phase(self, name: str, fn: Callable[..., None], **kwargs: Any) -> dict[str, Any]:
        """Run a phase and re-enter it while gates clear or stages progress."""
        from interview_mux.pipeline import run_single_stage

        self._write_job("running", stage=name, message=f"Running {name}")
        row = self._run_phase(fn, **kwargs)
        row["phase"] = name
        self.log(f"{name:9} {row['status'].upper():5} {row['seconds']:8.1f}s")
        if row.get("error"):
            self.log(f"      {row['error'][:300]}")

        gates = self._clear_gates()
        attempts = 0
        last_error: str | None = None
        direct_dispatched: set[str] = set()
        progressed = self._done_count()
        before_done = progressed
        # A first pass that fails before anything is marked, naming its own
        # remedy, is still worth one retry: the remedy dispatch lives inside
        # the loop.
        names_remedy = bool(resume_hint(str(row.get("error") or "")))
        while (
            (gates or progressed > 0 or names_remedy)
            and row["status"] != "ok"
            and attempts < MAX_GATE_RESUMES
        ):
            names_remedy = False
            attempts += 1
            self._write_job("running", stage=name, message=f"Resuming {name} ({attempts})")
            again = self._run_phase(fn, **kwargs)
            row["status"] = again["status"]
            row["seconds"] = round(row["seconds"] + again["seconds"], 2)
            row["gate_resumes"] = attempts
            for key in ("error", "traceback"):
                if again.get(key):
                    row[key] = again[key]
                else:
                    row.pop(key, None)
            self.log(
                f"  resume {attempts}: {name} -> {row['status'].upper()} ({row['seconds']:.1f}s total)"
            )
            if row.get("error"):
                self.log(f"      {row['error'][:300]}")
            current_error = str(row.get("error") or "")
            now_done = self._done_count()
            progressed = now_done - (progressed if attempts == 1 else before_done)
            before_done = now_done
            if current_error and progressed <= 0:
                hint = resume_hint(current_error)
                if hint and hint not in direct_dispatched:
                    for _hop in range(3):
                        if not hint or hint in direct_dispatched:
                            break
                        direct_dispatched.add(hint)
                        self.log(f"      dispatching {hint} directly (named as the remedy)")
                        try:
                            from interview_mux.run_lock import run_directory_lock

                            with run_directory_lock(self.ctx.run_id):
                                run_single_stage(self.ctx, hint)
                            landed = bool(self.ctx.is_done(hint))
                            self.log(f"      {hint} -> done={landed}")
                            if landed:
                                progressed = 1
                            break
                        except BaseException as exc:  # noqa: BLE001
                            self.log(
                                f"      {hint} direct dispatch failed: {type(exc).__name__}: {str(exc)[:200]}"
                            )
                            hint = resume_hint(str(exc))
                    last_error = None
                    gates = self._clear_gates()
                    continue
                if current_error == last_error:
                    self.log("      same error as the previous resume and no progress, stopping")
                    break
            if progressed > 0:
                self.log(f"      progress: {progressed} more stage(s) marked complete, retrying")
            last_error = current_error
            gates = self._clear_gates()
        self.summary.append(row)
        return row

    # ----- main -------------------------------------------------------------
    def run(self) -> int:
        from interview_mux.driver_singleton import claim_driver_run, release_driver_run
        from interview_mux.execution_status import pipeline_complete
        from interview_mux.pipeline import run_analysis, run_delivery
        from interview_mux.v2.config import ANALYSIS_ORDER

        claim_driver_run(self.ctx, force=True)
        self._stamp(True)
        _write_pointer(self.ctx.run_id)
        self.log(f"=== orchestrator {self.mode} run={self.ctx.run_id} ===")
        try:
            hops = 0
            until = self._delivery_until()
            row = self._phase("analysis", run_analysis)
            if row["status"] == "ok":
                row = self._phase("delivery", run_delivery, until_stage=until)
                last_hop: tuple[str, int] | None = None
                while row["status"] != "ok" and hops < MAX_GATE_RESUMES:
                    err = str(row.get("error") or "")
                    hop_back = "analysis incomplete" in err or (
                        "seed order: complete " in err
                        and any(f"complete {s} " in err for s in ANALYSIS_ORDER)
                    )
                    if not hop_back:
                        break
                    # A hop that reproduces the previous hop's error with no new
                    # stage landed is a loop, not recovery. exec_065 spent nine
                    # hops and nine error lines on one refused input check
                    # before the invoke cap ended it (ISSUES 106).
                    signature = (err[:200], self._done_count())
                    if last_hop == signature:
                        self.log(
                            "  hop loop: same error and no progress after a hop; stopping"
                        )
                        break
                    last_hop = signature
                    hops += 1
                    self.log(f"  hop {hops}: delivery invalidated analysis, re-running both")
                    a = self._phase("analysis", run_analysis)
                    if a["status"] != "ok":
                        row = a
                        break
                    row = self._phase("delivery", run_delivery, until_stage=until)
            at_signoff = row["status"] == "ok" or (
                row["status"] == "halt"
                and "G-Publish sign-off pending" in str(row.get("error") or "")
            )
            if at_signoff and until and not pipeline_complete(self.ctx):
                # Everything up to the sign-off is done; hold for the operator,
                # then run what remains (podcast_publish, or nothing after Skip).
                # A walk that reached podcast_publish past the boundary halts on
                # the stage's own guard with the same meaning (ISSUES 98).
                if self._final_signoff():
                    row = self._phase("delivery", run_delivery)
            if not self.partial and self.ctx.is_done("podcast_publish"):
                # Full-auto signs the final gate off itself: the package was
                # prepared by podcast_publish, so the GUI must not keep asking
                # for a sign-off nobody is waiting for (ISSUES 92).
                self._sign_off_publish_gate()
            complete = False
            try:
                complete = bool(pipeline_complete(self.ctx))
            except Exception:
                complete = self.ctx.is_done("podcast_publish")
            verdict = run_verdict(self.ctx, complete=complete, error=str(row.get("error") or ""))
            self.log(
                "=== verdict: "
                + ("PASS" if verdict["pass"] else "FAIL")
                + f" complete={verdict['complete']} stages={verdict['stages_done']}"
                + f" error_lines={verdict['error_lines']} stale_staging={len(verdict['stale_staging'])}"
                + f" outputs={verdict['publish_outputs']} ==="
            )
            if complete:
                self._write_job("done", stage="podcast_publish", message="Run complete")
                self.log("=== complete ===")
                return 0
            self._write_job(
                "error",
                stage=str(row.get("phase") or ""),
                message=str(row.get("error") or "incomplete")[:300],
            )
            self.log(f"=== stopped: {str(row.get('error') or 'incomplete')[:300]} ===")
            return 1
        finally:
            self._stamp(False)
            try:
                release_driver_run(self.ctx)
            except Exception:
                pass


PUBLISH_OUTPUTS: tuple[str, ...] = ("publish/audio.mp3", "publish/cover.jpg", "publish/package_ready.json")


def _standing_error_lines(log: Path) -> tuple[list[str], list[str]]:
    """Error-level rows split into standing and recovered.

    A row is recovered when its stage reports "Stage finished" later in the
    same log: the engine's resume loop ran the stage again and it landed
    (ISSUES 114). The acceptance record counts only standing errors; the
    recovered ones stay listed so a noisy run is still visible.
    """
    rows: list[tuple[int, str, str]] = []
    finished_at: dict[str, int] = {}
    try:
        with open(log, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if '"level": "error"' in line:
                    try:
                        doc = json.loads(line)
                        rows.append((i, str(doc.get("stage") or ""), str(doc.get("message") or "")[:200]))
                    except ValueError:
                        rows.append((i, "", line.strip()[:200]))
                elif '"Stage finished: ' in line and '"level": "success"' in line:
                    try:
                        doc = json.loads(line)
                    except ValueError:
                        continue
                    stage = str(doc.get("stage") or "")
                    if stage:
                        finished_at[stage] = i
    except OSError:
        return [], []
    standing: list[str] = []
    recovered: list[str] = []
    for i, stage, msg in rows:
        text = f"[{stage}] {msg}"
        if stage and finished_at.get(stage, -1) > i:
            recovered.append(text)
        else:
            standing.append(text)
    return standing, recovered


def run_verdict(ctx: RunContext, *, complete: bool, error: str = "") -> dict[str, Any]:
    """One deterministic acceptance record for a run (ISSUES 107).

    Written to ``operator/run_verdict.json`` when the engine ends. ``pass`` is
    true only when the pipeline is complete, every publish output is on disk,
    the run log carries no error-level line, and no finished stage left
    staged files behind. Anything less names what is missing, so acceptance
    is a file to read rather than a hunt for master.wav.
    """
    run_dir = Path(ctx.run_dir)
    error_lines: list[str] = []
    recovered: list[str] = []
    log = run_dir / "gui_log.jsonl"
    if log.is_file():
        error_lines, recovered = _standing_error_lines(log)
    stale: list[str] = []
    pending = run_dir / ".pending_writes"
    done = run_dir / ".stage_done"
    if pending.is_dir():
        for stage_dir in sorted(pending.iterdir()):
            if stage_dir.is_dir() and (done / stage_dir.name).is_file():
                for p in stage_dir.rglob("*"):
                    if p.is_file() and p.name != ".write.lock":
                        stale.append(f"{stage_dir.name}/{p.relative_to(stage_dir).as_posix()}")
    outputs = {rel: (run_dir / rel).is_file() for rel in PUBLISH_OUTPUTS}
    skipped = False
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        skipped = bool(isinstance(meta, dict) and meta.get("g_publish_skipped"))
    except Exception:
        skipped = False
    outputs_ok = outputs["publish/package_ready.json"] if skipped else all(outputs.values())
    try:
        from interview_mux.execution_status import package_bound_to_current_master

        package_current = bool(package_bound_to_current_master(ctx))
    except Exception:
        package_current = False
    verdict = {
        "version": 1,
        "run_id": ctx.run_id,
        "complete": bool(complete),
        "stages_done": len(list(done.glob("*"))) if done.is_dir() else 0,
        "error_lines": len(error_lines),
        "first_errors": error_lines[:5],
        "recovered_error_lines": len(recovered),
        "recovered_errors": recovered[:5],
        "stale_staging": stale[:40],
        "publish_outputs": outputs,
        "publish_skipped": skipped,
        "package_current": package_current,
        "stopped_on": str(error or "")[:300],
        "pass": bool(complete and outputs_ok and not error_lines and not stale),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        ctx.write_json("operator/run_verdict.json", verdict, skip_handoff=True)
    except Exception:
        try:
            path = run_dir / "operator" / "run_verdict.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
        except OSError:
            pass
    return verdict


def orchestrate(
    run_id: str,
    *,
    mode: str,
    poll_sec: float = 5.0,
    gate_timeout_sec: float | None = None,
) -> int:
    """Entry point for ``python -m interview_mux orchestrate``."""
    if gate_timeout_sec is None:
        raw = os.environ.get("MUX_ORCHESTRATOR_GATE_TIMEOUT_SEC") or "0"
        try:
            gate_timeout_sec = float(raw)
        except ValueError:
            gate_timeout_sec = 0.0
    ctx = RunContext(run_id, create=False)
    return Orchestrator(
        ctx, mode=mode, poll_sec=poll_sec, gate_timeout_sec=gate_timeout_sec
    ).run()
