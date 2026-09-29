#!/usr/bin/env python3
"""Traverse the whole pipeline with no API key and no network.

  python tools/stub_pipeline_smoke.py                    # all 72 stages
  python tools/stub_pipeline_smoke.py --until edl        # stop after a stage
  python tools/stub_pipeline_smoke.py --from transcribe  # resume
  python tools/stub_pipeline_smoke.py --keep             # keep the run dir
  python tools/stub_pipeline_smoke.py --json report.json # machine-readable

Every LLM call is served by ``interview_mux.stub_llm``, which generates a reply
from the JSON schema the stage itself requested, so the response is structurally
valid by construction. Everything else is real: real stage code, real artifact
writes, real sanitize and cross-validation, real gates, real local models where
they are installed.

What a green run proves: every stage executes, writes its artifacts, and passes
its own validators and the gates between stages. What it does not prove: output
quality, or that a real model's reply would be well-formed. Those need a key.

Stages are run one at a time rather than through run_analysis/run_delivery so a
failure names the stage and the traversal can continue past it, which is what
makes this useful as a diagnostic rather than a pass/fail gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import sys
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
#: Cap resumes so a gate that never clears cannot spin forever. Resumes also
#: fire on progress (more stages marked than the previous pass), with an early
#: stop on same-error-no-progress, so a healthy run can spend all of these
#: usefully: the 6-minute real run used four and was still advancing.
# A one-hour source needed 9+ progressing delivery passes (exec_052/054); the
# cap only stops passes that keep making progress, stalls still stop early.
MAX_GATE_RESUMES = 16
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("PYTHONUTF8", "1")


def _default_stub_env() -> None:
    """Stub the LLM unless the caller chose otherwise (``MUX_STUB_LLM=0``).

    Called from ``main`` and not at import: importing this module from a test
    used to switch the whole pytest worker into stub mode, which broke the
    real-client llm_runner and safe_pruning tests on that worker.
    """
    os.environ.setdefault("MUX_STUB_LLM", "1")


_RESUME_RE = re.compile(r"resume[= ]+([a-z][a-z0-9_]+)")


_SEED_ORDER_RE = re.compile(r"seed order: complete ([A-Za-z0-9_]+) before")
_AT_FIRST_RE = re.compile(r"\bat ([a-z][a-z0-9_]+) first\b")


def resume_hint(error: str) -> str | None:
    """The stage a failure names as its own remedy, if any.

    The conductor writes "resume=mix" or "resume mix" into its errors, then
    on the next pass names the same stage as remaining without dispatching it.
    Three stops on the 6-minute real run were exactly that (vo_line_adjudicate,
    mix twice), and each cleared the moment the stage was dispatched directly.
    """
    text = str(error or "")
    m = _RESUME_RE.search(text)
    if m:
        return m.group(1)
    # "seed order: complete X before running Y" names X the same way: the
    # walk wants X first and, on exec_050, kept saying so without running it.
    m = _SEED_ORDER_RE.search(text)
    if m:
        return m.group(1)
    # "... recut/fuse/omit at junction_snip_qa first" (a stage's own refusal).
    m = _AT_FIRST_RE.search(text)
    return m.group(1) if m else None


def write_synthetic_wav(path: Path, *, seconds: float = 12.0, rate: int = 16000) -> Path:
    """A small PCM16 mono WAV with actual signal, not silence.

    Silence makes STT return nothing, which starves every downstream stage for a
    reason that has nothing to do with the code being exercised. A couple of
    tones at speech-ish frequencies at least produce audio features.
    """
    import math

    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(seconds * rate)
    frames = bytearray()
    for i in range(n):
        t = i / rate
        # Two alternating tones so energy/segmentation has something to chew on.
        freq = 180.0 if (int(t) % 2 == 0) else 240.0
        env = 0.0 if (int(t * 2) % 7 == 6) else 1.0  # periodic gaps
        val = int(9000 * env * math.sin(2 * math.pi * freq * t))
        frames += struct.pack("<h", max(-32768, min(32767, val)))
    data = bytes(frames)
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    hdr += b"data" + struct.pack("<I", len(data))
    path.write_bytes(hdr + data)
    return path


def refresh_id_hints(ctx: Any, hints_path: Path) -> None:
    """Publish the run's real segment / speaker ids for the stub to reuse."""
    seg: list[str] = []
    spk: list[str] = []
    try:
        if ctx.artifact_exists("segments/manifest.json"):
            man = ctx.read_json("segments/manifest.json")
            seg = [
                str(s.get("segment_id"))
                for s in (man.get("segments") or [])
                if isinstance(s, dict) and s.get("segment_id")
            ]
    except Exception:
        pass
    try:
        if ctx.artifact_exists("understanding/speakers.json"):
            doc = ctx.read_json("understanding/speakers.json")
            spk = [
                str(s.get("speaker_id"))
                for s in (doc.get("speakers") or [])
                if isinstance(s, dict) and s.get("speaker_id")
            ]
    except Exception:
        pass
    hints_path.parent.mkdir(parents=True, exist_ok=True)
    hints_path.write_text(
        json.dumps({"segment_ids": seg, "speaker_ids": spk}), encoding="utf-8"
    )
    # The stub caches on first use; drop it so later stages see fresh ids.
    try:
        from interview_mux import stub_llm

        stub_llm._HINTS._loaded = False
        stub_llm._HINTS.segment_ids = seg
        stub_llm._HINTS.speaker_ids = spk
    except Exception:
        pass


