"""Hard execution limits for homunculus brains. Conductor cannot raise these."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.homunculus.ledger import count_identity, count_problem, read_ledger
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

MAX_INVOKES_PER_IDENTITY = 3
MAX_PROBLEM_ANALYSES = 1
MAX_COMPLETE_MASTERS = 3
MAX_MIX_CYCLES = 3

AUDIO_MUTATING = frozenset(
    {
        "mix",
        "master_finalize",
        "audio_preclean",
        "transcribe",
        "mmaudio_sfx",
        "music_palette_compose",
        "run_musicgen",
        "run_mmaudio",
        "run_chatterbox",
        "run_s2s",
        "run_deepfilter",
        "ears_stt_window",
        "ears_s2s_window",
    }
)


class LimitExhausted(RuntimeError):
    """Hard cap hit — dispatch refused."""

    def __init__(self, identity: str, reason: str, counts: dict[str, Any]) -> None:
        self.identity = identity
        self.reason = reason
        self.counts = counts
        super().__init__(f"limit_exhausted:{identity}:{reason}")


def _cfg() -> dict[str, Any]:
    hom = ((merged_config().get("mastering") or {}).get("homunculus") or {})
    limits = hom.get("limits") if isinstance(hom.get("limits"), dict) else {}
    return limits


def max_conductor_turns() -> int:
    limits = _cfg()
    if "max_conductor_turns" in limits:
        return int(limits["max_conductor_turns"])
    return 3 * (len(ANALYSIS_ORDER) + len(DELIVERY_ORDER))


def remaining(ctx: RunContext, identity: str) -> int:
    used = count_identity(ctx, identity)
    cap = int(_cfg().get("max_invokes_per_identity") or MAX_INVOKES_PER_IDENTITY)
    return max(0, cap - used)


def check_dispatch(
    ctx: RunContext,
    *,
    identity: str,
    kind: str,
    packet_hash: str | None = None,
    problem_id: str | None = None,
) -> None:
    """Refuse before side effects. Ledger is the source of counts."""
    limits = _cfg()
    cap = int(limits.get("max_invokes_per_identity") or MAX_INVOKES_PER_IDENTITY)
    used = count_identity(ctx, identity)
    if used >= cap:
        _halt(ctx, identity, "max_invokes_per_identity", {"used": used, "cap": cap})
    if packet_hash:
        from interview_mux.homunculus.ledger import has_packet_hash

        if has_packet_hash(ctx, identity, packet_hash):
            _halt(ctx, identity, "identical_packed_call", {"packet_hash": packet_hash})
    if kind == "analyze_issue" and problem_id:
        analyses = count_problem(ctx, problem_id)
        once = int(limits.get("max_problem_analyses_per_issue") or MAX_PROBLEM_ANALYSES)
        if analyses >= once:
            _halt(
                ctx,
                identity,
                "max_problem_analyses_per_issue",
                {"problem_id": problem_id, "used": analyses, "cap": once},
            )
    turns = count_identity(ctx, "conductor_turn")
    turn_cap = max_conductor_turns()
    if kind == "conductor_turn" and turns >= turn_cap:
        _halt(ctx, "conductor_turn", "max_conductor_turns", {"used": turns, "cap": turn_cap})
    if identity in {"mix", "master_finalize"}:
        mix_cap = int(limits.get("max_mix_cycles") or MAX_MIX_CYCLES)
        if used >= mix_cap:
            _halt(ctx, identity, "max_mix_cycles", {"used": used, "cap": mix_cap})
    if identity == "complete_master":
        master_cap = int(limits.get("max_complete_masters") or MAX_COMPLETE_MASTERS)
        if used >= master_cap:
            _halt(ctx, identity, "max_complete_masters", {"used": used, "cap": master_cap})


def check_audio_serialize(ctx: RunContext, identity: str, inflight: set[str]) -> None:
    if identity not in AUDIO_MUTATING:
        return
    busy = inflight & AUDIO_MUTATING
    if busy:
        _halt(
            ctx,
            identity,
            "audio_serialize",
            {"inflight": sorted(busy), "requested": identity},
        )


def _halt(ctx: RunContext, identity: str, reason: str, counts: dict[str, Any]) -> None:
    payload = {
        "identity": identity,
        "reason": reason,
        "counts": counts,
        "homunculus_version": (ctx.read_json("run_meta.json") or {}).get(
            "homunculus_version"
        ),
    }
    try:
        ctx.write_json("mastering/homunculus/limit_exhausted.json", payload)
    except Exception:
        pass
    try:
        from interview_mux.homunculus.issues import emit_issue

        emit_issue(
            ctx,
            kind="limit_exhausted",
            source="budget",
            implicated=[identity],
            evidence={"reason": reason, "counts": counts},
        )
    except Exception:
        pass
    raise LimitExhausted(identity, reason, counts)


def snapshot(ctx: RunContext) -> dict[str, Any]:
    ledger = read_ledger(ctx)
    identities: dict[str, int] = {}
    for row in ledger:
        ident = str(row.get("identity") or "")
        if ident:
            identities[ident] = identities.get(ident, 0) + 1
    cap = int(_cfg().get("max_invokes_per_identity") or MAX_INVOKES_PER_IDENTITY)
    return {
        "max_invokes_per_identity": cap,
        "max_conductor_turns": max_conductor_turns(),
        "identities": identities,
        "remaining": {k: max(0, cap - v) for k, v in identities.items()},
    }
