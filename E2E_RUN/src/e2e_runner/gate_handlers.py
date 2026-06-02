"""API-first gate resolution for E2E automation."""

from __future__ import annotations

from typing import Any

from e2e_runner.api_client import API_CONSENTS, ApiClient
from e2e_runner.wav_stub import minimal_wav_bytes


def resolve_blocking(
    api: ApiClient,
    run_id: str,
    run: dict[str, Any],
) -> list[str]:
    """Resolve gates/checkpoints; return list of actions taken."""
    actions: list[str] = []
    job = run.get("job") or {}
    job_status = str(job.get("status") or "idle")

    if job_status == "needs_operator" and _needs_api_consent(job):
        actions.append("api_consent_noted")

    stages = run.get("stages") or []
    for stage in stages:
        sid = stage.get("id") or ""
        status = stage.get("status") or ""

        if status == "action_required" and sid == "transcript_review":
            api.complete_transcript_review(run_id, accept_unreviewed=True)
            actions.append("transcript_review_complete")

        if run.get("profile_gate_pending") and sid == "analysis_profile":
            try:
                api.verify_profile(run_id)
                actions.append("profile_verified")
            except Exception:
                pass

    if run.get("g1_missing"):
        stub = minimal_wav_bytes()
        for line_id in run.get("g1_missing") or []:
            api.upload_vo(run_id, str(line_id), stub)
            actions.append(f"vo_upload:{line_id}")

    selected = run.get("selected_flow") or run.get("meta", {}).get("selected_flow")
    flow_intent = run.get("flow_intent") or run.get("meta", {}).get("flow_intent")
    if not selected and flow_intent and _needs_g2(run):
        api.select_flow(run_id, str(flow_intent))
        actions.append(f"flow_select:{flow_intent}")

    journey = run.get("journey") or {}
    milestones = journey.get("milestones") or {}
    if milestones.get("preview_ready") and not milestones.get("preview_listened"):
        try:
            api.preview_listened(run_id)
            actions.append("preview_listened")
        except Exception:
            pass

    _dismiss_preclean_offers(api, run_id, run, actions)
    _ack_handoffs(api, run_id, run, actions)
    _approve_elevenlabs_if_needed(api, run_id, stages, actions)

    return actions


def _needs_api_consent(job: dict[str, Any]) -> bool:
    msg = str(job.get("message") or "")
    return "API consent" in msg or bool(job.get("missing_api_providers"))


def _needs_g2(run: dict[str, Any]) -> bool:
    journey = run.get("journey") or {}
    phase = journey.get("phase") or ""
    milestones = journey.get("milestones") or {}
    return phase == "complete" and milestones.get("g1_complete") and not milestones.get("g2_complete")


def _dismiss_preclean_offers(
    api: ApiClient,
    run_id: str,
    run: dict[str, Any],
    actions: list[str],
) -> None:
    journey = run.get("journey") or {}
    for cp in journey.get("preclean_checkpoints") or []:
        rec = journey.get("recommended_preclean")
        if isinstance(rec, dict) and rec.get("checkpoint") == cp:
            try:
                api.preclean_offer(run_id, str(cp), "dismiss", scope=rec.get("scope"))
                actions.append(f"preclean_dismiss:{cp}")
            except Exception:
                pass


def _ack_handoffs(
    api: ApiClient,
    run_id: str,
    run: dict[str, Any],
    actions: list[str],
) -> None:
    handoff_ack = run.get("handoff_ack") or {}
    for stage in run.get("stages") or []:
        sid = stage.get("id") or ""
        if stage.get("status") != "done" or sid in handoff_ack:
            continue
        if _stage_has_handoff(run, sid):
            try:
                api.handoff_ack(run_id, sid)
                actions.append(f"handoff_ack:{sid}")
            except Exception:
                pass


def _stage_has_handoff(run: dict[str, Any], stage_id: str) -> bool:
    for entry in run.get("log_tail") or []:
        if entry.get("stage") != stage_id:
            continue
        detail = entry.get("detail")
        if isinstance(detail, dict) and detail.get("handoff"):
            return True
    return False


def _approve_elevenlabs_if_needed(
    api: ApiClient,
    run_id: str,
    stages: list[dict[str, Any]],
    actions: list[str],
) -> None:
    for stage in stages:
        if stage.get("id") != "elevenlabs_prompt_craft":
            continue
        if stage.get("status") not in ("action_required", "done"):
            continue
        try:
            api.approve_elevenlabs_prompts(run_id)
            actions.append("elevenlabs_prompts_approved")
        except Exception:
            pass


def build_execute_body(hint: dict[str, Any] | None) -> dict[str, Any] | None:
    if not hint:
        return None
    body: dict[str, Any] = {"mode": hint.get("mode")}
    if hint.get("from_stage"):
        body["from_stage"] = hint["from_stage"]
    if hint.get("until_stage"):
        body["until_stage"] = hint["until_stage"]
    return body


def execute_with_consent(api: ApiClient, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return api.execute(run_id, body, api_consents=API_CONSENTS)