def clear_operator_gates(ctx: Any) -> list[str]:
    """Sign off the human-in-the-loop gates, the way an operator would.

    These gates exist for judgement a person has to supply (listen to the tape,
    correct the transcript). A keyless traversal is testing code paths, not
    judgement, so it signs them off through the real sign-off functions rather
    than forging .stage_done markers, so their side effects still run.
    """
    cleared: list[str] = []

    def _try(label: str, fn) -> None:
        try:
            if fn():
                cleared.append(label)
        except Exception as exc:  # noqa: BLE001 - diagnostic tool
            cleared.append(f"{label}:FAILED({type(exc).__name__}: {str(exc)[:120]})")

    # G0: transcript review.
    def _g0() -> bool:
        from interview_mux.gates import check_transcript_review_pending
        from interview_mux.stages.transcript_review import mark_transcript_review_complete

        if check_transcript_review_pending(ctx) and ctx.artifact_exists(
            "transcript/review_queue.json"
        ):
            mark_transcript_review_complete(ctx)
            return True
        return False

    _try("transcript_review", _g0)

    # G-Framing: operator chooses whether to fill gaps with synthetic framing.
    def _gap_decision() -> bool:
        from interview_mux.gap_vo_gates import (
            check_gap_framing_decision_pending,
            set_gap_framing_enabled,
        )

        if check_gap_framing_decision_pending(ctx):
            # Enable, so the gap/VO path is exercised rather than skipped.
            set_gap_framing_enabled(ctx, True)
            return True
        return False

    _try("gap_framing_decision", _gap_decision)

    # Gap VO delivery: synthesize rather than wait for a human recording.
    def _gap_delivery() -> bool:
        from interview_mux.gap_vo_gates import check_gap_delivery_pending, set_gap_vo_delivery

        if check_gap_delivery_pending(ctx):
            set_gap_vo_delivery(ctx, "chatterbox")
            return True
        return False

    _try("gap_vo_delivery", _gap_delivery)

    # Voice reference: operator approves the interviewer sample used for cloning.
    def _voice_ref() -> bool:
        from interview_mux.gap_vo_gates import (
            check_voice_reference_pending,
            mark_voice_reference_approved,
        )
        from interview_mux.source_topology import pickup_eligible_speaker_id

        if not check_voice_reference_pending(ctx):
            return False
        sid = pickup_eligible_speaker_id(ctx)
        if not sid:
            return False
        # The GUI builds the sample clips as part of showing them for approval,
        # so nothing else does. Without this the gate is unsatisfiable: it asks
        # for an approved reference WAV that was never extracted, and reports
        # "approved reference WAV missing or too short". full_auto_driver does
        # the same thing before approving (see its ensure_speaker_sample_clips
        # call), so this mirrors the real automated path.
        from interview_mux.source_topology import ensure_speaker_sample_clips

        ensure_speaker_sample_clips(ctx)
        mark_voice_reference_approved(ctx, sid)
        return True

    _try("voice_reference", _voice_ref)

    # Clone consent: explicit consent to synthesize that speaker's voice.
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
            # VALID_SCOPES is bridges / cold_open / outro; grant all so the
            # traversal is not blocked by a scope it happens not to have.
            scopes=["bridges", "cold_open", "outro"],
            granted_by="stub_pipeline_smoke",
            disclosure="none",
        )
        return True

    _try("clone_consent", _clone_consent)

    def _optimizer() -> bool:
        # master_finalize waits for "Take best or Skip" while the timeline
        # optimizer daemon is running. An unattended run answers Skip: the
        # daemon's own promote either happened already or was refused.
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
            # Record the Skip anyway when a daemon ran and nobody took its
            # best, so finalize does not treat that candidate as owed.
            if not (state.get("status") == "running" and not state.get("operator_took_best")):
                return False
        clear_timeline_optimizer_gate(ctx, skipped=True)
        return True

    _try("timeline_optimizer", _optimizer)

    return cleared


