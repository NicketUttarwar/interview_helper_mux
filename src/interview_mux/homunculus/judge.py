"""End-judgment after a complete master.wav."""

from __future__ import annotations

from typing import Any

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
    return doc


def after_complete_master(ctx: RunContext) -> dict[str, Any]:
    """Ears then judgment. Fail-open STT still produces a packet so accept is allowed."""
    if ctx.artifact_exists(JUDGE_REL):
        existing = ctx.read_json(JUDGE_REL)
        return existing if isinstance(existing, dict) else {"verdict": "unknown"}
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
    if ctx.artifact_exists("mastering/listen_delight.json"):
        try:
            delight = ctx.read_json("mastering/listen_delight.json") or {}
        except Exception:
            delight = {}
    failed = list((delight.get("failed_dimensions") or []) if isinstance(delight, dict) else [])
    verdict = "reject" if failed else "accept"
    reason = (
        f"listen_delight floors failed: {failed}"
        if failed
        else "ears + delight allowed accept"
    )
    return write_judgment(
        ctx,
        verdict=verdict,
        reason=reason,
        ears_packet=ears_packet,
        fail_open_reason=fail_open if verdict == "accept" else None,
        implicated_groups=["listen_delight_audit", "mix"] if failed else [],
    )
