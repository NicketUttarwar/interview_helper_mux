#!/usr/bin/env python3
"""Drive the GUI pipeline to completion via HTTP API (operator gates auto-accepted)."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

BASE = "http://127.0.0.1:8765"
INPUT_AUDIO = "ASSETS/notebooklm_original_interview_2024.wav"
POLL_SEC = 15
MAX_WAIT_SEC = 7200


def api(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        try:
            payload = json.loads(detail)
        except json.JSONDecodeError:
            payload = {"detail": detail}
        raise RuntimeError(f"{method} {path} -> {exc.code}: {payload}") from exc


def clear_session() -> None:
    try:
        api("DELETE", "/api/session/active")
    except RuntimeError:
        api("PUT", "/api/session/active", {"run_id": None})


def active_run_id() -> str | None:
    try:
        sess = api("GET", "/api/session")
        active = sess.get("active") or {}
        rid = active.get("run_id")
        return str(rid) if rid else None
    except RuntimeError:
        return None


def ensure_run(*, fresh: bool = True) -> str:
    if fresh:
        clear_session()
        created = api("POST", "/api/runs", {"input_audio_path": INPUT_AUDIO})
        return str(created["run_id"])
    existing = active_run_id()
    if existing:
        return existing
    created = api("POST", "/api/runs", {"input_audio_path": INPUT_AUDIO})
    return str(created["run_id"])


def grant_consent() -> None:
    for provider in ("local", "openai"):
        api("POST", "/api/session/api-consent", {"provider": provider, "granted": True})


def stage_statuses(run_id: str) -> dict[str, str]:
    """Prefer filesystem .stage_done markers — full GET /api/runs can hang under load."""
    done_dir = EXEC_ROOT / run_id / ".stage_done"
    # Keep in sync with interview_mux.v2.config orders when possible
    try:
        from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

        ids = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    except Exception:
        ids = []
        if done_dir.is_dir():
            ids = [p.name for p in done_dir.iterdir()]
    return {sid: ("done" if (done_dir / sid).is_file() else "pending") for sid in ids}


from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXEC_ROOT = REPO / "ASSETS" / "executions"

STAGE_ARTIFACTS: dict[str, str] = {
    "source_acoustic_profile": "understanding/source_acoustic_profile.json",
    "interview_spine_build": "understanding/interview_spine.json",
    "speaker_roles": "understanding/speakers.json",
}


def artifact_exists(run_id: str, rel_path: str) -> bool:
    return (EXEC_ROOT / run_id / rel_path).is_file()


def stage_needs_run(run_id: str, stage_id: str) -> bool:
    if stage_statuses(run_id).get(stage_id) != "done":
        return True
    rel = STAGE_ARTIFACTS.get(stage_id)
    return bool(rel and not artifact_exists(run_id, rel))


def first_pending(run_id: str, stage_ids: list[str]) -> str | None:
    for sid in stage_ids:
        if stage_needs_run(run_id, sid):
            return sid
    return None


def wait_job(run_id: str, label: str = "") -> dict[str, Any]:
    deadline = time.time() + MAX_WAIT_SEC
    last_msg = ""
    while time.time() < deadline:
        job = api("GET", f"/api/runs/{run_id}/job")
        status = job.get("status") or "idle"
        msg = str(job.get("message") or "")
        stage = job.get("current_stage") or job.get("stage") or ""
        if msg != last_msg:
            print(f"  [{label}] {status} {stage}: {msg[:120]}", flush=True)
            last_msg = msg
        if status in {"complete", "error", "gate", "needs_operator", "interrupted"}:
            return job
        time.sleep(POLL_SEC)
    raise TimeoutError(f"Timed out waiting for job ({label})")


def dismiss_preclean(run_id: str) -> None:
    api(
        "POST",
        f"/api/runs/{run_id}/preclean-offer",
        {"checkpoint": "before_ingest", "action": "dismiss", "scope": "full_source"},
    )


def complete_g0(run_id: str) -> None:
    try:
        api("POST", f"/api/runs/{run_id}/transcript-review/complete", {"accept_unreviewed": True})
        print("  G0 transcript review accepted", flush=True)
    except RuntimeError as exc:
        if "not ready" in str(exc).lower():
            print(f"  G0 skip (not ready): {exc}", flush=True)
        else:
            raise


def verify_profile(run_id: str) -> None:
    try:
        api("POST", f"/api/runs/{run_id}/analysis-profile/verify", {})
        print("  Interview profile marked verified", flush=True)
    except RuntimeError as exc:
        print(f"  Profile verify note: {exc}", flush=True)


def skip_g1_optional(run_id: str) -> None:
    try:
        api("POST", f"/api/runs/{run_id}/g1/skip-optional", {"force": True})
        print("  G1 skip-optional applied", flush=True)
    except RuntimeError as exc:
        print(f"  G1 skip note: {exc}", flush=True)


def synthesize_g1(run_id: str) -> bool:
    try:
        result = api("POST", f"/api/runs/{run_id}/g1/synthesize-all", {})
        print(
            f"  G1 synthesize-all: {len(result.get('synthesized') or [])} lines"
            f" errors={result.get('errors') or []}",
            flush=True,
        )
        return bool(result.get("ok", True)) and not (result.get("errors") or [])
    except RuntimeError as exc:
        print(f"  G1 synthesize note: {exc}", flush=True)
        return False


def approve_sfx_prompts(run_id: str) -> None:
    try:
        result = api("POST", f"/api/runs/{run_id}/sfx-prompts/approve", {})
        print(f"  SFX prompts approve: {result}", flush=True)
    except RuntimeError as exc:
        print(f"  SFX prompts approve note: {exc}", flush=True)


def accept_gap_framing_defaults(run_id: str) -> None:
    """Apply product defaults: framing Yes, least-spoken host, Chatterbox clone + consent."""
    gate = api("GET", f"/api/runs/{run_id}/gap-framing")
    if gate.get("gap_framing_decision_pending"):
        api("POST", f"/api/runs/{run_id}/gap-framing/enable", {"enabled": True})
        print("  Gap framing enabled (default Yes)", flush=True)

    pickup = api("GET", f"/api/runs/{run_id}/pickup-speaker")
    if pickup.get("pending") or not pickup.get("pickup_speaker_confirmed"):
        sid = pickup.get("pickup_eligible_speaker_id") or pickup.get("least_spoken_speaker_id")
        body = {"pickup_eligible_speaker_id": sid} if sid else {}
        api("POST", f"/api/runs/{run_id}/pickup-speaker/confirm", body)
        print(f"  Pickup speaker confirmed: {sid or 'default least-spoken'}", flush=True)

    gate = api("GET", f"/api/runs/{run_id}/gap-framing")
    if gate.get("voice_reference_pending"):
        try:
            api("POST", f"/api/runs/{run_id}/voice-reference/approve")
            print("  Voice reference approved", flush=True)
        except RuntimeError as exc:
            print(f"  Voice reference approve note: {exc}", flush=True)
            return

    gate = api("GET", f"/api/runs/{run_id}/gap-framing")
    if gate.get("gap_delivery_pending") or not gate.get("gap_vo_delivery"):
        api("POST", f"/api/runs/{run_id}/gap-framing/delivery", {"delivery": "chatterbox"})
        print("  Gap delivery: chatterbox", flush=True)

    gate = api("GET", f"/api/runs/{run_id}/gap-framing")
    if gate.get("clone_consent_pending") or gate.get("clone_consent_required"):
        sid = gate.get("pickup_eligible_speaker_id")
        try:
            api(
                "POST",
                f"/api/runs/{run_id}/voice-clone-consent",
                {
                    "speaker_id": sid,
                    "scopes": ["cold_open", "bridges", "outro"],
                    "disclosure": "none",
                    "granted_by": "e2e_pipeline_driver",
                },
            )
            print("  Voice clone consent granted", flush=True)
        except RuntimeError as exc:
            print(f"  Clone consent note: {exc}", flush=True)


def decline_reuse(run_id: str, stage_id: str) -> None:
    api("POST", f"/api/runs/{run_id}/stages/{stage_id}/reuse", {"action": "decline"})
    print(f"  Declined reuse for {stage_id}", flush=True)


def auto_pass_post_listen(run_id: str) -> None:
    try:
        sfx = api("GET", f"/api/runs/{run_id}/sfx-prompts")
    except RuntimeError:
        return
    asset_ids: set[str] = set()
    for row in sfx.get("prompts") or []:
        if isinstance(row, dict) and row.get("asset_id"):
            asset_ids.add(str(row["asset_id"]))
    for row in sfx.get("assets") or []:
        if isinstance(row, dict) and row.get("asset_id"):
            asset_ids.add(str(row["asset_id"]))
    for aid in sorted(asset_ids):
        api(
            "POST",
            f"/api/runs/{run_id}/sfx-prompts/listen-result",
            {"asset_id": aid, "result": "pass", "note": "e2e auto-pass"},
        )
    if asset_ids:
        print(f"  Auto-passed post-listen for {len(asset_ids)} asset(s)", flush=True)


def execute(run_id: str, body: dict[str, Any]) -> None:
    body = {**body, "api_consents": {"local": True, "openai": True}}
    api("POST", f"/api/runs/{run_id}/execute", body)


def handle_gate(run_id: str, job: dict[str, Any], body: dict[str, Any]) -> bool:
    """Return True if gate was handled and caller should retry/wait."""
    status = job.get("status")
    stage = job.get("stage") or job.get("current_stage") or ""
    msg = str(job.get("message") or "")
    low = msg.lower()

    if job.get("needs_stage_reuse") and stage:
        decline_reuse(run_id, stage)
        execute(run_id, body)
        return True

    if "transcript review" in low or stage == "transcript_review":
        complete_g0(run_id)
        if stage_statuses(run_id).get("transcript_review_build") == "done":
            return True
        execute(run_id, body)
        return True

    if "operator-verified" in low or "mark verified" in low or "interview profile" in low:
        verify_profile(run_id)
        execute(run_id, body)
        return True

    if stage == "g1_vo_pickup" or ("g1" in low and "vo" in low):
        if not synthesize_g1(run_id):
            framing_active = False
            delivery = ""
            try:
                gate = api("GET", f"/api/runs/{run_id}/gap-framing")
                framing_active = bool(gate.get("gap_framing_enabled") or gate.get("enabled"))
                delivery = str(gate.get("gap_vo_delivery") or gate.get("delivery") or "").lower()
            except Exception:
                pass
            if framing_active or delivery in {"chatterbox", "voice_clone", "synthesize"}:
                raise RuntimeError(
                    "G1 synthesize-all failed while framing/chatterbox active — refusing auto-skip"
                )
            skip_g1_optional(run_id)
        execute(run_id, body)
        return True

    if (
        stage in {"sfx_prompt_craft", "mmaudio_sfx"}
        or "g1.5" in low
        or "prompt approval" in low
        or "sfx prompt" in low
        or "approve prompts" in low
    ):
        approve_sfx_prompts(run_id)
        execute(run_id, body)
        return True

    if (
        stage in {"missing_framing", "gap_framing_compose", "optimal_questions"}
        or "gap framing" in low
        or "pickup speaker" in low
        or "voice reference" in low
        or "gap delivery" in low
        or "voice clone" in low
    ):
        accept_gap_framing_defaults(run_id)
        execute(run_id, body)
        return True

    if stage == "audio_preclean" or "pre-clean" in low or "preclean" in low:
        dismiss_preclean(run_id)
        execute(run_id, body)
        return True

    if "post_listen" in low or "post-listen" in low:
        auto_pass_post_listen(run_id)
        execute(run_id, body)
        return True

    if status == "needs_operator" and "api consent" in low:
        grant_consent()
        execute(run_id, body)
        return True

    return False


def run_until_done(run_id: str, body: dict[str, Any], label: str) -> dict[str, Any]:
    execute(run_id, body)
    last_gate = ""
    gate_retries = 0
    while True:
        job = wait_job(run_id, label)
        status = job.get("status")
        if status == "complete":
            return job
        if status == "interrupted":
            print(f"  Job interrupted — retrying {label}", flush=True)
            execute(run_id, body)
            continue
        if status in {"gate", "needs_operator"}:
            gate_msg = str(job.get("message") or "")[:160]
            if gate_msg == last_gate:
                gate_retries += 1
            else:
                last_gate = gate_msg
                gate_retries = 0
            if gate_retries >= 5:
                print(f"  Gate retry limit reached for {label}", flush=True)
                return job
            if handle_gate(run_id, job, body):
                continue
            return job
        if status == "error":
            stage = job.get("stage") or job.get("current_stage") or ""
            if stage:
                print(f"  Retrying failed stage {stage}", flush=True)
                execute(run_id, {"mode": "stage", "stage": stage, "from_stage": stage})
                continue
            return job
        time.sleep(POLL_SEC)


def build_steps(run_id: str) -> list[tuple[str, dict[str, Any]]]:
    prepare_from = first_pending(
        run_id,
        ["transcribe", "transcript_review_build"],
    )
    analysis_from = first_pending(
        run_id,
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
            "vernacular_segment_sanitize",
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
        ],
    )
    steps: list[tuple[str, dict[str, Any]]] = []
    if stage_statuses(run_id).get("ingest") != "done":
        steps.append(("ingest", {"mode": "stage", "stage": "ingest", "from_stage": "ingest"}))
    if prepare_from:
        steps.append(
            ("prepare", {"mode": "analysis_until_g0", "from_stage": prepare_from}),
        )
    if analysis_from:
        steps.append(("analysis", {"mode": "analysis", "from_stage": analysis_from}))
    steps.append(("delivery", {"mode": "delivery"}))
    return steps


def main() -> int:
    fresh = "--resume" not in sys.argv
    print("Granting API consent…", flush=True)
    grant_consent()

    print("Creating execution…" if fresh else "Resuming active execution…", flush=True)
    run_id = ensure_run(fresh=fresh)
    print(f"Run: {run_id}", flush=True)

    api("PUT", "/api/session/active", {"run_id": run_id, "active_tab": "pipeline"})
    dismiss_preclean(run_id)

    for label, body in build_steps(run_id):
        print(f"\n=== {label.upper()} ===", flush=True)
        job = run_until_done(run_id, body, label)
        if job.get("status") == "gate" and label == "prepare":
            complete_g0(run_id)
            job = run_until_done(run_id, body, label + "-after-g0")
        if job.get("status") != "complete":
            msg = str(job.get("message") or "")
            if label == "analysis" and "missing" in msg.lower() and "remediation: run" in msg.lower():
                for sid in STAGE_ARTIFACTS:
                    if sid.replace("_", " ") in msg.lower() or sid in msg.lower():
                        print(f"  Retrying analysis from {sid}", flush=True)
                        body = {"mode": "analysis", "from_stage": sid}
                        job = run_until_done(run_id, body, f"{label}-{sid}")
                        break
            if job.get("status") != "complete":
                print(
                    f"STOP: {label} ended with {job.get('status')}: {job.get('message', '')[:240]}",
                    flush=True,
                )
                run = api("GET", f"/api/runs/{run_id}")
                done = sum(1 for s in run.get("stages", []) if s.get("status") == "done")
                total = len(run.get("stages", []))
                print(f"Progress: {done}/{total} stages done", flush=True)
                return 1

    run = api("GET", f"/api/runs/{run_id}")
    master = run.get("meta", {}).get("master_path") or "master/master.wav"
    print(f"\nDONE — run {run_id} ({master})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