def main() -> int:
    _default_stub_env()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_stage", default=None)
    ap.add_argument("--until", dest="until_stage", default=None)
    ap.add_argument("--run-id", default=None, help="reuse an existing run")
    ap.add_argument("--keep", action="store_true", help="keep the run directory")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument(
        "--stop-on-fail", action="store_true", help="halt at the first failing stage"
    )
    ap.add_argument("--audio-seconds", type=float, default=12.0)
    ap.add_argument(
        "--orchestrated",
        action="store_true",
        help=(
            "Drive run_analysis/run_delivery, the real entry points, instead of "
            "forcing all 72 stages in order. The orchestrator skips stages "
            "conditionally (may_skip_as_complete) and runs nested stages, so the "
            "linear walk reports failures a real execution never sees. Use this "
            "to answer 'does an execution work', and the linear walk to answer "
            "'does this individual stage work'."
        ),
    )
    ap.add_argument(
        "--resume-from-run",
        default=None,
        help="Copy an existing run and continue in the copy, so completed stages "
        "are not redone (and their API cost is not paid twice).",
    )
    ap.add_argument(
        "--audio",
        default=None,
        help=(
            "WAV of real speech. The synthetic default is tones, which STT "
            "transcribes to nothing, so stages past speaker_roles starve. Point "
            "this at real audio to exercise the rest."
        ),
    )
    args = ap.parse_args()

    from interview_mux.pipeline import run_single_stage
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS as ARTIFACT_OF
    from interview_mux.run_context import RunContext
    from interview_mux.v2.config import effective_analysis_order, effective_delivery_order

    stages = [("analysis", s) for s in effective_analysis_order()]
    stages += [("delivery", s) for s in effective_delivery_order()]
    names = [s for _, s in stages]

    start = 0
    if args.from_stage:
        if args.from_stage not in names:
            print(f"unknown --from stage: {args.from_stage}", file=sys.stderr)
            return 2
        start = names.index(args.from_stage)
    end = len(stages)
    if args.until_stage:
        if args.until_stage not in names:
            print(f"unknown --until stage: {args.until_stage}", file=sys.stderr)
            return 2
        end = names.index(args.until_stage) + 1

    from interview_mux.config import repo_root

    # ctx.input_audio() reads run_meta.json, so the source has to be registered
    # there exactly as cli.py does it. Keep a distinct filename so a real
    # ASSETS/input/interview.wav is never touched.
    #
    # Resuming an existing run must NOT re-register a source. Writing a fresh
    # tone here silently repointed a resumed run at 12 seconds of sine wave, so
    # every speaker sample became "too short for clone" and the later stages
    # were judging a tone instead of the interview.
    audio: Path | None = None
    resuming_in_place = bool(args.run_id) and not args.audio
    if args.audio:
        src = Path(args.audio).expanduser().resolve()
        if not src.is_file():
            print(f"--audio not found: {src}", file=sys.stderr)
            return 2
        input_dir = repo_root() / "ASSETS" / "input"
        if src.parent == input_dir:
            # Already where the pipeline looks. Use it in place: copying to a
            # stub_smoke_ name would duplicate the file and force a second
            # conversion, which for an hour of audio is another 600 MB of WAV.
            audio = src
        else:
            audio = input_dir / f"stub_smoke_{src.stem}{src.suffix}"
            audio.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, audio)
    elif not resuming_in_place:
        audio = repo_root() / "ASSETS" / "input" / "stub_smoke_tone.wav"
        write_synthetic_wav(audio, seconds=args.audio_seconds)

    if args.resume_from_run:
        src_ctx = RunContext(args.resume_from_run, create=False)
        ctx = RunContext(create=True)
        src_dir, dst_dir = Path(src_ctx.run_dir), Path(ctx.run_dir)
        for item in src_dir.iterdir():
            target = dst_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
        print(f"resumed from {args.resume_from_run} into {ctx.run_id}")
    elif args.run_id:
        ctx = RunContext(args.run_id, create=False)
    else:
        ctx = RunContext(create=True)
    os.environ["MUX_RUN_ID"] = ctx.run_id

    if audio is None:
        # Resume in place: keep the source the run was created with.
        try:
            audio = Path(ctx.input_audio())
        except Exception:
            audio = None
        if audio is not None:
            os.environ["MUX_INPUT_AUDIO"] = str(audio)
        print("resuming with the run's existing source audio")
    else:
        os.environ["MUX_INPUT_AUDIO"] = str(audio)
        rel = audio.relative_to(repo_root()).as_posix()
        try:
            from interview_mux.source_audio_hash import source_audio_hash_pair

            full_hash, short_hash = source_audio_hash_pair(audio)
        except Exception:
            full_hash = short_hash = None
        ctx.init_run_meta(
            rel, source_audio_hash=full_hash, source_audio_hash_short=short_hash
        )
    if not resuming_in_place:
        try:
            from interview_mux.homunculus.version import stamp_run_meta

            stamp_run_meta(ctx)
        except Exception:
            pass

    # Let the stub keep its generated time windows inside the real tape.
    try:
        if audio is None:
            raise RuntimeError("no audio handle to probe")
        import wave

        from interview_mux.source_audio_hash import pipeline_wav_path

        # mp3/m4a have no wave header; hash/probe the canonical pipeline WAV.
        probe_target = pipeline_wav_path(audio) if audio.suffix.lower() != ".wav" else audio

        with wave.open(str(probe_target), "rb") as wf:
            frames, rate = wf.getnframes(), wf.getframerate()
        # Cross-check against file size: a header can declare a bogus frame count
        # (the classic 0xFFFFFFFF streamed-WAV placeholder), and a wrong duration
        # here would push every generated timestamp off the end of the tape.
        declared_ms = int(frames / float(rate or 1) * 1000) if rate else 0
        actual_ms = int(
            (probe_target.stat().st_size - 44) / max(1, (rate or 1) * wf.getsampwidth() * wf.getnchannels()) * 1000
        )
        dur_ms = declared_ms if 0 < declared_ms <= actual_ms * 2 + 1000 else actual_ms
        os.environ["MUX_STUB_AUDIO_MS"] = str(max(20000, dur_ms))
        print(f"tape   : {dur_ms / 1000:.1f}s (stub time windows bounded to this)")
    except Exception:
        pass

    hints = Path(ctx.run_dir) / "stub_id_hints.json"
    os.environ["MUX_STUB_LLM_HINTS"] = str(hints)
    refresh_id_hints(ctx, hints)

    print(f"run_id : {ctx.run_id}")
    print(f"run_dir: {ctx.run_dir}")
    print(f"audio  : {audio.name if audio else '(existing run source)'}")
    from interview_mux.stub_llm import stub_enabled

    print(f"stages : {end - start} of {len(stages)}  {'(stub LLM, no API key)' if stub_enabled() else '(real LLM, API key)'}")
    print("-" * 78)

    if args.orchestrated:
        from interview_mux.pipeline import run_analysis, run_delivery
        from interview_mux.v2.config import ANALYSIS_ORDER

        hops = 0

        summary: list[dict[str, Any]] = []
        for phase, fn in (("analysis", run_analysis), ("delivery", run_delivery)):
            t0 = time.perf_counter()
            row: dict[str, Any] = {"phase": phase}
            try:
                fn(ctx)
                row["status"] = "ok"
            except SystemExit as exc:
                row["status"] = "halt"
                row["error"] = f"SystemExit: {str(exc)[:500]}"
            except BaseException as exc:  # noqa: BLE001 - diagnostic tool
                row["status"] = "fail"
                row["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
                row["traceback"] = traceback.format_exc()[-2500:]
            row["seconds"] = round(time.perf_counter() - t0, 2)
            print(f"{phase:9} {row['status'].upper():5} {row['seconds']:8.1f}s")
            if row.get("error"):
                print(f"      {row['error'][:300]}")

            # An operator gate halting the phase is the gate doing its job. Sign
            # it off and re-enter, which is what an operator does; otherwise the
            # first gate always looks like a failed execution.
            gates = clear_operator_gates(ctx)
            for name in gates:
                print(f"      gate cleared: {name}")
            attempts = 0
            # Resuming is only worth it while the error keeps changing. Four
            # resumes against an identical message cost about 16 minutes and
            # taught nothing, because signing the gates again cannot fix a
            # failure that is not about the gates.
            last_error: str | None = None
            direct_dispatched: set[str] = set()

            def _done_count() -> int:
                dd = Path(ctx.run_dir) / ".stage_done"
                return len(list(dd.glob("*"))) if dd.is_dir() else 0

            # A pass can fail and still have moved the run forward: the recovery
            # path heals after a stage raises (seed, mark), so the next pass
            # skips straight through. Retry on progress, not only on gates, so
            # a run is not abandoned one pass short with the fix already landed.
            progressed = _done_count()
            before_done = progressed
            while (
                (gates or progressed > 0)
                and row["status"] != "ok"
                and attempts < MAX_GATE_RESUMES
            ):
                attempts += 1
                t1 = time.perf_counter()
                try:
                    fn(ctx)
                    row["status"] = "ok"
                    row.pop("error", None)
                    row.pop("traceback", None)
                except SystemExit as exc:
                    row["status"] = "halt"
                    row["error"] = f"SystemExit: {str(exc)[:500]}"
                except BaseException as exc:  # noqa: BLE001
                    row["status"] = "fail"
                    row["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
                    row["traceback"] = traceback.format_exc()[-2500:]
                row["seconds"] = round(row["seconds"] + time.perf_counter() - t1, 2)
                row["gate_resumes"] = attempts
                print(f"  resume {attempts}: {phase} -> {row['status'].upper()}"
                      f" ({row['seconds']:.1f}s total)")
                if row.get("error"):
                    print(f"      {row['error'][:300]}")
                current_error = str(row.get("error") or "")
                now_done = _done_count()
                progressed = now_done - (progressed if attempts == 1 else before_done)
                before_done = now_done
                if current_error and progressed <= 0:
                    # A pass that failed without moving anything, naming its own
                    # remedy: dispatch that stage once, directly, then let the
                    # phase try again. This must run before the loop guard sees
                    # "no progress, no gates" and gives up, which is exactly how
                    # the hands-off 6-minute run stopped at 53 of 72.
                    hint = resume_hint(current_error)
                    if hint and hint not in direct_dispatched:
                        from interview_mux.pipeline import run_single_stage

                        # Follow a short remedy chain: a dispatched stage may
                        # refuse and name another stage to run first (exec_052:
                        # mix -> "recut ... at junction_snip_qa first").
                        for _hop in range(3):
                            if not hint or hint in direct_dispatched:
                                break
                            direct_dispatched.add(hint)
                            print(f"      dispatching {hint} directly (named as resume, walk did not run it)")
                            try:
                                run_single_stage(ctx, hint)
                                landed = bool(ctx.is_done(hint))
                                print(f"      {hint} -> done={landed}")
                                if landed:
                                    progressed = 1  # keep the loop alive for one more pass
                                break
                            except BaseException as exc:  # noqa: BLE001
                                print(f"      {hint} direct dispatch failed: {type(exc).__name__}: {str(exc)[:200]}")
                                hint = resume_hint(str(exc))
                        last_error = None
                        gates = clear_operator_gates(ctx)
                        continue
                    if current_error == last_error:
                        print("      same error as the previous resume and no progress, stopping early")
                        break
                if progressed > 0:
                    print(f"      progress: {progressed} more stage(s) marked complete, retrying")
                last_error = current_error
                gates = clear_operator_gates(ctx)
                for name in gates:
                    print(f"      gate cleared: {name}")

            summary.append(row)
            if row["status"] != "ok":
                # Delivery can invalidate an analysis stage: chapter_close_hitch
                # re-runs missing_framing, the evaluations change, and the
                # homunculus correctly clears gap_framing_compose's marker. The
                # product then says "analysis incomplete" and waits for someone
                # to run analysis again. Full-auto loops; this driver resumed
                # only the current phase, so it stopped one hop short. Hop back
                # to analysis (which skips everything still complete) and retry
                # delivery, bounded like the gate resumes.
                err = str(row.get("error") or "")
                hop_back = phase == "delivery" and (
                    "analysis incomplete" in err
                    or ("seed order: complete " in err and any(
                        f"complete {s} " in err for s in ANALYSIS_ORDER
                    ))
                )
                if hop_back and hops < MAX_GATE_RESUMES:
                    hops += 1
                    print(f"  hop {hops}: delivery invalidated analysis, re-running analysis then delivery")
                    for hop_phase, hop_fn in (("analysis", run_analysis), ("delivery", run_delivery)):
                        t2 = time.perf_counter()
                        hop_row = {"phase": hop_phase, "status": "ok", "seconds": 0.0, "hop": hops}
                        try:
                            hop_fn(ctx)
                        except SystemExit as exc:
                            hop_row["status"] = "halt"; hop_row["error"] = f"SystemExit: {str(exc)[:500]}"
                        except BaseException as exc:  # noqa: BLE001
                            hop_row["status"] = "fail"; hop_row["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
                            hop_row["traceback"] = traceback.format_exc()[-2500:]
                        hop_row["seconds"] = round(time.perf_counter() - t2, 2)
                        print(f"  hop {hops}: {hop_phase} -> {hop_row['status'].upper()} ({hop_row['seconds']:.1f}s)")
                        if hop_row.get("error"):
                            print(f"      {hop_row['error'][:300]}")
                        summary.append(hop_row)
                        if hop_row["status"] != "ok":
                            break
                    if summary[-1]["status"] == "ok" and summary[-1]["phase"] == "delivery":
                        row = summary[-1]
                        continue
                break

        done_dir = Path(ctx.run_dir) / ".stage_done"
        marked = sorted(p.name for p in done_dir.iterdir()) if done_dir.is_dir() else []
        print("-" * 78)
        print(f"stages marked complete: {len(marked)}")
        print("  " + ", ".join(marked))
        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(
                    {"run_id": ctx.run_id, "mode": "orchestrated",
                     "phases": summary, "marked": marked},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"report: {args.json_out}")
        return 0 if all(r["status"] == "ok" for r in summary) else 1

    results: list[dict[str, Any]] = []
    for idx in range(start, end):
        phase, stage = stages[idx]
        n = idx + 1
        t0 = time.perf_counter()
        row: dict[str, Any] = {"n": n, "phase": phase, "stage": stage}
        try:
            run_single_stage(ctx, stage)
            row["status"] = "ok"
        except SystemExit as exc:
            row["status"] = "halt"
            row["error"] = f"SystemExit: {str(exc)[:400]}"
        except BaseException as exc:  # noqa: BLE001 - diagnostic tool
            row["status"] = "fail"
            row["error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
            row["traceback"] = traceback.format_exc()[-1800:]
        row["seconds"] = round(time.perf_counter() - t0, 2)

        # A stage that returns without error but writes nothing has not been
        # exercised, and reporting it as "ok" would be false confidence. Record
        # whether its primary artifact now exists.
        want = ARTIFACT_OF.get(stage)
        row["artifact"] = want
        if want:
            try:
                row["artifact_present"] = bool(ctx.artifact_exists(want))
            except Exception:
                row["artifact_present"] = False
            if row["status"] == "ok" and not row["artifact_present"]:
                row["status"] = "noop"
        results.append(row)

        mark = {"ok": "ok  ", "fail": "FAIL", "halt": "HALT", "noop": "NOOP"}[row["status"]]
        print(f"{n:3} {mark} {phase:8} {stage:34} {row['seconds']:7.2f}s")
        if row["status"] == "noop":
            print(f"      returned cleanly but did not write {want}")
        elif row["status"] != "ok":
            print(f"      {row.get('error')}")
        # Operator gates block the rest of the walk; sign them off as they open.
        gates = clear_operator_gates(ctx)
        for name in gates:
            print(f"      gate cleared: {name}")
            row.setdefault("gates_cleared", []).append(name)
        # A stage that halted *on* a gate is meant to halt: raising is how it
        # tells the operator to act. Having just acted, re-run it once, which is
        # what an operator does after signing off.
        if gates and row["status"] in {"halt", "fail", "noop"}:
            t1 = time.perf_counter()
            try:
                run_single_stage(ctx, stage)
                row["status"] = "ok"
                row["retried_after_gate"] = True
                row.pop("error", None)
                row.pop("traceback", None)
            except BaseException as exc:  # noqa: BLE001
                row["status"] = "fail"
                row["error"] = f"after gate clear: {type(exc).__name__}: {str(exc)[:400]}"
            row["seconds"] = round(row["seconds"] + time.perf_counter() - t1, 2)
            want_retry = ARTIFACT_OF.get(stage)
            if row["status"] == "ok" and want_retry:
                try:
                    if not ctx.artifact_exists(want_retry):
                        row["status"] = "noop"
                except Exception:
                    pass
            mark2 = {"ok": "ok  ", "fail": "FAIL", "noop": "NOOP"}.get(row["status"], "????")
            print(f"    -> retry after gate: {mark2} {stage}")
        # Ids appear as stages land; keep the stub's refs pointing at real ones.
        refresh_id_hints(ctx, hints)

        if row["status"] != "ok" and args.stop_on_fail:
            print("\nstopping at first failure (--stop-on-fail)")
            break

    ok = sum(1 for r in results if r["status"] == "ok")
    noop = [r for r in results if r["status"] == "noop"]
    failed = [r for r in results if r["status"] in {"fail", "halt"}]
    print("-" * 78)
    print(f"wrote artifacts {ok}/{len(results)}   no-op {len(noop)}   failed {len(failed)}")
    if noop:
        print("no-op (clean return, no artifact): " + ", ".join(r["stage"] for r in noop))
    if failed:
        print(f"first failure: #{failed[0]['n']} {failed[0]['stage']}")
        print("failing stages: " + ", ".join(f"#{r['n']} {r['stage']}" for r in failed))

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {"run_id": ctx.run_id, "passed": ok, "total": len(results), "stages": results},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"report: {args.json_out}")

    if not args.keep and not args.run_id:
        shutil.rmtree(Path(ctx.run_dir), ignore_errors=True)
        print(f"removed {ctx.run_id} (pass --keep to inspect artifacts)")

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
