#!/usr/bin/env python3
"""Drive exec_1123 (baba_all_vocals) to master.wav via HTTP API + gate handling."""

from __future__ import annotations

import json
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = "http://127.0.0.1:8765"
RUN_ID = "exec_1123_1311e28fffa1_20260727T200034Z"
POLL_SEC = 20
MAX_WAIT_SEC = 60 * 60 * 12  # 12h for 56-min source
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


def grant_consent() -> None:
    for provider in ("local", "openai"):
        try:
            api("POST", "/api/session/api-consent", {"provider": provider, "granted": True})
        except RuntimeError as exc:
            log(f"consent {provider}: {exc}")


def stage_statuses() -> dict[str, str]:
    run = api("GET", f"/api/runs/{RUN_ID}", timeout=300)
    return {s["id"]: str(s.get("status") or "pending") for s in run.get("stages", [])}


def progress() -> str:
    st = stage_statuses()
    done = sum(1 for v in st.values() if v == "done")
    return f"{done}/{len(st)} done; master={'yes' if MASTER.is_file() else 'no'}"


def wait_job(label: str = "") -> dict[str, Any]:
    deadline = time.time() + MAX_WAIT_SEC
    last = ""
    while time.time() < deadline:
        if MASTER.is_file() and MASTER.stat().st_size > 1000:
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
            # idle right after start can race — wait once more if recently running
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
    try:
        api("POST", f"/api/runs/{RUN_ID}/execute", body)
    except RuntimeError as exc:
        if "409" in str(exc) or "already" in str(exc).lower():
            log(f"execute busy: {exc}")
            return
        raise


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
        api(
            "POST",
            f"/api/runs/{RUN_ID}/transcript-review/complete",
            {"accept_unreviewed": True},
        )
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
    pickup = api("GET", f"/api/runs/{RUN_ID}/pickup-speaker")
    if pickup.get("pending") or not pickup.get("pickup_speaker_confirmed"):
        sid = pickup.get("pickup_eligible_speaker_id") or pickup.get("least_spoken_speaker_id")
        body = {"pickup_eligible_speaker_id": sid} if sid else {}
        api("POST", f"/api/runs/{RUN_ID}/pickup-speaker/confirm", body)
        log(f"pickup speaker: {sid}")
    gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
    if gate.get("voice_reference_pending"):
        try:
            api("POST", f"/api/runs/{RUN_ID}/voice-reference/approve")
            log("voice reference approved")
        except RuntimeError as exc:
            log(f"voice ref: {exc}")
            return
    gate = api("GET", f"/api/runs/{RUN_ID}/gap-framing")
    if gate.get("gap_delivery_pending") or not gate.get("gap_vo_delivery"):
        api("POST", f"/api/runs/{RUN_ID}/gap-framing/delivery", {"delivery": "chatterbox"})
        log("delivery chatterbox")
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


def handle_gate(job: dict[str, Any], body: dict[str, Any]) -> bool:
    status = job.get("status")
    stage = str(job.get("stage") or job.get("current_stage") or "")
    msg = str(job.get("message") or "")
    low = msg.lower()

    if job.get("needs_stage_reuse") and stage:
        decline_reuse(stage)
        execute(body)
        return True

    if "transcript review" in low or stage in {"transcript_review", "transcript_review_build"}:
        complete_g0()
        execute(body)
        return True

    if (
        stage in {"missing_framing", "gap_framing_compose", "optimal_questions", "source_topology_build"}
        or "gap framing" in low
        or "pickup speaker" in low
        or "voice reference" in low
        or "gap delivery" in low
        or "voice clone" in low
    ):
        accept_gap_framing_defaults()
        execute(body)
        return True

    if stage == "g1_vo_pickup" or ("g1" in low and "vo" in low):
        if not synthesize_g1():
            skip_g1()
        execute(body)
        return True

    if stage == "audio_preclean" or "pre-clean" in low or "preclean" in low:
        dismiss_preclean()
        execute(body)
        return True

    if "post_listen" in low or "post-listen" in low:
        auto_pass_post_listen()
        execute(body)
        return True

    if status == "needs_operator" and "api consent" in low:
        grant_consent()
        execute(body)
        return True

    # Soft preview / continue gates
    if "continue" in low or "preview" in low:
        execute(body)
        return True

    return False


