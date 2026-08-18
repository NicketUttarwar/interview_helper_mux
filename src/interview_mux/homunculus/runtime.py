"""Run helpers: is this execution a homunculus brain, and dispatch stages through rails."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.homunculus.admit import admit
from interview_mux.homunculus.budget import LimitExhausted, check_audio_serialize, check_dispatch
from interview_mux.homunculus.issues import emit_issue, has_analysis
from interview_mux.homunculus.ledger import append_ledger
from interview_mux.homunculus.version import is_homunculus_brain
from interview_mux.run_context import RunContext

_INFLIGHT: dict[str, set[str]] = {}


def homunculus_version(ctx: RunContext) -> str:
    if not ctx.artifact_exists("run_meta.json"):
        return "0.0.0"
    meta = ctx.read_json("run_meta.json") or {}
    return str(meta.get("homunculus_version") or "0.0.0")


def is_homunculus_run(ctx: RunContext) -> bool:
    return is_homunculus_brain(homunculus_version(ctx))


def dispatch_stage(
    ctx: RunContext,
    stage: str,
    impl: Callable[[], None],
    *,
    source: str = "conductor",
) -> None:
    """Budget + serialize + ledger, then host impl, then admit. 0.1.0 only."""
    identity = stage
    inflight = _INFLIGHT.setdefault(ctx.run_id, set())
    check_dispatch(ctx, identity=identity, kind="stage")
    check_audio_serialize(ctx, identity, inflight)
    append_ledger(
        ctx,
        {
            "kind": "stage",
            "identity": identity,
            "source": source,
            "status": "started",
        },
    )
    inflight.add(identity)
    try:
        impl()
    except Exception as exc:
        inflight.discard(identity)
        issue = emit_issue(
            ctx,
            kind="stage_failure",
            source=source,
            stage_id=stage,
            implicated=[stage],
            evidence={"error_class": type(exc).__name__, "message": str(exc)[:400]},
        )
        append_ledger(
            ctx,
            {
                "kind": "stage",
                "identity": identity,
                "status": "failed",
                "issue_id": issue.get("issue_id"),
            },
        )
        raise
    inflight.discard(identity)
    admit(ctx, identity=identity, action="keep", payload={"stage": stage, "source": source})
    append_ledger(ctx, {"kind": "stage", "identity": identity, "status": "done", "source": source})


def recovery_allowed(ctx: RunContext, stage: str) -> bool:
    """0.1.0: recovery playbook only after an analysis exists for this stage failure."""
    if not is_homunculus_run(ctx):
        return True
    from interview_mux.homunculus.issues import read_issues

    for issue in read_issues(ctx):
        if issue.get("stage_id") == stage and has_analysis(ctx, str(issue.get("issue_id"))):
            return True
    return False


def snapshot_status(ctx: RunContext) -> dict[str, Any]:
    from interview_mux.homunculus.admit import read_admitted, read_memory
    from interview_mux.homunculus.budget import snapshot as budget_snapshot
    from interview_mux.homunculus.issues import read_issues
    from interview_mux.homunculus.ledger import last_fact_ids, read_ledger

    packs = []
    pack_dir = ctx.path("mastering/homunculus/volley_packs")
    if pack_dir.is_dir():
        packs = sorted(p.name for p in pack_dir.glob("*.json"))[-8:]
    exhausted = None
    if ctx.artifact_exists("mastering/homunculus/limit_exhausted.json"):
        exhausted = ctx.read_json("mastering/homunculus/limit_exhausted.json")
    from interview_mux.homunculus.gates import category_status

    kb_lessons = 0
    last_implicated: list[Any] = []
    musicgen: dict[str, Any] = {}
    try:
        from interview_mux.homunculus.kb import lessons, read_kb

        rows = lessons(ctx)
        kb_lessons = len(rows)
        if rows:
            last_implicated = list((rows[-1] or {}).get("implicated_groups") or [])
        musicgen = dict(read_kb(ctx).get("musicgen") or {})
    except Exception:
        pass
    return {
        "homunculus_version": homunculus_version(ctx),
        "active": is_homunculus_run(ctx),
        "budget": budget_snapshot(ctx),
        "issues": read_issues(ctx)[-12:],
        "admitted_tail": read_admitted(ctx)[-12:],
        "memory_fact_count": len(read_memory(ctx).get("facts") or []),
        "last_fact_ids": last_fact_ids(ctx),
        "recent_packs": packs,
        "ledger_len": len(read_ledger(ctx)),
        "limit_exhausted": exhausted,
        "gates": category_status(ctx),
        "kb_lessons": kb_lessons,
        "last_implicated": last_implicated,
        "musicgen": musicgen,
    }
