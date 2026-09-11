"""End-judgment after a complete master.wav."""

from __future__ import annotations

from typing import Any

from interview_mux.delivery_invariants import committed_master_wav
from interview_mux.homunculus.budget import check_dispatch
from interview_mux.homunculus.ledger import append_ledger
from interview_mux.homunculus.runtime import homunculus_version
from interview_mux.run_context import RunContext

JUDGE_REL = "mastering/homunculus/end_judgment.json"


def write_judgment(
    ctx: RunContext,
    *,
    verdict: str,
    reason: str,
    implicated_groups: list[str] | None = None,
    ears_packet: dict[str, Any] | None = None,
    fail_open_reason: str | None = None,
) -> dict[str, Any]:
    if verdict == "accept" and not ears_packet and not fail_open_reason:
        raise RuntimeError("accept blocked: ears packet or fail-open reason required")
    if verdict == "reject":
        check_dispatch(ctx, identity="complete_master", kind="complete_master")
    doc = {
        "homunculus_version": homunculus_version(ctx),
        "verdict": verdict,
        "reason": reason,
        "implicated_groups": list(implicated_groups or []),
        "ears": ears_packet,
        "fail_open_reason": fail_open_reason,
    }
    ctx.write_json(JUDGE_REL, doc)
    append_ledger(ctx, {"kind": "end_judgment", "identity": "end_judgment", "verdict": verdict})
    if verdict == "reject":
        try:
            from interview_mux.homunculus.kb import record_reject_lessons

            failed: list[str] = []
            if ctx.artifact_exists("mastering/listen_delight_audit.json"):
                delight = ctx.read_json("mastering/listen_delight_audit.json") or {}
                if isinstance(delight, dict):
                    failed = list(delight.get("failed_dimensions") or [])
            record_reject_lessons(
                ctx,
                failed_dimensions=failed or ["reject"],
                implicated_groups=list(implicated_groups or []),
                reason=reason,
            )
        except Exception:
            pass
    return doc


def after_complete_master(ctx: RunContext) -> dict[str, Any]:
    """Ears then judgment. Fail-open STT still produces a packet so accept is allowed.

    Do not accept a missing master.wav as a successful listen. If neither
    ``master/master.wav`` nor ``master/assembly.wav`` exists, reject only when
    listen-delight already failed; otherwise defer until a wav is written.
    """
    has_wav = committed_master_wav(ctx) or ctx.artifact_exists("master/assembly.wav")
    if ctx.artifact_exists(JUDGE_REL):
        existing = ctx.read_json(JUDGE_REL)
        if isinstance(existing, dict):
            fail_reason = str(existing.get("fail_open_reason") or "")
            stale_accept = (
                existing.get("verdict") == "accept"
                and "FileNotFoundError" in fail_reason
                and has_wav
            )
            if existing.get("verdict") in {"accept", "reject"} and not stale_accept:
                return existing
        elif not has_wav:
            return {"verdict": "unknown"}
    ears_packet: dict[str, Any] | None = None
    fail_open = None
    try:
        from interview_mux.homunculus.ears import hear_master_windows

        ears_packet = hear_master_windows(ctx)
        if ears_packet.get("fail_open"):
            fail_open = str(ears_packet.get("fail_open_reason") or "ears_stt_unavailable")
    except Exception as exc:
        fail_open = f"ears_unavailable:{type(exc).__name__}"
        from interview_mux.homunculus.issues import ingest_catch

        ingest_catch(
            ctx,
            kind="ears_stt_unavailable",
            source="end_judgment",
            evidence={"error": str(exc)[:240]},
        )
    delight = {}
    delight_rel = "mastering/listen_delight_audit.json"
    if ctx.artifact_exists(delight_rel):
        try:
            delight = ctx.read_json(delight_rel) or {}
        except Exception:
            delight = {}
    failed = list((delight.get("failed_dimensions") or []) if isinstance(delight, dict) else [])
    aspirational = False
    try:
        from interview_mux.aspirational_quality import (
            is_aspirational_enabled,
            record_quality_advisories,
        )

        aspirational = is_aspirational_enabled(ctx) and bool(failed)
    except Exception:
        aspirational = False
    verdict = "reject" if failed and not aspirational else "accept"
    reason = (
        f"listen_delight floors failed: {failed}"
        if failed and not aspirational
        else (
            f"aspirational accept with delight advisories: {failed}"
            if failed
            else "ears + delight allowed accept"
        )
    )
    if aspirational and failed:
        record_quality_advisories(
            ctx,
            gate_id="homunculus_delight_reject",
            failed_checks=failed,
            detail={"deferred_verdict": "accept"},
            aspirational_proceeded=True,
        )
    if verdict == "accept" and not has_wav:
        return {
            "verdict": "pending",
            "reason": "master.wav not written yet — defer end judgment",
            "ears": ears_packet,
            "fail_open_reason": fail_open,
        }
    return write_judgment(
        ctx,
        verdict=verdict,
        reason=reason,
        ears_packet=ears_packet,
        fail_open_reason=fail_open if verdict == "accept" else None,
        implicated_groups=["listen_delight_audit", "mix"] if failed else [],
    )
