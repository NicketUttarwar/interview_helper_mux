"""Self-correction backstops: refusal feedback for the model, declared fallback at the cap.

Two rules the maintainer asked for (ISSUES 124), both bounded and recorded:

1. **Refusal feedback.** When the pre-flush commit barrier refuses a stage's
   staged artifact, the refusal reasons are written to
   ``operator/refusal_feedback/<stage>.json``. The next run of that LLM stage
   reads them once and appends them to the model's user turn, so the retry is
   told exactly what was refused instead of re-rolling blind. Each distinct
   reason set is fed back once; a second identical refusal falls through to
   the deterministic sanitizers and, at the cap, to the fallback below.

2. **Declared fallback at the identical-failure cap.** When a stage fails
   identically for the third time, the walk used to halt and leave the run
   for an operator. If the stage's primary artifact already exists in the
   committed tree and is acceptable (the old version, from a previous pass
   or a previous run of the stage), the engine keeps it, marks the stage
   done through the heal ladder, records the decision in
   ``operator/fallback_decisions.jsonl``, and continues. Without an old
   version there is nothing honest to fall back to, and the halt stands.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FEEDBACK_DIR = "operator/refusal_feedback"
DECISIONS_REL = "operator/fallback_decisions.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reasons_hash(reasons: list[str]) -> str:
    blob = "\n".join(sorted(str(r).strip() for r in reasons if str(r).strip()))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _feedback_path(ctx: Any, stage: str) -> Path:
    return Path(ctx.run_dir) / FEEDBACK_DIR / f"{stage}.json"


def _read(path: Path) -> dict[str, Any]:
    try:
        if path.is_file():
            doc = json.loads(path.read_text(encoding="utf-8"))
            return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        pass
    return {}


def _write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def note_refusal(ctx: Any, stage: str, reasons: list[str]) -> dict[str, Any]:
    """Record the barrier's reasons for ``stage`` so its next run can read them."""
    clean = [str(r).strip()[:400] for r in reasons if str(r).strip()]
    clean = [r for r in clean if not r.startswith("heal_success:")]
    if not clean:
        return {}
    path = _feedback_path(ctx, stage)
    prev = _read(path)
    doc = {
        "stage": stage,
        "reasons": clean[:12],
        "hash": _reasons_hash(clean),
        "refusals": int(prev.get("refusals") or 0) + 1,
        "consumed_hashes": list(prev.get("consumed_hashes") or [])[-8:],
        "at": _now(),
    }
    try:
        _write(path, doc)
    except OSError:
        return {}
    return doc


def take_refusal_feedback(ctx: Any, stage: str) -> list[str]:
    """Reasons to feed the model once per distinct refusal; empty when none or already fed."""
    path = _feedback_path(ctx, stage)
    doc = _read(path)
    reasons = [str(r) for r in (doc.get("reasons") or []) if str(r).strip()]
    if not reasons:
        return []
    h = str(doc.get("hash") or _reasons_hash(reasons))
    consumed = [str(x) for x in (doc.get("consumed_hashes") or [])]
    if h in consumed:
        return []
    doc["consumed_hashes"] = (consumed + [h])[-8:]
    doc["consumed_at"] = _now()
    try:
        _write(path, doc)
    except OSError:
        return []
    return reasons


def clear_refusal_feedback(ctx: Any, stage: str) -> None:
    try:
        _feedback_path(ctx, stage).unlink(missing_ok=True)
    except OSError:
        pass


def feedback_note(reasons: list[str]) -> str:
    """The text appended to the model's user turn."""
    lines = "\n".join(f"- {r}" for r in reasons[:12])
    return (
        "\n\n---\nPREVIOUS ATTEMPT REFUSED: the commit barrier rejected the last "
        "artifact for the reasons below. Fix exactly these in this reply and keep "
        "everything else the same.\n" + lines
    )


def record_fallback_decision(ctx: Any, decision: dict[str, Any]) -> None:
    path = Path(ctx.run_dir) / DECISIONS_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({**decision, "at": _now()}) + "\n")
    except OSError:
        pass


