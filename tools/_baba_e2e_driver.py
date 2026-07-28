#!/usr/bin/env python3
"""Fresh baba_all_vocals E2E driver — mirrors current v2 ANALYSIS/DELIVERY orders.

Resumes exec_1123 (or RUN_ID env) through operator gates until master/master.wav.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Current pipeline orders (keep in sync with interview_mux.v2.config)
ANALYSIS_ORDER = (
    "audio_preclean",
    "ingest",
    "transcribe",
    "transcript_review_build",
    "source_acoustic_profile",
    "interview_spine_build",
    "speaker_roles",
    "source_topology_build",
    "content_context",
    "boundary_detection",
    "segment_classification",
    "content_brief_reanchor",
    "boundary_topic_resplit",
    "sonic_context_build",
    "sound_design_palettes",
    "mastering_research_routing",
    "mastering_research_waves",
    "mastering_research_rollup",
    "mastering_shape_agenda",
    "mastering_shape_candidates",
    "mastering_plan_synthesize",
    "missing_framing",
    "mastering_plan_confirm",
    "gap_framing_compose",
    "delivery_brief_build",
    "soundscape_policy_build",
    "episode_structure_compose",
)
DELIVERY_ORDER = (
    "topic_coverage_audit",
    "narrative_arc_plan",
    "full_master_ranking",
    "refinement_agenda",
    "gap_framing_recompose",
    "selection_framing_apply",
    "ranking_refine",
    "narrative_arc_refine",
    "transitions",
    "transitions_refine",
    "sound_design_plan",
    "sdp_intent_refine",
    "sound_design_vo_finalize",
    "edl_narrative_audit",
    "edl_narrative_refine",
    "edl",
    "assembly_preview",
    "listen_delight_audit",
    "sfx_prompt_craft",
    "mmaudio_sfx",
    "mix",
    "master_finalize",
)
PREPARE_STAGES = ("ingest", "transcribe", "transcript_review_build")

BASE = os.environ.get("MUX_BASE", "http://127.0.0.1:8765")
RUN_ID = os.environ.get("MUX_RUN_ID", "exec_1123_1311e28fffa1_20260727T200034Z")
POLL_SEC = int(os.environ.get("MUX_POLL_SEC", "20"))
MAX_WAIT_SEC = int(os.environ.get("MUX_MAX_WAIT_SEC", str(60 * 60 * 12)))
REPO = Path(__file__).resolve().parents[1]
MASTER = REPO / "ASSETS" / "executions" / RUN_ID / "master" / "master.wav"
LOG = REPO / "ASSETS" / "executions" / RUN_ID / "operator_e2e.log"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def api(method: str, path: str, body: dict[str, Any] | None = None, timeout: int = 180) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode()
    last_exc: Exception | None = None
    for attempt in range(5):
        req = urllib.request.Request(
            BASE + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()
            try:
                payload = json.loads(detail)
            except json.JSONDecodeError:
                payload = {"detail": detail}
            raise RuntimeError(f"{method} {path} -> {exc.code}: {payload}") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
            last_exc = exc
            log(f"api retry {attempt + 1}/5 {method} {path}: {exc}")
            time.sleep(2 + attempt * 2)
            continue
    raise RuntimeError(f"{method} {path} failed after retries: {last_exc}")


def grant_consent() -> None:
    for provider in ("local", "openai"):
        try:
            api("POST", "/api/session/api-consent", {"provider": provider, "granted": True})
        except RuntimeError as exc:
            log(f"consent {provider}: {exc}")


def stage_statuses() -> dict[str, str]:
    run = api("GET", f"/api/runs/{RUN_ID}", timeout=300)
    return {s["id"]: str(s.get("status") or "pending") for s in run.get("stages", [])}


def milestones() -> dict[str, Any]:
    run = api("GET", f"/api/runs/{RUN_ID}", timeout=300)
    return (run.get("meta") or {}).get("journey_milestones") or {}


def g0_complete() -> bool:
    st = stage_statuses()
    if st.get("transcript_review") == "done":
        return True
    return bool(milestones().get("g0_complete"))


def progress() -> str:
    st = stage_statuses()
    done = sum(1 for v in st.values() if v == "done")
    return f"{done}/{len(st)} done; master={'yes' if MASTER.is_file() else 'no'}"


def master_ready() -> bool:
    return MASTER.is_file() and MASTER.stat().st_size > 1000


def wait_job(label: str = "") -> dict[str, Any]:
    deadline = time.time() + MAX_WAIT_SEC
    last = ""
    while time.time() < deadline:
        if master_ready():
            return {"status": "complete", "message": "master.wav present"}
        job = api("GET", f"/api/runs/{RUN_ID}/job")
        status = job.get("status") or "idle"
        msg = str(job.get("message") or "")
        stage = job.get("current_stage") or job.get("stage") or ""
        key = f"{status}|{stage}|{msg[:80]}"
        if key != last:
            log(f"[{label}] {status} {stage}: {msg[:160]} | {progress()}")
            last = key
        if status in {"complete", "error", "gate", "needs_operator", "interrupted", "idle", "stalled"}:
            if status == "idle":
                time.sleep(3)
                job2 = api("GET", f"/api/runs/{RUN_ID}/job")
                if (job2.get("status") or "idle") not in {"idle", "complete"}:
                    continue
                return job2
            return job
        time.sleep(POLL_SEC)
    raise TimeoutError(f"Timed out ({label})")


def execute(body: dict[str, Any]) -> None:
    body = {**body, "api_consents": {"local": True, "openai": True}}
    for attempt in range(8):
        try:
            api("POST", f"/api/runs/{RUN_ID}/execute", body)
            return
        except RuntimeError as exc:
            text = str(exc).lower()
            if "409" in str(exc) or "busy" in text or "already" in text:
                log(f"execute busy (attempt {attempt + 1}): waiting")
                time.sleep(20 + attempt * 5)
                job = api("GET", f"/api/runs/{RUN_ID}/job")
                if (job.get("status") or "") == "running":
                    log("worker already running — joining")
                    return
                continue
            raise
    log("execute still busy after retries — joining existing job")


def dismiss_preclean() -> None:
    try:
        api(
            "POST",
            f"/api/runs/{RUN_ID}/preclean-offer",
            {"checkpoint": "before_ingest", "action": "dismiss", "scope": "full_source"},
        )
        log("preclean dismissed")
    except RuntimeError as exc:
        log(f"preclean note: {exc}")


def complete_g0() -> None:
    try:
        api("POST", f"/api/runs/{RUN_ID}/transcript-review/complete", {"accept_unreviewed": True})
        log("G0 accepted")
    except RuntimeError as exc:
        log(f"G0 note: {exc}")


def accept_gap_framing_defaults() -> None:
    try:
        gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
    except RuntimeError as exc:
        log(f"gap-framing get: {exc}")
        return
    if gate.get("gap_framing_decision_pending"):
        api("POST", f"/api/runs/{RUN_ID}/gap-framing/enable", {"enabled": True})
        log("gap framing enabled")
    # Operator chose framing — force gap-fill active so auto-skip cannot no-op compose.
    try:
        from interview_mux.run_context import RunContext
        from interview_mux.gap_fill_eligibility import clear_gap_fill_skip

        ctx = RunContext(RUN_ID, create=False)
        if clear_gap_fill_skip:
            clear_gap_fill_skip(ctx, reason="baba_e2e_gap_framing_enabled")

        def patch(meta: dict[str, Any]) -> None:
            meta["gap_fill_mode"] = "active"
            meta["gap_framing_enabled"] = True
            meta.pop("gap_fill_skip_reason", None)

        ctx.mutate_run_meta(patch)
        log("gap_fill_mode forced active")
    except Exception as exc:
        log(f"force gap_fill active: {exc}")
    try:
        pickup = api("GET", f"/api/runs/{RUN_ID}/pickup-speaker")
    except RuntimeError as exc:
        log(f"pickup get: {exc}")
        pickup = {}
    if pickup.get("pending") or not pickup.get("pickup_speaker_confirmed"):
        sid = pickup.get("pickup_eligible_speaker_id") or pickup.get("least_spoken_speaker_id")
        body = {"pickup_eligible_speaker_id": sid} if sid else {}
        try:
            api("POST", f"/api/runs/{RUN_ID}/pickup-speaker/confirm", body)
            log(f"pickup speaker: {sid}")
        except RuntimeError as exc:
            log(f"pickup confirm: {exc}")
    gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
    if gate.get("voice_reference_pending"):
        try:
            api("POST", f"/api/runs/{RUN_ID}/voice-reference/approve")
            log("voice reference approved")
        except RuntimeError as exc:
            log(f"voice ref: {exc}")
    gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
    if gate.get("gap_delivery_pending") or not gate.get("gap_vo_delivery"):
        try:
            api("POST", f"/api/runs/{RUN_ID}/gap-framing/delivery", {"delivery": "chatterbox"})
            log("delivery chatterbox")
        except RuntimeError as exc:
            log(f"delivery: {exc}")
    gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
    if gate.get("clone_consent_pending") or gate.get("clone_consent_required"):
        sid = gate.get("pickup_eligible_speaker_id")
        try:
            api(
                "POST",
                f"/api/runs/{RUN_ID}/voice-clone-consent",
                {
                    "speaker_id": sid,
                    "scopes": ["cold_open", "bridges", "outro"],
                    "disclosure": "none",
                    "granted_by": "baba_e2e_driver",
                },
            )
            log("clone consent granted")
        except RuntimeError as exc:
            log(f"clone consent: {exc}")


def skip_g1() -> None:
    try:
        api("POST", f"/api/runs/{RUN_ID}/g1/skip-optional", {"force": True})
        log("G1 skipped")
    except RuntimeError as exc:
        log(f"G1 skip: {exc}")


def synthesize_g1() -> bool:
    try:
        result = api("POST", f"/api/runs/{RUN_ID}/g1/synthesize-all", {}, timeout=600)
        log(f"G1 synth: {result}")
        return bool(result.get("ok", True)) and not (result.get("errors") or [])
    except RuntimeError as exc:
        log(f"G1 synth: {exc}")
        return False


def approve_sfx_prompts() -> None:
    try:
        result = api("POST", f"/api/runs/{RUN_ID}/sfx-prompts/approve", {})
        log(f"sfx-prompts approve: {result}")
    except Exception as exc:
        log(f"sfx-prompts approve: {exc}")


def decline_reuse(stage_id: str) -> None:
    api("POST", f"/api/runs/{RUN_ID}/stages/{stage_id}/reuse", {"action": "decline"})
    log(f"declined reuse {stage_id}")


def auto_pass_post_listen() -> None:
    try:
        sfx = api("GET", f"/api/runs/{RUN_ID}/sfx-prompts")
    except RuntimeError:
        return
    asset_ids: set[str] = set()
    for row in (sfx.get("prompts") or []) + (sfx.get("assets") or []):
        if isinstance(row, dict) and row.get("asset_id"):
            asset_ids.add(str(row["asset_id"]))
    for aid in sorted(asset_ids):
        api(
            "POST",
            f"/api/runs/{RUN_ID}/sfx-prompts/listen-result",
            {"asset_id": aid, "result": "pass", "note": "baba e2e auto-pass"},
        )
    if asset_ids:
        log(f"post-listen passed {len(asset_ids)}")


def parse_failed_stage(job: dict[str, Any]) -> str:
    stage = str(job.get("stage") or job.get("current_stage") or "")
    err_obj = job.get("last_error") if isinstance(job.get("last_error"), dict) else {}
    err = str(
        (err_obj or {}).get("message")
        or job.get("error")
        or job.get("message")
        or ""
    )
    low = err.lower()
    # Prefer artifact/path hints over a stale from_stage left on the job object.
    if "gap_report.json" in low or "gap_framing_compose" in low:
        return "gap_framing_compose"
    if "gap_evaluations.json" in low or "missing_framing" in low:
        return "missing_framing"
    if "manifest.json" in low and "segment_classification" in low:
        return "segment_classification"
    if "LLM stage " in err:
        try:
            parsed = err.split("LLM stage ", 1)[1].split(" ", 1)[0].strip(":")
            if parsed:
                return parsed
        except IndexError:
            pass
    err_stage = str((err_obj or {}).get("stage") or "")
    if err_stage and err_stage != "None":
        return err_stage
    if stage and stage != "None":
        return stage
    return ""


def heal_stage_done_markers() -> None:
    """Restore .stage_done when producer artifacts are complete but markers were cleared."""
    try:
        from interview_mux.run_context import RunContext
        from interview_mux.stage_completion import stage_artifact_incompleteness
    except Exception as exc:
        log(f"heal import: {exc}")
        return
    ctx = RunContext(RUN_ID, create=False)
    healed: list[str] = []
    for sid in (*ANALYSIS_ORDER, *DELIVERY_ORDER):
        if ctx.is_done(sid):
            continue
        reason = stage_artifact_incompleteness(ctx, sid)
        if reason:
            continue
        # Only heal stages that declare a required artifact path (avoid false dones).
        from interview_mux.stage_completion import stage_required_artifact_paths

        if not stage_required_artifact_paths(sid):
            continue
        try:
            ctx.mark_done(sid, force=True)
            healed.append(sid)
        except Exception as exc:
            log(f"heal {sid}: {exc}")
    if healed:
        log(f"healed stage_done: {', '.join(healed)}")


def handle_gate(job: dict[str, Any], body: dict[str, Any]) -> str:
    """Return 'continue' | 'advance' | 'stuck'."""
    status = job.get("status")
    stage = str(job.get("stage") or job.get("current_stage") or "")
    msg = str(job.get("message") or "")
    low = msg.lower()

    if job.get("needs_stage_reuse") and stage:
        decline_reuse(stage)
        execute(body)
        return "continue"

    if "prerequisite" in low and ("incomplete" in low or "not complete" in low or "fill gaps" in low):
        import re

        # Incomplete artifact → fill-gaps when path present, else resume from named stage.
        path_m = re.search(r"artifact\s+([a-z0-9_./-]+\.json)", low)
        stage_m = re.search(r"(?:from stage|prerequisite stage)\s+([a-z0-9_]+)", low)
        if path_m:
            rel = path_m.group(1)
            log(f"fill gaps for {rel}")
            try:
                api(
                    "POST",
                    f"/api/runs/{RUN_ID}/fill-artifact-gaps",
                    {"path": rel, "api_consents": {"local": True, "openai": True}},
                    timeout=300,
                )
                return "continue"
            except RuntimeError as exc:
                log(f"fill-gaps: {exc}")
        if stage_m:
            need = stage_m.group(1)
            log(f"prerequisite incomplete: {need} — resuming from there")
            mode = "delivery" if "delivery" in str(body.get("mode") or "") else "analysis"
            execute({"mode": mode, "from_stage": need})
            return "advance"
        return "stuck"

    if "profile not operator-verified" in low or "coherence_report" in low or "mark verified" in low:
        try:
            api("POST", f"/api/runs/{RUN_ID}/analysis-profile/verify", {})
            log("analysis profile verified")
        except RuntimeError as exc:
            log(f"profile verify: {exc}")
        try:
            api("POST", f"/api/runs/{RUN_ID}/recompute-coherence", {"phase": "post_reanchor"}, timeout=300)
            log("coherence recomputed")
        except RuntimeError as exc:
            log(f"coherence: {exc}")
        execute(body)
        return "continue"

    if "narrative_qc strict" in low or "edl_narrative_qc strict" in low:
        try:
            from interview_mux.run_context import RunContext
            from interview_mux.artifact_repairs import repair_coverage_audit, repair_master_selection
            from interview_mux.artifact_writes import write_validated_artifact
            from interview_mux.narrative_qc import validate_flow1_narrative

            ctx = RunContext(RUN_ID, create=False)
            if ctx.artifact_exists("master/coverage_audit.json"):
                audit = ctx.read_json("master/coverage_audit.json")
                repaired, _ = repair_coverage_audit(ctx, audit)
                ctx.write_json("master/coverage_audit.json", repaired)
            if "edl_narrative_qc" in low and ctx.artifact_exists("master/selection.json"):
                sel = ctx.read_json("master/selection.json")
                repaired, notes = repair_master_selection(ctx, sel)
                write_validated_artifact(
                    ctx,
                    "master/selection.json",
                    repaired,
                    merge_from_disk=False,
                    stage_key="full_master_ranking",
                )
                log(f"selection chapter heal: {[n for n in notes if 'chapter' in str(n) or 'reorder' in str(n)][:3]}")
                # Drop transitions that no longer sit on adjacent ordered speech.
                if ctx.artifact_exists("master/transitions.json"):
                    order = [str(s) for s in (repaired.get("ordered_segment_ids") or []) if s]
                    pos = {sid: i for i, sid in enumerate(order)}
                    trans = ctx.read_json("master/transitions.json")
                    kept = []
                    for row in trans.get("transitions") or []:
                        if not isinstance(row, dict):
                            continue
                        a = str(row.get("after_segment_id") or "")
                        b = str(row.get("before_segment_id") or "")
                        if a in pos and b in pos and pos[b] == pos[a] + 1:
                            kept.append(row)
                    trans["transitions"] = kept
                    ctx.write_json("master/transitions.json", trans)
                    log(f"transitions pruned to {len(kept)} adjacent pair(s)")
            errs = validate_flow1_narrative(ctx)
            log(f"narrative_qc after repair: {errs[:3] or 'pass'}")
        except Exception as exc:
            log(f"narrative_qc repair: {exc}")
        execute(body)
        return "continue"

    if "prerequisite stage" in low:
        # e.g. "Prerequisite stage segment_classification is not complete..."
        import re

        m = re.search(r"prerequisite stage\s+([a-z0-9_]+)", low)
        if m:
            need = m.group(1)
            log(f"prerequisite missing: {need} — resuming from there")
            execute({"mode": "analysis" if "delivery" not in str(body.get("mode")) else "delivery", "from_stage": need})
            return "advance"
        return "stuck"

    if "transcript review" in low or stage in {"transcript_review", "transcript_review_build"}:
        complete_g0()
        # Never re-run analysis_until_g0 — that archives review_queue and rebuilds clips.
        if body.get("mode") == "analysis_until_g0":
            return "advance"
        execute(body)
        return "continue"

    if (
        stage
        in {
            "missing_framing",
            "gap_framing_compose",
            "optimal_questions",
            "source_topology_build",
            "mastering_plan_confirm",
        }
        or "gap framing" in low
        or "pickup speaker" in low
        or "voice reference" in low
        or "gap delivery" in low
        or "voice clone" in low
    ):
        accept_gap_framing_defaults()
        execute(body)
        return "continue"

    if stage == "g1_vo_pickup" or ("g1" in low and "vo" in low):
        if not synthesize_g1():
            # Never auto-skip when framing / voice-clone delivery is active —
            # that produced source-only masters (g1_vo_skipped_optional cascade).
            framing_active = False
            delivery = ""
            try:
                gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
                framing_active = bool(gate.get("gap_framing_enabled") or gate.get("enabled"))
                delivery = str(gate.get("gap_vo_delivery") or gate.get("delivery") or "").lower()
            except Exception:
                pass
            if framing_active or delivery in {"chatterbox", "voice_clone", "synthesize"}:
                log(
                    "HARD: G1 synthesize-all failed while framing/chatterbox active — "
                    "not auto-skipping (fix TTS / leave needs_operator)"
                )
                return "stuck"
            skip_g1()
        execute(body)
        return "continue"

    if (
        stage in {"sfx_prompt_craft", "mmaudio_sfx"}
        or "g1.5" in low
        or "prompt approval" in low
        or "sfx prompt" in low
        or "approve prompts" in low
    ):
        approve_sfx_prompts()
        execute(body)
        return "continue"

    if stage == "audio_preclean" or "pre-clean" in low or "preclean" in low:
        dismiss_preclean()
        execute(body)
        return "continue"

    if "post_listen" in low or "post-listen" in low:
        auto_pass_post_listen()
        execute(body)
        return "continue"

    if status == "needs_operator" and "api consent" in low:
        grant_consent()
        execute(body)
        return "continue"

    if "continue" in low or "preview" in low or "save" in low or "commit" in low:
        execute(body)
        return "continue"

    return "stuck"


def first_pending(ids: tuple[str, ...] | list[str]) -> str | None:
    st = stage_statuses()
    for sid in ids:
        # Skip stages not exposed on the run (hidden research/shape stages, etc.)
        if sid not in st:
            continue
        if st.get(sid) != "done":
            return sid
    return None


def build_bodies() -> list[tuple[str, dict[str, Any]]]:
    steps: list[tuple[str, dict[str, Any]]] = []
    if not g0_complete():
        prepare_from = first_pending(PREPARE_STAGES)
        if prepare_from:
            steps.append(("prepare", {"mode": "analysis_until_g0", "from_stage": prepare_from}))
    analysis_from = first_pending([s for s in ANALYSIS_ORDER if s not in PREPARE_STAGES and s != "audio_preclean"])
    # After G0, also skip transcript_review_build if somehow pending while g0 done
    if analysis_from and analysis_from != "transcript_review_build":
        steps.append(("analysis", {"mode": "analysis", "from_stage": analysis_from}))
    elif g0_complete() and analysis_from == "transcript_review_build":
        # Should not happen; force next real analysis stage
        nxt = first_pending(
            [s for s in ANALYSIS_ORDER if s not in (*PREPARE_STAGES, "audio_preclean", "transcript_review_build")]
        )
        if nxt:
            steps.append(("analysis", {"mode": "analysis", "from_stage": nxt}))
    delivery_from = first_pending(DELIVERY_ORDER)
    if delivery_from:
        steps.append(("delivery", {"mode": "delivery", "from_stage": delivery_from}))
    elif not master_ready():
        steps.append(("delivery", {"mode": "delivery"}))
    return steps


def run_until_done(body: dict[str, Any], label: str) -> dict[str, Any]:
    execute(body)
    last_gate = ""
    gate_retries = 0
    error_retries: dict[str, int] = {}
    while True:
        if master_ready():
            return {"status": "complete", "message": "master ready"}
        job = wait_job(label)
        status = job.get("status")
        if status == "complete":
            return job
        if status == "interrupted":
            # Reconcile can mark interrupted while a live worker still holds the lock.
            # Wait and re-check before forcing a re-execute (avoids 409 busy loops).
            log(f"interrupted — waiting to see if worker is still live ({label})")
            time.sleep(30)
            job2 = api("GET", f"/api/runs/{RUN_ID}/job")
            st2 = job2.get("status") or "idle"
            if st2 == "running":
                continue
            if st2 in {"gate", "needs_operator", "complete", "error"}:
                continue
            # Still interrupted/idle — try resume, but back off on busy
            log(f"interrupted — retry {label}")
            try:
                execute(body)
            except RuntimeError:
                pass
            time.sleep(15)
            continue
        if status in {"gate", "needs_operator"}:
            gate_msg = str(job.get("message") or "")[:200]
            if gate_msg == last_gate:
                gate_retries += 1
            else:
                last_gate = gate_msg
                gate_retries = 0
            if gate_retries >= 10:
                log(f"gate stuck: {gate_msg}")
                return job
            action = handle_gate(job, body)
            if action == "advance":
                log(f"{label} phase advance after gate")
                return {"status": "complete", "message": gate_msg}
            if action == "continue":
                continue
            execute(body)
            continue
        if status == "error":
            stage = parse_failed_stage(job)
            err = str(job.get("error") or job.get("message") or "")
            low_err = err.lower()
            if "lock busy" in low_err or "run_busy" in low_err or "already in progress" in low_err:
                log(f"lock busy — joining existing worker ({label})")
                time.sleep(20)
                continue
            log(f"ERROR at {stage}: {err[:400]}")
            low_err = err.lower()
            if "gap vo lines missing wav" in low_err or "missing wav" in low_err and "vo" in low_err:
                framing_active = False
                try:
                    gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
                    framing_active = bool(gate.get("gap_framing_enabled") or gate.get("enabled"))
                    delivery = str(gate.get("gap_vo_delivery") or gate.get("delivery") or "").lower()
                    if delivery in {"chatterbox", "voice_clone", "synthesize"}:
                        framing_active = True
                except Exception:
                    pass
                if framing_active:
                    log(
                        "HARD: missing gap VO WAV while framing/chatterbox active — "
                        "not auto-skipping G1; re-run synthesize-all after TTS fix"
                    )
                    return {**job, "status": "error", "message": "missing_vo_framing_active_no_skip"}
                log("healing G1 skipped VO markers after missing WAV")
                skip_g1()
                try:
                    from interview_mux.run_context import RunContext
                    from interview_mux.artifact_repairs import repair_gap_report
                    from interview_mux.artifact_writes import write_validated_artifact

                    ctx = RunContext(RUN_ID, create=False)
                    if ctx.artifact_exists("understanding/gap_report.json"):
                        gr = ctx.read_json("understanding/gap_report.json")
                        repaired, _ = repair_gap_report(ctx, gr)
                        write_validated_artifact(
                            ctx,
                            "understanding/gap_report.json",
                            repaired,
                            merge_from_disk=False,
                            stage_key="gap_framing_compose",
                        )
                        log("gap_report skipped_optional healed")
                except Exception as exc:
                    log(f"gap_report heal: {exc}")
            if "outside palette mapping" in low_err or "outside palettes" in low_err:
                try:
                    from interview_mux.run_context import RunContext
                    from interview_mux.artifact_repairs import repair_sound_design_plan
                    from interview_mux.artifact_writes import write_validated_artifact

                    ctx = RunContext(RUN_ID, create=False)
                    if ctx.artifact_exists("understanding/sound_design_plan.json"):
                        sdp = ctx.read_json("understanding/sound_design_plan.json")
                        repaired, notes = repair_sound_design_plan(ctx, sdp)
                        write_validated_artifact(
                            ctx,
                            "understanding/sound_design_plan.json",
                            repaired,
                            merge_from_disk=False,
                            stage_key="sound_design_plan",
                        )
                        log(f"sdp palette heal: {notes[:3]}")
                except Exception as exc:
                    log(f"sdp heal: {exc}")
            n = error_retries.get(stage or "unknown", 0)
            if stage and n < 3:
                error_retries[stage] = n + 1
                # Resume analysis/delivery from the failed stage, not a single-stage mode
                mode = body.get("mode") or "analysis"
                if mode == "analysis_until_g0":
                    mode = "analysis"
                execute({"mode": mode, "from_stage": stage})
                continue
            return job
        if status == "stalled":
            stage = str(job.get("stage") or job.get("current_stage") or "")
            log(f"stalled {stage} — waiting before re-execute")
            time.sleep(120)
            job2 = api("GET", f"/api/runs/{RUN_ID}/job")
            st2 = job2.get("status") or "idle"
            if st2 in {"running", "gate", "needs_operator", "complete"}:
                continue
            if stage:
                execute({"mode": body.get("mode") or "analysis", "from_stage": stage})
            else:
                execute(body)
            continue
        if status == "idle":
            return job
        time.sleep(POLL_SEC)


def main() -> int:
    log(f"=== baba e2e start run={RUN_ID} ===")
    # Wait for GUI server (restarts mid-run are common while fixing bugs).
    for i in range(60):
        try:
            api("GET", "/api/health", timeout=10)
            break
        except Exception as exc:
            log(f"waiting for server ({i + 1}/60): {exc}")
            time.sleep(3)
    else:
        log("STOP: server never became healthy")
        return 2
    grant_consent()
    try:
        api("PUT", "/api/session/active", {"run_id": RUN_ID, "active_tab": "pipeline"})
    except RuntimeError as exc:
        log(f"session active: {exc}")
    dismiss_preclean()
    heal_stage_done_markers()
    hard_fail_rounds = 0

    while True:
        if master_ready():
            log(f"DONE master={MASTER} size={MASTER.stat().st_size}")
            return 0
        try:
            heal_stage_done_markers()
            bodies = build_bodies()
        except Exception as exc:
            log(f"build_bodies failed (will retry): {exc}")
            time.sleep(10)
            continue
        if not bodies:
            log("no pending stages but no master — waiting")
            time.sleep(30)
            continue
        for label, body in bodies:
            log(f"=== {label.upper()} {body} | {progress()} ===")
            try:
                job = run_until_done(body, label)
            except Exception as exc:
                log(f"run_until_done failed (will retry): {exc}")
                time.sleep(10)
                break
            if label == "prepare":
                if not g0_complete():
                    complete_g0()
                if g0_complete():
                    log("G0 confirmed — leaving prepare")
            if master_ready():
                log(f"DONE master={MASTER}")
                return 0
            if job.get("status") == "error":
                msg = str(job.get("message") or job.get("error") or "")
                log(f"error (will heal+retry): {msg[:400]}")
                hard_fail_rounds += 1
                if hard_fail_rounds >= 40:
                    log(f"STOP after {hard_fail_rounds} error rounds")
                    return 1
                time.sleep(5)
                break
            hard_fail_rounds = 0
        time.sleep(10)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        log(traceback.format_exc())
        raise
