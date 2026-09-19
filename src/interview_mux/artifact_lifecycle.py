"""Artifact lifecycle: fingerprints, post-commit validation, reuse, stale reads."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from interview_mux.artifact_dependency_graph import transitive_invalidate
from interview_mux.config import merged_config
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS


class LifecyclePhase(str, Enum):
    PRESTAGE = "prestage"
    PRE_CALL = "pre_call"
    LLM_EXECUTE = "llm_execute"
    STAGED_WRITE = "staged_write"
    STAGED_VALIDATE = "staged_validate"
    AWAITING_APPROVAL = "awaiting_approval"
    COMMITTED = "committed"
    POST_COMMIT_VALIDATE = "post_commit_validate"
    CONSUMED = "consumed"
    INVALIDATED = "invalidated"


def lifecycle_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "fingerprint_enabled": True,
        "post_commit_validate": True,
        "read_stale_guard": True,
        "reuse_validate": True,
    }
    return {**defaults, **(analysis.get("artifact_lifecycle") or {})}


def fingerprint_artifact(artifact: dict[str, Any], stage_key: str) -> dict[str, Any]:
    out = copy.deepcopy(artifact)
    body = {k: v for k, v in out.items() if k != "_meta"}
    raw = json.dumps(body, sort_keys=True, default=str)
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    meta = dict(out.get("_meta") or {})
    meta.update(
        {
            "producer_stage": stage_key,
            "content_hash": h,
            "committed_at": datetime.now(timezone.utc).isoformat(),
            "stale": False,
        }
    )
    meta.pop("stale_reason", None)
    out["_meta"] = meta
    return out


def content_fingerprint(ctx: Any, rel: str) -> str:
    """TH3: live content hash for an on-disk artifact (JSON body or file bytes).

    Fail-closed callers compare this to ``run_meta.artifact_fingerprints[rel]``.
    Returns empty string only when the path is missing/unreadable.
    """
    path = str(rel or "").replace("\\", "/").lstrip("/")
    if not path or not hasattr(ctx, "artifact_exists") or not ctx.artifact_exists(path):
        return ""
    try:
        if path.endswith(".json"):
            doc = ctx.read_json(path)
            if not isinstance(doc, dict):
                return ""
            meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
            fp = fingerprint_artifact(
                doc, str((meta or {}).get("producer_stage") or "read")
            )
            return str((fp.get("_meta") or {}).get("content_hash") or "")
        if hasattr(ctx, "final_path"):
            fpath = ctx.final_path(*path.split("/"))
        else:
            fpath = None
        if fpath is None or not getattr(fpath, "is_file", lambda: False)():
            return ""
        h = hashlib.sha256()
        with open(fpath, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except Exception:
        return ""


def compare_content_fingerprint(ctx: Any, rel: str, stored: Any) -> tuple[bool, str]:
    """Return (ok, reason). Fail-closed when stored fingerprint disagrees with live.

    ``stored`` may be a bare hash string or ``{"hash": "..."}`` entry from run_meta.
    """
    path = str(rel or "").replace("\\", "/").lstrip("/")
    if not path:
        return False, "empty_rel"
    if isinstance(stored, dict):
        expected = str(stored.get("hash") or stored.get("content_hash") or "")
    else:
        expected = str(stored or "")
    if not expected:
        return True, ""
    live = content_fingerprint(ctx, path)
    if not live:
        return False, "fingerprint_unreadable"
    if live != expected:
        return False, "fingerprint_mismatch"
    return True, ""


def _record_fingerprint(ctx: Any, rel: str, content_hash: str, stage_key: str) -> None:
    def _mut(meta: dict[str, Any]) -> None:
        fps = dict(meta.get("artifact_fingerprints") or {})
        fps[rel] = {"hash": content_hash, "producer_stage": stage_key}
        meta["artifact_fingerprints"] = fps

    if hasattr(ctx, "mutate_run_meta"):
        ctx.mutate_run_meta(_mut)


def restamp_committed_artifact(
    ctx: Any,
    rel: str,
    *,
    producer_stage: str,
    doc: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Fingerprint + write + record so consumer stale guards match the on-disk body.

    Used after nested stage commits and after heals that rewrite an artifact
    outside its producer stage's flush list (e.g. content_brief id remap).
    """
    if doc is None:
        if not ctx.artifact_exists(rel):
            return None
        raw = ctx.read_json(rel)
        if not isinstance(raw, dict):
            return None
        doc = raw
    fp = fingerprint_artifact(doc, producer_stage)
    ctx.write_json(rel, fp, stage_key=producer_stage, skip_handoff=True)
    h = str((fp.get("_meta") or {}).get("content_hash") or "")
    if h:
        _record_fingerprint(ctx, rel, h, producer_stage)
    return fp