def prior_committed_artifact(ctx: Any, stage: str) -> str | None:
    """The stage's primary artifact when it exists committed and is acceptable."""
    try:
        from interview_mux.llm_flow_hardening import producer_artifact_path
        from interview_mux.llm_output_resilience import upstream_artifact_acceptable
    except Exception:
        return None
    rel = producer_artifact_path(stage)
    if not rel:
        return None
    try:
        if not (Path(ctx.run_dir) / rel).is_file():
            return None
        if not upstream_artifact_acceptable(stage, rel, ctx):
            return None
    except Exception:
        return None
    return str(rel)


def _skip_stub_delivery_brief(ctx: Any, stage: str) -> None:
    from interview_mux.delivery_brief import persist_delivery_brief_skip_stub

    persist_delivery_brief_skip_stub(ctx)


def _skip_stub_episode_structure(ctx: Any, stage: str) -> None:
    from interview_mux.episode_structure import persist_structure_skip_stub

    persist_structure_skip_stub(ctx)


def _skip_stub_pass2(ctx: Any, stage: str) -> None:
    from interview_mux.refinement_passes import persist_pass2_skip_stub

    persist_pass2_skip_stub(ctx, stage, skip_reason="fallback_at_identical_failure_cap")


#: Stages the pipeline already knows how to run without (each has a schema-valid
#: skip stub the downstream readers accept). At the cap, with no old version to
#: keep, the stage is skipped through its stub and the decision recorded.
#: Stages the master cannot do without (ranking, EDL, mix, master) are not here.
OPTIONAL_STAGE_SKIP_STUBS: dict[str, Any] = {
    "delivery_brief_build": _skip_stub_delivery_brief,
    "episode_structure_compose": _skip_stub_episode_structure,
    "gap_framing_recompose": _skip_stub_pass2,
    "selection_framing_apply": _skip_stub_pass2,
}


def _mark_through_heal(ctx: Any, stage: str) -> bool:
    try:
        if ctx.is_done(stage):
            return True
        from interview_mux.stage_completion import heal_or_refuse_mark

        out = heal_or_refuse_mark(ctx, stage, force=True)
        return bool(ctx.is_done(stage)) or bool(isinstance(out, dict) and out.get("marked"))
    except Exception:
        return False


def apply_declared_fallback(ctx: Any, stage: str, reason: str) -> dict[str, Any] | None:
    """At the identical-failure cap: keep the old version, else skip an optional stage.

    Returns the recorded decision when the stage ended done; None when neither
    rung applies, in which case the halt stands.
    """
    rel = prior_committed_artifact(ctx, stage)
    if not rel:
        stub = OPTIONAL_STAGE_SKIP_STUBS.get(str(stage or ""))
        if stub is None:
            return None
        try:
            stub(ctx, stage)
        except Exception as exc:  # noqa: BLE001 - a stub that cannot land is no fallback
            try:
                ctx.log(
                    f"fallback: skip stub for {stage} failed: {type(exc).__name__}: {str(exc)[:120]}",
                    level="warning",
                    stage=stage,
                )
            except Exception:
                pass
            return None
        if not _mark_through_heal(ctx, stage):
            return None
        decision = {
            "stage": stage,
            "fallback": "skip_stub",
            "artifact": None,
            "reason": str(reason or "")[:300],
        }
        record_fallback_decision(ctx, decision)
        clear_refusal_feedback(ctx, stage)
        try:
            ctx.log(
                f"fallback: skipped {stage} through its stub after identical failures "
                f"({str(reason or '')[:120]})",
                level="warning",
                stage=stage,
                action_id="fallback.skip_stub",
                detail=decision,
            )
        except Exception:
            pass
        return decision
    try:
        if ctx.is_done(stage):
            marked = True
        else:
            from interview_mux.stage_completion import heal_or_refuse_mark

            out = heal_or_refuse_mark(ctx, stage, force=True)
            marked = bool(ctx.is_done(stage)) or bool(isinstance(out, dict) and out.get("marked"))
    except Exception:
        marked = False
    if not marked:
        return None
    decision = {
        "stage": stage,
        "fallback": "keep_prior_committed_artifact",
        "artifact": rel,
        "reason": str(reason or "")[:300],
    }
    record_fallback_decision(ctx, decision)
    clear_refusal_feedback(ctx, stage)
    try:
        ctx.log(
            f"fallback: kept prior committed {rel} for {stage} after identical failures "
            f"({str(reason or '')[:120]})",
            level="warning",
            stage=stage,
            action_id="fallback.keep_prior",
            detail=decision,
        )
    except Exception:
        pass
    return decision
