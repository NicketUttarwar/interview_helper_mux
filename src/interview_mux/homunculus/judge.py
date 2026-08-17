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