def post_commit_validate(ctx: Any, stage_key: str) -> list[str]:
    if not lifecycle_cfg().get("post_commit_validate", True):
        return []
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel or not ctx.artifact_exists(rel):
        return []
    from interview_mux.stage_acceptance import stage_acceptance_ok

    result = stage_acceptance_ok(ctx, stage_key, staged=False, include_downstream=False)
    errors = list(result.all_errors or [])
    if stage_key == "vo_synthesize":
        try:
            from interview_mux.vo_contract import assert_seated_vo_rendered

            assert_seated_vo_rendered(ctx)
        except RuntimeError as exc:
            errors.append(str(exc))
    elif stage_key == "edl_narrative_audit":
        try:
            from interview_mux.vo_contract import validate_vo_contract

            errors.extend(validate_vo_contract(ctx)[:3])
        except Exception:
            pass
    elif stage_key == "assembly_preview":
        wav = ctx.final_path("master", "assembly_preview.wav")
        if not wav.is_file():
            errors.append("assembly_preview.wav missing on disk")
    if stage_key == "transitions" and any(
        "redundant with framing VO" in str(e) for e in errors
    ):
        try:
            from interview_mux.gap_framing import heal_redundant_framing_transitions

            healed = heal_redundant_framing_transitions(ctx)
            if healed.get("dropped"):
                result = stage_acceptance_ok(
                    ctx, stage_key, staged=False, include_downstream=False
                )
                errors = list(result.all_errors or [])
        except Exception:
            pass
    if stage_key == "gap_framing_compose" and any(
        "has no interviewer line" in str(e) for e in errors
    ):
        try:
            from interview_mux.high_gap_vo import resolve_seats

            report = (
                ctx.read_json("understanding/gap_report.json")
                if ctx.artifact_exists("understanding/gap_report.json")
                else {"interviewer_lines": []}
            )
            resolution = resolve_seats(
                ctx,
                intent="compose_persist",
                gap_report=report if isinstance(report, dict) else None,
            )
            if resolution.demoted:
                result = stage_acceptance_ok(
                    ctx, stage_key, staged=False, include_downstream=False
                )
                errors = list(result.all_errors or [])
        except Exception:
            pass
    return errors