def first_pending(ids: list[str]) -> str | None:
    st = stage_statuses()
    for sid in ids:
        if st.get(sid) != "done":
            return sid
    return None


def build_bodies() -> list[tuple[str, dict[str, Any]]]:
    prepare_from = first_pending(["ingest", "transcribe", "transcript_review_build"])
    analysis_from = first_pending(
        [
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
        ]
    )
    delivery_from = first_pending(
        [
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
        ]
    )
    steps: list[tuple[str, dict[str, Any]]] = []
    if prepare_from:
        steps.append(("prepare", {"mode": "analysis_until_g0", "from_stage": prepare_from}))
    if analysis_from:
        steps.append(("analysis", {"mode": "analysis", "from_stage": analysis_from}))
    if delivery_from:
        steps.append(("delivery", {"mode": "delivery", "from_stage": delivery_from}))
    elif not MASTER.is_file():
        steps.append(("delivery", {"mode": "delivery"}))
    return steps


def run_until_done(body: dict[str, Any], label: str) -> dict[str, Any]:
    execute(body)
    last_gate = ""
    gate_retries = 0
    error_retries: dict[str, int] = {}
    while True:
        if MASTER.is_file() and MASTER.stat().st_size > 1000:
            return {"status": "complete", "message": "master ready"}
        job = wait_job(label)
        status = job.get("status")
        if status == "complete":
            return job
        if status == "interrupted":
            log(f"interrupted — retry {label}")
            execute(body)
            continue
        if status in {"gate", "needs_operator"}:
            gate_msg = str(job.get("message") or "")[:200]
            if gate_msg == last_gate:
                gate_retries += 1
            else:
                last_gate = gate_msg
                gate_retries = 0
            if gate_retries >= 8:
                log(f"gate stuck: {gate_msg}")
                return job
            if handle_gate(job, body):
                continue
            # try default continue
            execute(body)
            continue
        if status == "error":
            stage = str(job.get("stage") or job.get("current_stage") or "")
            err = str(job.get("last_error") or job.get("message") or "")
            log(f"ERROR at {stage}: {err[:400]}")
            n = error_retries.get(stage, 0)
            if stage and n < 3:
                error_retries[stage] = n + 1
                execute({"mode": "stage", "stage": stage, "from_stage": stage})
                continue
            return job
        if status == "stalled":
            # Long local STT can look stalled while the subprocess is healthy.
            # Only re-execute after the job is no longer busy.
            stage = str(job.get("stage") or job.get("current_stage") or "")
            log(f"stalled {stage} — waiting before re-execute")
            time.sleep(120)
            job2 = api("GET", f"/api/runs/{RUN_ID}/job")
            st2 = job2.get("status") or "idle"
            if st2 in {"running", "gate", "needs_operator", "complete"}:
                continue
            if stage:
                execute({"mode": "stage", "stage": stage, "from_stage": stage})
            else:
                execute(body)
            continue
        if status == "idle":
            return job
        time.sleep(POLL_SEC)


def main() -> int:
    log(f"=== baba e2e start run={RUN_ID} ===")
    grant_consent()
    api("PUT", "/api/session/active", {"run_id": RUN_ID, "active_tab": "pipeline"})
    dismiss_preclean()

    while True:
        if MASTER.is_file() and MASTER.stat().st_size > 1000:
            log(f"DONE master={MASTER} size={MASTER.stat().st_size}")
            return 0
        bodies = build_bodies()
        if not bodies:
            log("no pending stages but no master — waiting")
            time.sleep(30)
            continue
        for label, body in bodies:
            log(f"=== {label.upper()} {body} | {progress()} ===")
            job = run_until_done(body, label)
            if label == "prepare" and job.get("status") in {"gate", "needs_operator", "complete"}:
                complete_g0()
            if MASTER.is_file():
                log(f"DONE master={MASTER}")
                return 0
            if job.get("status") == "error":
                log(f"STOP error: {job}")
                # dump stage statuses for diagnosis
                st = stage_statuses()
                bad = {k: v for k, v in st.items() if v not in {"done", "skipped", "pending"}}
                log(f"non-done statuses: {bad}")
                return 1
        time.sleep(10)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        log(traceback.format_exc())
        raise
