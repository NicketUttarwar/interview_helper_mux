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


def _identity_cap(identity: str, kind: str = "") -> int:
    """Per-tool invoke cap. Conductor turns use max_conductor_turns, not the stage cap."""
    if identity == "conductor_turn" or kind == "conductor_turn":
        return max_conductor_turns()
    return int(_cfg().get("max_invokes_per_identity") or MAX_INVOKES_PER_IDENTITY)


def remaining(ctx: RunContext, identity: str) -> int:
    used = count_identity(ctx, identity)
    cap = _identity_cap(identity)
    return max(0, cap - used)


def mark_identity_exhausted(ctx: RunContext, identity: str) -> None:
    cache = getattr(ctx, "_budget_exhausted_identities", None)
    if cache is None:
        cache = set()
        setattr(ctx, "_budget_exhausted_identities", cache)
    cache.add(identity)


def identity_exhausted(ctx: RunContext, identity: str) -> bool:
    cache = getattr(ctx, "_budget_exhausted_identities", None)
    if isinstance(cache, set) and identity in cache:
        return True
    return remaining(ctx, identity) <= 0


def remaining_conductor_turns(ctx: RunContext) -> int:
    return remaining(ctx, "conductor_turn")


def check_dispatch(
    ctx: RunContext,
    *,
    identity: str,
    kind: str,
    packet_hash: str | None = None,
    problem_id: str | None = None,
) -> None:
    """Refuse before side effects. Ledger is the source of counts."""
    from interview_mux.chapter_close_hitch import hitch_budget_identity, junction_snip_budget_identity

    identity = junction_snip_budget_identity(ctx, hitch_budget_identity(ctx, identity))
    try:
        from interview_mux.media_ip_cta import cta_cover_budget_exempt

        if cta_cover_budget_exempt(ctx):
            return
    except Exception:
        pass
    limits = _cfg()
    cap = _identity_cap(identity, kind)
    used = count_identity(ctx, identity)
    if used >= cap:
        reason = (
            "max_conductor_turns"
            if identity == "conductor_turn" or kind == "conductor_turn"
            else "max_invokes_per_identity"
        )
        mark_identity_exhausted(ctx, identity)
        _halt(ctx, identity, reason, {"used": used, "cap": cap})
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
    turn_cap = max_conductor_turns()
    remaining_map: dict[str, int] = {}
    for k, v in identities.items():
        ident_cap = turn_cap if k == "conductor_turn" else cap
        remaining_map[k] = max(0, ident_cap - v)
    return {
        "max_invokes_per_identity": cap,
        "max_conductor_turns": turn_cap,
        "identities": identities,
        "remaining": remaining_map,
    }