def read_stale_guard(ctx: Any, rel: str, *, consumer_stage: str) -> str | None:
    if not lifecycle_cfg().get("read_stale_guard", True):
        return None
    if not ctx.artifact_exists(rel):
        return None
    # Binary media: never UTF-8 / JSON-decode (Wave 3 durable).
    if str(rel).lower().endswith((".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".png", ".jpg")):
        return None
    # The producing stage may rewrite its own stale file (rerun / self-heal).
    if STAGE_ARTIFACT_DISK_PATHS.get(consumer_stage) == rel:
        return None
    try:
        from interview_mux.file_store import read_json as fs_read_json
        from interview_mux.write_staging import resolve_read_path

        committed = ctx.final_path(*rel.split("/"))
        if committed.is_file():
            doc = fs_read_json(committed)
        else:
            doc = fs_read_json(resolve_read_path(ctx, rel))
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    meta = doc.get("_meta") or {}
    if meta.get("stale"):
        reason = str(meta.get("stale_reason") or "")
        if reason == f"invalidated_by:{consumer_stage}":
            # A stage must not deadlock on a stale stamp it just wrote.
            return None
        # Producer rewriting its own disk path after upstream invalidation
        # (e.g. transitions resume while transitions.json still marked stale
        # by nugget_layup_compose) — clear stamp and allow regenerate.
        producer_rel = STAGE_ARTIFACT_DISK_PATHS.get(str(consumer_stage or ""))
        if producer_rel and producer_rel == rel:
            meta = dict(meta)
            meta.pop("stale", None)
            meta.pop("stale_reason", None)
            doc = dict(doc)
            doc["_meta"] = meta
            try:
                ctx.write_json(rel, doc, skip_handoff=True)
            except Exception:
                pass
            return None
        if rel == "understanding/content_brief.json" and reason.startswith("invalidated_by:"):
            from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

            from_stage = reason.split(":", 1)[-1]
            order = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
            if (
                from_stage in order
                and "content_brief_reanchor" in order
                and order.index(from_stage) < order.index("content_brief_reanchor")
            ):
                # Shared path: boundary_detection must not stale the pre-reanchor brief.
                meta.pop("stale", None)
                meta.pop("stale_reason", None)
                doc["_meta"] = meta
                try:
                    ctx.write_json(rel, doc, skip_handoff=True)
                except Exception:
                    pass
                return None
        return f"{rel} is marked stale ({reason or 'upstream fix'})"
    stored = {}
    if ctx.artifact_exists("run_meta.json"):
        try:
            meta_path = resolve_read_path(ctx, "run_meta.json")
            stored = (fs_read_json(meta_path) or {}).get("artifact_fingerprints") or {}
        except Exception:
            stored = {}
    entry = stored.get(rel) or {}
    if entry.get("hash") and meta.get("content_hash") and entry["hash"] != meta["content_hash"]:
        producer = str(entry.get("producer_stage") or consumer_stage or "")
        try:
            restamped = restamp_committed_artifact(
                ctx, rel, producer_stage=producer, doc=doc
            )
            if restamped is not None:
                return None
        except Exception:
            pass
        return f"{rel} fingerprint mismatch — re-run producer {entry.get('producer_stage')}"
    return None


def validate_reuse_copy(ctx: Any, stage_key: str, source_run_id: str) -> list[str]:
    if not lifecycle_cfg().get("reuse_validate", True):
        return []
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_key)
    if not rel or not ctx.artifact_exists(rel):
        return [f"reuse missing artifact {rel}"]
    from interview_mux.prompt_validation import validate_artifact_write
    from interview_mux.sufficiency_engine import evaluate

    doc = ctx.read_json(rel)
    if not isinstance(doc, dict):
        return [f"reuse invalid json {rel}"]
    errors = list(validate_artifact_write(rel, doc) or [])
    evaluated = evaluate(stage_key, doc, ctx)
    findings = evaluated.get("findings") if isinstance(evaluated, dict) else evaluated
    for f in findings or []:
        blocking = getattr(f, "blocking", None)
        if blocking is None and isinstance(f, dict):
            blocking = f.get("blocking")
        if blocking:
            message = getattr(f, "message", None) or (f.get("message") if isinstance(f, dict) else str(f))
            if message:
                errors.append(str(message))
    return errors


def invalidate_downstream_memory(ctx: Any, from_stage: str) -> list[str]:
    """Bundle stale stamps, volley index invalidation, and stage summary clears on redo."""
    stamped = stamp_stale_and_archive(ctx, from_stage)
    downstream = tuple(transitive_invalidate(from_stage))
    if downstream:
        from interview_mux.artifact_cross_validate import invalidate_stage_summaries
        from interview_mux.context_resolver import invalidate_entries_for_stages

        invalidate_stage_summaries(ctx, downstream)
        invalidate_entries_for_stages(ctx, downstream)
    _record_invalidation_epoch(ctx, from_stage, downstream)
    return stamped


def _record_invalidation_epoch(ctx: Any, from_stage: str, downstream: tuple[str, ...]) -> None:
    """Stamp the invalidation epoch (plan §5.4 rail 2). Observer only — never raises.

    `RunContext.clear_from` funnels both of its branches through
    `invalidate_downstream_memory`, so this is the one place every real
    invalidation passes. `master_qc.verify_master` reads what it writes and
    refuses a master that predates the epoch.
    """
    try:
        from interview_mux.artifact_dependency_graph import precision_eligible
        from interview_mux.master_epoch import record_invalidation

        record_invalidation(
            ctx,
            from_stage,
            downstream,
            mode="precise" if precision_eligible(from_stage) else "blanket",
        )
    except Exception:
        return


def stamp_stale_and_archive(ctx: Any, from_stage: str) -> list[str]:
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    order = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    from_idx = order.index(from_stage) if from_stage in order else -1
    stamped: list[str] = []
    # Respect delivery blast radius — do not false-stale out-of-blast artifacts (esp. SDP).
    blast: frozenset[str] | None = None
    try:
        from interview_mux.delivery_guardrails import (
            INVALIDATION_BLAST_RADIUS,
            music_clear_blocked,
        )

        blast = INVALIDATION_BLAST_RADIUS.get(from_stage)
    except Exception:
        music_clear_blocked = None  # type: ignore[assignment]
        blast = None
    for sid in transitive_invalidate(from_stage):
        if blast is not None and sid not in blast:
            continue
        try:
            if music_clear_blocked is not None and music_clear_blocked(
                ctx, sid, source=from_stage
            ):
                continue
        except Exception:
            pass
        rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
        if not rel or not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
            if isinstance(doc, dict):
                meta = dict(doc.get("_meta") or {})
                producer = str(meta.get("producer_stage") or "")
                if (
                    from_idx >= 0
                    and producer in order
                    and order.index(producer) < from_idx
                ):
                    # Shared disk paths (content_brief, boundaries) must not
                    # stale an upstream producer when a later alias is downstream.
                    continue
                # Never self-stale the from_stage's own disk path. Shared aliases
                # (boundary_detection / boundary_topic_resplit → boundaries.json)
                # otherwise stamp invalidated_by:boundary_detection while the
                # agenda skips BD and walks segment_classification first.
                if STAGE_ARTIFACT_DISK_PATHS.get(from_stage) == rel:
                    continue
                if (
                    rel == "understanding/content_brief.json"
                    and "content_brief_reanchor" in order
                    and from_idx >= 0
                    and from_idx < order.index("content_brief_reanchor")
                ):
                    # Reanchor shares content_brief.json with content_context.
                    # Re-running boundary_detection must not stale the still-valid
                    # pre-reanchor brief (that deadlock blocked boundaries forever).
                    continue
                meta["stale"] = True
                meta["stale_reason"] = f"invalidated_by:{from_stage}"
                doc["_meta"] = meta
                ctx.write_json(rel, doc, stage_key=sid, skip_handoff=True)
                stamped.append(rel)
        except Exception:
            continue
    try:
        consumers = transitive_invalidate(from_stage)
        for sid in consumers:
            rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
            if rel in stamped and ctx.is_done(sid):
                (Path(ctx.run_dir) / ".stage_done" / sid).unlink(missing_ok=True)
            # Belt: always clear transitions done when its artifact was staled.
            if sid == "transitions" and rel in stamped:
                (Path(ctx.run_dir) / ".stage_done" / "transitions").unlink(missing_ok=True)
                try:
                    from interview_mux.seat_authority import (
                        hard_freeze_active,
                        soft_freeze_active,
                    )
                    from interview_mux.transition_vo import clear_transitions_pair_freeze

                    # b9: do not blind-clear pair freeze while seats are frozen
                    if soft_freeze_active(ctx) or hard_freeze_active(ctx):
                        pass
                    else:
                        clear_transitions_pair_freeze(ctx)
                except Exception:
                    pass
                try:
                    from interview_mux.delivery_guardrails import record_wasted_work

                    record_wasted_work(
                        ctx,
                        event="invalidate_schedule_producer",
                        stage="transitions",
                        detail={
                            "invalidated_by": from_stage,
                            "resume_stage": "transitions",
                        },
                    )
                except Exception:
                    pass
    except Exception:
        pass
    return stamped


def apply_fingerprints_on_flush(ctx: Any, stage_key: str, flushed_paths: list[str]) -> None:
    if not lifecycle_cfg().get("fingerprint_enabled", True):
        return
    from interview_mux.stage_acceptance import BINARY_ARTIFACT_SUFFIXES as _binary_suffixes
    for rel in flushed_paths:
        if rel not in STAGE_ARTIFACT_DISK_PATHS.values():
            continue
        if not ctx.artifact_exists(rel):
            continue
        # Producer outputs may be binary (mix → assembly.wav). Never read_json them.
        if str(rel).lower().endswith(_binary_suffixes):
            continue
        try:
            doc = ctx.read_json(rel)
            if isinstance(doc, dict):
                fp = fingerprint_artifact(doc, stage_key)
                ctx.write_json(rel, fp, stage_key=stage_key, skip_handoff=True)
                h = (fp.get("_meta") or {}).get("content_hash")
                if h:
                    _record_fingerprint(ctx, rel, str(h), stage_key)
        except Exception as exc:
            try:
                ctx.log(
                    f"fingerprint flush skipped for {rel}: {exc}",
                    level="warning",
                    stage=stage_key,
                )
            except Exception:
                pass
            continue


MISSING_HARD_INPUT_BLOCKER = "missing_hard_input"
_ENV_HARD_INPUT_STRICT = "MUX_CONTRACT_HARD_INPUT_STRICT"
_PRESTAGE_REFUSAL_ATTR = "_prestage_refusals"


def hard_input_strict() -> bool:
    """Is an absent declared hard input fatal at `PRESTAGE`? Default **NO**.

    Contract population is in flight, and a hard input on a conditionally produced
    artifact is the likely mistake: `audio_preclean` may be marked done with only
    `preclean/skip.json` on disk while its primary is `preclean/isolated.wav`, so a
    contract naming that primary would crash every skipped-preclean run. Under the
    live default brain a crash is strictly worse than a recorded refusal, so the
    default is lenient and `MUX_CONTRACT_HARD_INPUT_STRICT=1` restores the old
    fatal behaviour for CI and forensics runs that *want* to fail loudly.
    """
    return str(os.environ.get(_ENV_HARD_INPUT_STRICT) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _missing_hard_input(
    ctx: Any,
    stage_key: str,
    rel: str,
    *,
    producer: str | None = None,
    phase: LifecyclePhase = LifecyclePhase.PRESTAGE,
) -> str | None:
    """Handle an absent declared hard input. Returns a fatal message, or None.

    The refusal path is the established "cannot proceed, record it, do not crash"
    machinery: a `defect_ledger` row (so the walk can advance while `master.wav`
    stays reachable, and so PMQ sees a ship-bar risk on the critical path) plus a
    `stage_resilience` event and an operator-visible warning. Nothing is silent;
    what changes is refusal instead of exception.
    """
    message = f"missing input {rel} for {stage_key}"
    if hard_input_strict():
        return message
    detail = {
        "artifact": rel,
        "producer": str(producer or ""),
        "phase": phase.value,
        "cause": "absent",
    }
    try:
        from interview_mux.defect_ledger import record_defect

        record_defect(
            ctx,
            stage=stage_key,
            blocker=MISSING_HARD_INPUT_BLOCKER,
            artifact=rel,
            detail=detail,
        )
    except Exception:
        pass
    try:
        from interview_mux.stage_resilience import record_resilience_event

        record_resilience_event(
            ctx,
            stage_key,
            event="prestage_missing_hard_input",
            action="refuse",
            reasons=[message],
            detail=detail,
        )
    except Exception:
        pass
    try:
        ctx.log(
            f"{stage_key}: declared hard input {rel} is absent — recorded as "
            f"{MISSING_HARD_INPUT_BLOCKER} (not raising; "
            f"{_ENV_HARD_INPUT_STRICT}=1 to make it fatal)",
            level="warning",
            stage=stage_key,
        )
    except Exception:
        pass
    if phase == LifecyclePhase.PRESTAGE:
        _note_prestage_refusal(ctx, stage_key, {**detail, "blocker": MISSING_HARD_INPUT_BLOCKER})
    return None


def _refusal_memo(ctx: Any) -> dict[str, list[dict[str, Any]]] | None:
    memo = getattr(ctx, _PRESTAGE_REFUSAL_ATTR, None)
    if isinstance(memo, dict):
        return memo
    memo = {}
    try:
        setattr(ctx, _PRESTAGE_REFUSAL_ATTR, memo)
    except Exception:
        return None
    return memo


def _note_prestage_refusal(ctx: Any, stage_key: str, detail: dict[str, Any]) -> None:
    memo = _refusal_memo(ctx)
    if memo is None:
        return
    memo.setdefault(stage_key, []).append(dict(detail))


def prestage_refusals(ctx: Any, stage_key: str) -> tuple[dict[str, Any], ...]:
    """What the most recent `PRESTAGE` evaluation of `stage_key` refused on.

    Per-process and re-derived by every evaluation, deliberately not read back
    from the defect ledger: a ledger row stays open until the stage produces, so
    a stage refused once would keep looking refused after its input arrived.
    """
    memo = getattr(ctx, _PRESTAGE_REFUSAL_ATTR, None)
    if not isinstance(memo, dict):
        return ()
    rows = memo.get(stage_key)
    return tuple(rows) if isinstance(rows, list) else ()


def prestage_refused(ctx: Any, stage_key: str) -> bool:
    """Did this stage's last `PRESTAGE` evaluation refuse it? Consumes the refusal.

    The second channel `run_single_stage` needs. `run_phase_checks` can only
    *return errors*, and an error there becomes a `ValueError`, so a lenient
    refusal had no way to stop the stage — it recorded the defect and ran on.
    True here means "recorded, cannot proceed, do not raise": the caller returns.

    Routed through `dispatch_door.refuse_dispatch` for the same reason a cap or
    no-delta refusal is: one defect row keyed on the output that will not appear,
    one attempt-memo row so the walk stops re-offering a stage whose state has
    not changed (self-invalidating — the memo lapses the moment the missing input
    lands), one homunculus ledger row, one reachability line. `refuse_dispatch`
    never raises and `MISSING_HARD_INPUT_BLOCKER` is deliberately absent from
    `ship_reachability.TERMINAL_BLOCKERS`, so a spurious declaration cannot sever
    reachability.

    This is not the only thing stopping a stage that cannot run: the downstream
    rails (`stage_input_checks.require_stage_inputs`, seed order,
    `llm_flow_hardening`, each stage body's labelled reads) still cover every case
    a contract does not declare. This channel only makes a *declared* refusal
    clean instead of a crash.
    """
    rows = prestage_refusals(ctx, stage_key)
    if not rows:
        return False
    memo = getattr(ctx, _PRESTAGE_REFUSAL_ATTR, None)
    if isinstance(memo, dict):
        memo.pop(stage_key, None)
    artifacts = [str(row.get("artifact") or "") for row in rows if row.get("artifact")]
    try:
        from interview_mux.dispatch_door import DispatchVerdict, refuse_dispatch

        refuse_dispatch(
            ctx,
            stage_key,
            DispatchVerdict(
                False,
                MISSING_HARD_INPUT_BLOCKER,
                {"stage": stage_key, "inputs": artifacts, "refusals": list(rows)},
            ),
            source="prestage",
        )
    except Exception:
        pass
    try:
        ctx.log(
            f"{stage_key}: refused before start — declared hard input(s) "
            f"{', '.join(artifacts[:4]) or 'absent'} missing",
            level="warning",
            stage=stage_key,
        )
    except Exception:
        pass
    return True


def run_phase_checks(ctx: Any, stage_key: str, phase: LifecyclePhase) -> list[str]:
    """Pre-stage / pre-call lifecycle gates.

    An error returned from the `PRESTAGE` phase becomes a `ValueError` in
    `pipeline.run_single_stage`, so what goes in this list decides whether a
    declared dependency can crash a live run. Two causes, deliberately handled
    differently — see `_missing_hard_input`:

    * **absent** — upstream has not produced it (yet, or at all on this tape).
      Recorded as a defect and a resilience event; never fatal by default.
    * **stale stamp** — produced and then invalidated. A genuine ordering
      problem, still fatal, and independently enforced by
      `delivery_guardrails.upstream_stale_blockers` on the same code path.

    A lenient refusal is also published on `ctx` for `prestage_refused`, which is
    how `run_single_stage` stops the stage without raising. Each `PRESTAGE`
    evaluation clears this stage's refusals first, so the answer always describes
    the tree as it is now.
    """
    errors: list[str] = []
    if phase == LifecyclePhase.PRESTAGE:
        memo = _refusal_memo(ctx)
        if memo is not None:
            memo.pop(stage_key, None)
    from interview_mux.stage_contract import evaluate_when, is_path_spec, load_contract

    contract = load_contract(stage_key)
    if contract:
        for inp in contract.inputs:
            if not inp.hard or not inp.path:
                continue
            # A declared family (`vo_pickup/`, `glob:...`) can never satisfy
            # `artifact_exists`, so treating one as a required file would refuse the
            # stage forever. Families are checked by sufficiency, not here.
            if is_path_spec(inp.path):
                continue
            try:
                required = evaluate_when(inp.when, ctx)
            except Exception:
                # An unevaluable condition is not evidence that the input is
                # required — `ship_reachability` makes the same call.
                required = False
            if not required:
                continue
            if not ctx.artifact_exists(inp.path):
                message = _missing_hard_input(
                    ctx, stage_key, inp.path, producer=inp.producer, phase=phase
                )
                if message:
                    errors.append(message)
                continue
            stale = read_stale_guard(ctx, inp.path, consumer_stage=stage_key)
            if stale:
                errors.append(stale)
    if phase == LifecyclePhase.PRESTAGE and errors:
        return errors
    # pre_call adds schema preflight for LLM stages
    if phase == LifecyclePhase.PRE_CALL:
        from interview_mux.llm_preflight import run_schema_preflight
        from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS

        if stage_key in STAGE_ARTIFACT_SCHEMAS:
            errors.extend(run_schema_preflight(stage_key, "primary"))
    return errors


def _artifact_lifecycle_phase(ctx: Any, rel: str, *, stage_id: str) -> str:
    from interview_mux.write_staging import has_pending_writes, staged_path

    if not rel:
        return "n_a"
    if not ctx.artifact_exists(rel):
        staged = staged_path(ctx, rel, stage_id=stage_id)
        if staged.is_file():
            return "staged"
        return "pending"
    try:
        doc = ctx.read_json(rel)
        meta = (doc.get("_meta") or {}) if isinstance(doc, dict) else {}
        if meta.get("stale"):
            return "invalidated"
    except (FileNotFoundError, OSError):
        return "pending"
    except Exception:
        pass
    if has_pending_writes(ctx, stage_id):
        staged = staged_path(ctx, rel, stage_id=stage_id)
        if staged.is_file():
            return "staged"
    return "committed"


def split_artifact_lists(
    ctx: Any, stage_id: str, artifacts: list[str]
) -> tuple[list[str], list[str], dict[str, str]]:
    committed: list[str] = []
    staged: list[str] = []
    lifecycle: dict[str, str] = {}
    for rel in artifacts:
        if not rel or rel.endswith("/"):
            continue
        phase = _artifact_lifecycle_phase(ctx, rel, stage_id=stage_id)
        lifecycle[rel] = phase
        if phase == "staged":
            staged.append(rel)
        elif phase in ("committed", "invalidated"):
            committed.append(rel)
    return committed, staged, lifecycle


def build_outputs_view(ctx: Any, stage_id: str) -> list[dict[str, Any]]:
    from interview_mux.web.stages import STAGE_BY_ID

    info = STAGE_BY_ID.get(stage_id)
    if not info:
        return []
    rows: list[dict[str, Any]] = []
    for rel in info.artifacts or []:
        if not rel or rel.endswith("/"):
            continue
        phase = _artifact_lifecycle_phase(ctx, rel, stage_id=stage_id)
        from interview_mux.artifact_completeness import artifact_status_for_stage
        from interview_mux.sufficiency_engine import evaluate, sufficiency_enabled

        suff = "ok"
        # Never read_json binary/audio — GUI snapshot would parse multi‑hundred‑MB WAVs.
        if (
            sufficiency_enabled()
            and ctx.artifact_exists(rel)
            and rel.endswith(".json")
        ):
            try:
                doc = ctx.read_json(rel)
                if isinstance(doc, dict):
                    blocking = [f for f in evaluate(stage_id, doc, ctx) if f.blocking]
                    suff = "blocking" if blocking else "ok"
            except Exception:
                suff = "unknown"
        rows.append(
            {
                "path": rel,
                "label": rel.split("/")[-1],
                "status": artifact_status_for_stage(rel, ctx, stage_id),
                "phase": phase,
                "kind": "artifact",
                "sufficiency_status": suff,
            }
        )
    return rows


def stage_output_mode(ctx: Any, stage_id: str) -> str:
    from interview_mux.web.stages import STAGE_BY_ID

    if stage_id == "audio_preclean":
        from interview_mux.stages.audio_preclean import preclean_was_skipped

        if ctx.is_done("audio_preclean") and preclean_was_skipped(ctx):
            return "optional_skipped"

    # N/A gates force-marked done must not T1-downgrade to incomplete via pending deps.
    if stage_id == "g1_5_preview_pickup":
        from interview_mux.gates_tbiy import g1_5_preview_pickup_enabled
        from interview_mux.production_profile import is_tbiy

        if not g1_5_preview_pickup_enabled() or not is_tbiy(ctx):
            return "optional_skipped"

    if stage_id in ("missing_framing", "optimal_questions", "g1_vo_pickup"):
        from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

        if gap_fill_was_skipped(ctx):
            return "optional_skipped"

    info = STAGE_BY_ID.get(stage_id)
    if not info or not info.artifacts:
        return "none"
    statuses = []
    for rel in info.artifacts:
        if rel and not rel.endswith("/"):
            statuses.append(_artifact_lifecycle_phase(ctx, rel, stage_id=stage_id))
    if not statuses:
        return "none"
    if all(s == "pending" for s in statuses):
        return "not_started"
    if any(s == "staged" for s in statuses):
        return "awaiting_approval"
    if all(s in ("committed", "n_a") for s in statuses):
        return "committed"
    return "partial"


__all__ = [
    "LifecyclePhase",
    "apply_fingerprints_on_flush",
    "build_outputs_view",
    "compare_content_fingerprint",
    "content_fingerprint",
    "fingerprint_artifact",
    "invalidate_downstream_memory",
    "lifecycle_cfg",
    "post_commit_validate",
    "read_stale_guard",
    "restamp_committed_artifact",
    "run_phase_checks",
    "split_artifact_lists",
    "stage_output_mode",
    "stamp_stale_and_archive",
    "validate_reuse_copy",
]
