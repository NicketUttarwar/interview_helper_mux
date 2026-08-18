"""Authoritative omit / suppress / defer / waive ledger for layup + G1 decisions.

Append/supersede only — never mutate prior active entries in place. Writers mint
new rows via ``mint_entry`` / ``supersede_entry`` and rebuild summaries with
``build_omit_ledger``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

OMIT_LEDGER_REL = "understanding/omit_ledger.json"

DECISION_KINDS = frozenset(
    {
        "segment_exclude",
        "layup_skip",
        "nugget_waive",
        "gap_line_skip",
        "suppress",
        "defer",
        "structural_omit",
        "asset_adjust",
    }
)
DECISIONS = frozenset({"omit", "defer", "suppress", "waive"})


def empty_omit_ledger() -> dict[str, Any]:
    return {
        "version": 1,
        "order_content_hash": None,
        "order_lock": None,
        "entries": [],
        "summary": {
            "active_count": 0,
            "by_kind": {},
            "unresolved_high_salience": 0,
            "compensated_count": 0,
        },
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _entry_id(kind: str, subject_id: str, seq: int) -> str:
    safe_kind = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in kind)
    safe_subj = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in subject_id)
    return f"omit_{safe_kind}_{safe_subj}_{seq}"


def summarize_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    active = 0
    compensated = 0
    unresolved_high = 0
    for row in entries:
        if not isinstance(row, dict) or not row.get("active"):
            continue
        active += 1
        kind = str(row.get("kind") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        path = str(row.get("compensating_path") or "").strip()
        if path:
            compensated += 1
        forgone = [str(x) for x in (row.get("value_forgone") or []) if x]
        if forgone and not path:
            unresolved_high += len(forgone)
    return {
        "active_count": active,
        "by_kind": by_kind,
        "unresolved_high_salience": unresolved_high,
        "compensated_count": compensated,
    }


def mint_entry(
    *,
    kind: str,
    subject_id: str,
    decision: str,
    reason_code: str,
    owner_stage: str,
    target_segment_id: str | None = None,
    rationale: str | None = None,
    evidence_refs: list[str] | None = None,
    value_forgone: list[str] | None = None,
    compensating_path: str | None = None,
    revisit_if: list[str] | None = None,
    decision_confidence: float | None = None,
    source_artifact: str | None = None,
    replacement_ref: str | None = None,
    operator_override: bool = False,
    provenance: dict[str, Any] | None = None,
    seq: int = 1,
) -> dict[str, Any]:
    if kind not in DECISION_KINDS:
        kind = "layup_skip"
    if decision not in DECISIONS:
        decision = "omit"
    return {
        "entry_id": _entry_id(kind, subject_id, seq),
        "kind": kind,
        "subject_id": str(subject_id),
        "target_segment_id": target_segment_id,
        "decision": decision,
        "reason_code": str(reason_code or "unspecified"),
        "rationale": rationale,
        "evidence_refs": list(evidence_refs or []),
        "value_forgone": list(value_forgone or []),
        "compensating_path": compensating_path,
        "revisit_if": list(revisit_if or []),
        "decision_confidence": decision_confidence,
        "owner_stage": str(owner_stage or "unknown"),
        "source_artifact": source_artifact,
        "replacement_ref": replacement_ref,
        "active": True,
        "superseded_by": None,
        "operator_override": bool(operator_override),
        "decided_at": _now_iso(),
        "provenance": provenance or {},
    }


def supersede_entry(
    ledger: dict[str, Any],
    *,
    subject_id: str,
    kind: str | None = None,
    replacement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mark matching active entries inactive; optionally append ``replacement``."""
    out = dict(ledger) if isinstance(ledger, dict) else empty_omit_ledger()
    entries = [dict(e) for e in (out.get("entries") or []) if isinstance(e, dict)]
    replacement_id = str((replacement or {}).get("entry_id") or "") or None
    for row in entries:
        if not row.get("active"):
            continue
        if str(row.get("subject_id") or "") != str(subject_id):
            continue
        if kind and str(row.get("kind") or "") != kind:
            continue
        row["active"] = False
        if replacement_id:
            row["superseded_by"] = replacement_id
    if replacement and isinstance(replacement, dict):
        entries.append(dict(replacement))
    out["entries"] = entries
    out["summary"] = summarize_entries(entries)
    return out


def active_entries(
    ledger: dict[str, Any] | None,
    *,
    kind: str | None = None,
    subject_id: str | None = None,
    target_segment_id: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(ledger, dict):
        return []
    out: list[dict[str, Any]] = []
    for row in ledger.get("entries") or []:
        if not isinstance(row, dict) or not row.get("active"):
            continue
        if kind and str(row.get("kind") or "") != kind:
            continue
        if subject_id and str(row.get("subject_id") or "") != subject_id:
            continue
        if target_segment_id and str(row.get("target_segment_id") or "") != target_segment_id:
            continue
        out.append(row)
    return out


def active_omit_for_target(
    ledger: dict[str, Any] | None, target_segment_id: str
) -> dict[str, Any] | None:
    rows = active_entries(
        ledger, kind="layup_skip", target_segment_id=str(target_segment_id)
    )
    if rows:
        return rows[-1]
    rows = active_entries(ledger, target_segment_id=str(target_segment_id))
    return rows[-1] if rows else None


def line_is_omitted(ledger: dict[str, Any] | None, line_id: str) -> bool:
    return bool(
        active_entries(ledger, kind="gap_line_skip", subject_id=str(line_id))
        or active_entries(ledger, kind="layup_skip", subject_id=str(line_id))
    )


def effective_air_contract(
    ledger: dict[str, Any] | None,
    *,
    line_id: str | None = None,
    target_segment_id: str | None = None,
) -> dict[str, Any]:
    """Return how delivery should treat a VO line / target.

    Outcomes:
    - ``required`` — no active omit; synthesize / keep
    - ``omitted`` — do not introduce VO
    - ``suppressed`` — replacement must be audible instead
    - ``deferred`` — G1-optional only
    """
    if line_id:
        for row in active_entries(ledger, subject_id=str(line_id)):
            decision = str(row.get("decision") or "omit")
            if decision == "suppress":
                return {
                    "status": "suppressed",
                    "entry": row,
                    "replacement_ref": row.get("replacement_ref"),
                }
            if decision == "defer":
                return {"status": "deferred", "entry": row}
            return {"status": "omitted", "entry": row}
    if target_segment_id:
        row = active_omit_for_target(ledger, target_segment_id)
        if row:
            decision = str(row.get("decision") or "omit")
            if decision == "suppress":
                return {
                    "status": "suppressed",
                    "entry": row,
                    "replacement_ref": row.get("replacement_ref"),
                }
            if decision == "defer":
                return {"status": "deferred", "entry": row}
            return {"status": "omitted", "entry": row}
    return {"status": "required", "entry": None}


def reconcile_edl_with_omit_ledger(
    ctx: RunContext,
    *,
    edl: dict[str, Any] | None = None,
    ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Drop audible VO clips that the omit ledger actively omits; retime EDL.

    Stale EDL can retain synthesized layup VO after a later typed skip stamps
    ``omit``. Post-master QC then fails ``omit_ledger_air_contract`` and
    ``audible_script_hash_agreement`` (missing gap script). Stripping keeps
    assembly authority aligned with the ledger without shipping canned air.
    """
    if ledger is None:
        ledger = (
            ctx.read_json(OMIT_LEDGER_REL)
            if ctx.artifact_exists(OMIT_LEDGER_REL)
            else None
        )
    if not isinstance(ledger, dict):
        return {"removed": [], "updated": False}
    if edl is None:
        if not ctx.artifact_exists("master/edl.json"):
            return {"removed": [], "updated": False}
        loaded = ctx.read_json("master/edl.json")
        edl = loaded if isinstance(loaded, dict) else None
    if not isinstance(edl, dict):
        return {"removed": [], "updated": False}

    omitted_line_ids: set[str] = set()
    omitted_targets: set[str] = set()
    for entry in active_entries(ledger):
        if str(entry.get("decision") or "omit") != "omit":
            continue
        subject = str(entry.get("subject_id") or "").strip()
        if subject:
            omitted_line_ids.add(subject)
        tid = str(entry.get("target_segment_id") or "").strip()
        if tid and str(entry.get("kind") or "") == "layup_skip":
            omitted_targets.add(tid)
            omitted_line_ids.add(f"vo_layup_{tid}")

    clips_in = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
    kept: list[dict[str, Any]] = []
    removed: list[str] = []
    for clip in clips_in:
        ctype = str(clip.get("type") or "")
        if ctype != "vo_pickup":
            kept.append(clip)
            continue
        lid = str(clip.get("line_id") or clip.get("vo_line_id") or "").strip()
        tid = str(clip.get("targets_segment_id") or "").strip()
        if (lid and lid in omitted_line_ids) or (tid and tid in omitted_targets):
            removed.append(lid or tid or "vo_pickup")
            continue
        kept.append(clip)

    if not removed:
        return {"removed": [], "updated": False}

    from interview_mux.junction_snip_qa import _recompute_timeline

    timeline_ms = _recompute_timeline(kept)
    out = dict(edl)
    out["clips"] = kept
    out["timeline_duration_ms"] = timeline_ms
    out["vo_pickup_clip_count"] = sum(1 for c in kept if c.get("type") == "vo_pickup")
    out["transition_clip_count"] = sum(1 for c in kept if c.get("type") == "transition")
    out["silence_clip_count"] = sum(1 for c in kept if c.get("type") == "silence")
    from interview_mux.write_staging import write_committed_json

    write_committed_json(ctx, "master/edl.json", out)
    try:
        from interview_mux.assembly_ledger import write_assembly_ledger

        write_assembly_ledger(ctx, edl=out)
    except Exception:
        pass
    ctx.log(
        f"omit_ledger: stripped {len(removed)} omitted VO clip(s) from EDL",
        level="info",
        stage="edl",
        detail={"removed": removed[:12]},
    )
    return {"removed": removed, "updated": True, "timeline_duration_ms": timeline_ms}


def air_contract_errors(
    ctx: RunContext,
    *,
    ledger: dict[str, Any] | None = None,
    gap_report: dict[str, Any] | None = None,
    edl: dict[str, Any] | None = None,
) -> list[str]:
    """Return ship-blocking violations of active omit decisions.

    This intentionally tolerates runs created before the ledger existed. Once
    present, the ledger must agree with selection authority and with the
    listener-facing gap report / EDL it governs.
    """
    if ledger is None:
        ledger = (
            ctx.read_json(OMIT_LEDGER_REL)
            if ctx.artifact_exists(OMIT_LEDGER_REL)
            else None
        )
    if not isinstance(ledger, dict):
        return []

    errors: list[str] = []
    try:
        from interview_mux.order_hash import get_order_lock, order_locks_match

        selection = (
            ctx.read_json("master/selection.json")
            if ctx.artifact_exists("master/selection.json")
            else {}
        )
        selection_lock = get_order_lock(selection if isinstance(selection, dict) else None)
        ledger_lock = get_order_lock(ledger)
        if selection_lock and ledger_lock and not order_locks_match(selection, ledger):
            errors.append("omit_ledger_order_lock_stale")
    except Exception:
        errors.append("omit_ledger_order_lock_unreadable")

    summary = ledger.get("summary")
    if isinstance(summary, dict) and int(summary.get("unresolved_high_salience") or 0) > 0:
        errors.append(
            "omit_ledger_unresolved_high_salience="
            + str(summary.get("unresolved_high_salience"))
        )

    if gap_report is None:
        gap_report = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else {}
        )
    lines = [
        row
        for row in ((gap_report or {}).get("interviewer_lines") or [])
        if isinstance(row, dict)
    ]
    by_line_id = {str(row.get("line_id") or ""): row for row in lines if row.get("line_id")}

    if edl is None:
        edl = ctx.read_json("master/edl.json") if ctx.artifact_exists("master/edl.json") else {}
    edl_refs = {
        str(clip.get(key) or "")
        for clip in ((edl or {}).get("clips") or [])
        if isinstance(clip, dict)
        for key in ("line_id", "vo_line_id", "source_line_id")
        if clip.get(key)
    }

    for entry in active_entries(ledger):
        subject_id = str(entry.get("subject_id") or "")
        decision = str(entry.get("decision") or "omit")
        kind = str(entry.get("kind") or "")
        if kind == "gap_line_skip":
            line = by_line_id.get(subject_id)
            if line and not line.get("skipped_optional"):
                errors.append(f"omit_ledger_gap_line_not_skipped:{subject_id}")
            if subject_id in edl_refs:
                errors.append(f"omit_ledger_gap_line_still_in_edl:{subject_id}")
        elif decision == "omit" and subject_id in edl_refs:
            errors.append(f"omit_ledger_omitted_line_still_in_edl:{subject_id}")
        elif decision == "suppress":
            replacement = str(entry.get("replacement_ref") or "")
            if not replacement:
                errors.append(f"omit_ledger_suppress_missing_replacement:{subject_id}")
            elif replacement == "episode_orientation":
                if not any(bool(row.get("episode_orientation")) for row in lines):
                    errors.append(
                        f"omit_ledger_orientation_replacement_missing:{subject_id}"
                    )
    return list(dict.fromkeys(errors))


def stamp_gap_report_omit_skips(ctx: RunContext) -> int:
    """Mark gap-report lines skipped when the omit ledger already decided omit/defer."""
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return 0
    ledger = (
        ctx.read_json(OMIT_LEDGER_REL) if ctx.artifact_exists(OMIT_LEDGER_REL) else None
    )
    report = ctx.read_json("understanding/gap_report.json")
    if not isinstance(report, dict) or not isinstance(ledger, dict):
        return 0
    lines = [row for row in (report.get("interviewer_lines") or []) if isinstance(row, dict)]
    by_id = {str(row.get("line_id") or ""): row for row in lines if row.get("line_id")}
    stamped = 0
    for entry in active_entries(ledger):
        subject = str(entry.get("subject_id") or "").strip()
        kind = str(entry.get("kind") or "")
        if kind not in {"gap_line_skip", "layup_skip"}:
            continue
        line = by_id.get(subject)
        if line is None and kind == "layup_skip":
            tid = str(entry.get("target_segment_id") or "").strip()
            if tid:
                line = by_id.get(f"vo_layup_{tid}")
        if not isinstance(line, dict) or line.get("skipped_optional"):
            continue
        line["skipped_optional"] = True
        if not line.get("skip_reason_code"):
            line["skip_reason_code"] = str(entry.get("reason_code") or "omit_ledger")
        stamped += 1
    if not stamped:
        return 0
    report["interviewer_lines"] = lines
    try:
        from interview_mux.write_staging import write_committed_json

        write_committed_json(ctx, "understanding/gap_report.json", report)
    except Exception:
        ctx.write_json("understanding/gap_report.json", report)
    return stamped


def heal_omit_ledger_air_contract(ctx: RunContext) -> dict[str, Any]:
    """Align gap report + EDL with the omit ledger before post-master QC."""
    errors = air_contract_errors(ctx)
    healable = {
        e
        for e in errors
        if e == "omit_ledger_order_lock_stale"
        or e.startswith("omit_ledger_gap_line_not_skipped:")
        or e.startswith("omit_ledger_gap_line_still_in_edl:")
        or e.startswith("omit_ledger_omitted_line_still_in_edl:")
    }
    if not healable:
        return {"healed": False, "errors": errors, "notes": []}
    notes: list[str] = []
    if "omit_ledger_order_lock_stale" in healable:
        rebuild_and_write_omit_ledger(ctx)
        notes.append("rebuilt_stale_order_lock")
    stamped = stamp_gap_report_omit_skips(ctx)
    if stamped:
        notes.append(f"stamped_gap_skips:{stamped}")
    rec = reconcile_edl_with_omit_ledger(ctx)
    removed = list(rec.get("removed") or [])
    if removed:
        notes.append(f"stripped_edl:{len(removed)}")
    remaining = air_contract_errors(ctx)
    return {"healed": True, "notes": notes, "errors": remaining, "removed": removed}


def build_omit_ledger(
    ctx: RunContext,
    *,
    plan: dict[str, Any] | None = None,
    gap_report: dict[str, Any] | None = None,
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild ledger from selection excludes + layup skips + waivers + gap skips.

    Preserves operator_override / gap_line_skip entries from ``prior`` that are
    still referenced, then supersedes deterministic layup/selection rows.
    """
    from interview_mux.nugget_layup import (
        CORPUS_REL,
        GAP_REL,
        PLAN_REL,
        is_justified_skip_row,
        row_nugget_ids,
    )
    from interview_mux.order_hash import get_order_lock

    ledger = empty_omit_ledger()
    prior = prior if isinstance(prior, dict) else (
        ctx.read_json(OMIT_LEDGER_REL) if ctx.artifact_exists(OMIT_LEDGER_REL) else {}
    )
    # Carry forward operator / G1 skips that deterministic rebuild would lose.
    preserved: list[dict[str, Any]] = []
    for row in (prior.get("entries") or []) if isinstance(prior, dict) else []:
        if not isinstance(row, dict) or not row.get("active"):
            continue
        if row.get("operator_override") or str(row.get("kind") or "") == "gap_line_skip":
            preserved.append(dict(row))

    entries: list[dict[str, Any]] = list(preserved)
    seq = len(entries) + 1

    sel = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else {}
    )
    if isinstance(sel, dict):
        lock = get_order_lock(sel)
        if lock:
            ledger["order_lock"] = dict(lock)
            ledger["order_content_hash"] = lock.get("order_content_hash")
        for ex in sel.get("excluded_segment_ids") or []:
            if isinstance(ex, dict):
                sid = str(ex.get("segment_id") or "")
                reason = str(ex.get("reason") or "excluded")
            else:
                sid = str(ex or "")
                reason = "excluded"
            if not sid:
                continue
            entries.append(
                mint_entry(
                    kind="segment_exclude",
                    subject_id=sid,
                    target_segment_id=sid,
                    decision="omit",
                    reason_code=reason,
                    owner_stage="full_master_ranking",
                    source_artifact="master/selection.json",
                    evidence_refs=[f"selection:excluded:{sid}"],
                    compensating_path="nugget_layup_recovery",
                    revisit_if=["selection_reinclude"],
                    decision_confidence=0.9,
                    seq=seq,
                )
            )
            seq += 1

    if plan is None:
        plan = ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    plan = plan if isinstance(plan, dict) else {}
    for row in plan.get("layups") or []:
        if not isinstance(row, dict) or not row.get("skip"):
            continue
        if not is_justified_skip_row(row, soft_migrate=True):
            # Still record unjustified skips so recovery can see them, but they
            # do not count as compensated coverage.
            pass
        tid = str(row.get("target_segment_id") or "")
        lid = str(row.get("line_id") or f"vo_layup_{tid}" or tid)
        reason = str(row.get("skip_reason_code") or "empty_or_skip")
        decision = "suppress" if reason == "opening_orientation_owns_target" else "omit"
        replacement = (
            "episode_orientation"
            if reason == "opening_orientation_owns_target"
            else None
        )
        entries.append(
            mint_entry(
                kind="layup_skip",
                subject_id=lid or tid,
                target_segment_id=tid or None,
                decision=decision,
                reason_code=reason,
                owner_stage=str(row.get("owner_stage") or "nugget_layup_compose"),
                source_artifact=PLAN_REL,
                evidence_refs=[str(x) for x in (row.get("evidence_refs") or []) if x],
                value_forgone=[str(x) for x in (row.get("value_forgone") or []) if x],
                compensating_path=str(row.get("compensating_path") or "") or None,
                revisit_if=[str(x) for x in (row.get("revisit_if") or []) if x],
                decision_confidence=(
                    float(row["decision_confidence"])
                    if row.get("decision_confidence") is not None
                    else 0.85
                ),
                replacement_ref=replacement,
                rationale=str(row.get("listener_need_entering_T") or "") or None,
                seq=seq,
            )
        )
        seq += 1

    for waived in plan.get("waived_nugget_ids") or []:
        if isinstance(waived, dict):
            nid = str(waived.get("nugget_id") or "")
            reason = str(waived.get("reason") or "waived")
        else:
            nid = str(waived or "")
            reason = "waived"
        if not nid:
            continue
        entries.append(
            mint_entry(
                kind="nugget_waive",
                subject_id=nid,
                decision="waive",
                reason_code=reason,
                owner_stage="nugget_layup_compose",
                source_artifact=PLAN_REL,
                evidence_refs=[f"nugget:{nid}"],
                compensating_path="operator_or_compose_waiver",
                decision_confidence=0.8,
                seq=seq,
            )
        )
        seq += 1

    if gap_report is None:
        gap_report = ctx.read_json(GAP_REL) if ctx.artifact_exists(GAP_REL) else {}
    if isinstance(gap_report, dict):
        for ln in gap_report.get("interviewer_lines") or []:
            if not isinstance(ln, dict) or not ln.get("skipped_optional"):
                continue
            lid = str(ln.get("line_id") or "")
            if not lid:
                continue
            # Prefer preserved operator row if already present.
            if any(str(e.get("subject_id") or "") == lid for e in preserved):
                continue
            entries.append(
                mint_entry(
                    kind="gap_line_skip",
                    subject_id=lid,
                    target_segment_id=str(ln.get("targets_segment_id") or "") or None,
                    decision="defer",
                    reason_code="g1_skipped_optional",
                    owner_stage="g1_vo_pickup",
                    source_artifact=GAP_REL,
                    evidence_refs=[f"gap_report:{lid}"],
                    compensating_path="operator_skip_optional",
                    operator_override=True,
                    decision_confidence=1.0,
                    seq=seq,
                )
            )
            seq += 1

    # High-salience open nuggets without compensation surface in summary.
    corpus = ctx.read_json(CORPUS_REL) if ctx.artifact_exists(CORPUS_REL) else {}
    open_high = {str(x) for x in (plan.get("open_high_salience_nugget_ids") or []) if x}
    discharged = {str(x) for x in (plan.get("discharged_nugget_ids") or []) if x}
    claimed: set[str] = set()
    for row in plan.get("layups") or []:
        if isinstance(row, dict):
            claimed.update(row_nugget_ids(row))
    unresolved = 0
    for nug in (corpus.get("nuggets") or []) if isinstance(corpus, dict) else []:
        if not isinstance(nug, dict):
            continue
        nid = str(nug.get("nugget_id") or "")
        if not nid or nid in discharged or nid in claimed:
            continue
        sal = str(nug.get("salience") or "")
        if sal in ("high", "critical") or nid in open_high:
            if not nug.get("in_selection") or nid in open_high:
                unresolved += 1

    ledger["entries"] = entries
    summary = summarize_entries(entries)
    summary["unresolved_high_salience"] = max(
        int(summary.get("unresolved_high_salience") or 0), unresolved
    )
    ledger["summary"] = summary
    if isinstance(sel, dict) and get_order_lock(sel):
        ledger["order_lock"] = dict(get_order_lock(sel) or {})
        ledger["order_content_hash"] = (get_order_lock(sel) or {}).get("order_content_hash")
    return ledger


def write_omit_ledger(ctx: RunContext, ledger: dict[str, Any]) -> dict[str, Any]:
    from interview_mux.artifact_writes import write_validated_artifact

    doc = dict(ledger) if isinstance(ledger, dict) else empty_omit_ledger()
    doc["summary"] = summarize_entries(
        [e for e in (doc.get("entries") or []) if isinstance(e, dict)]
    )
    try:
        write_validated_artifact(
            ctx,
            OMIT_LEDGER_REL,
            doc,
            merge_from_disk=False,
            stage_key="nugget_layup_compose",
        )
    except Exception:
        ctx.write_json(OMIT_LEDGER_REL, doc)
    return doc


def rebuild_and_write_omit_ledger(
    ctx: RunContext,
    *,
    plan: dict[str, Any] | None = None,
    gap_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prior = ctx.read_json(OMIT_LEDGER_REL) if ctx.artifact_exists(OMIT_LEDGER_REL) else {}
    ledger = build_omit_ledger(ctx, plan=plan, gap_report=gap_report, prior=prior)
    return write_omit_ledger(ctx, ledger)


def record_gap_line_skip(
    ctx: RunContext,
    *,
    line_id: str,
    target_segment_id: str | None = None,
    reason_code: str = "g1_skipped_optional",
    operator_override: bool = True,
) -> dict[str, Any]:
    prior = ctx.read_json(OMIT_LEDGER_REL) if ctx.artifact_exists(OMIT_LEDGER_REL) else empty_omit_ledger()
    entry = mint_entry(
        kind="gap_line_skip",
        subject_id=str(line_id),
        target_segment_id=target_segment_id,
        decision="defer",
        reason_code=reason_code,
        owner_stage="g1_vo_pickup",
        source_artifact="understanding/gap_report.json",
        evidence_refs=[f"gap_report:{line_id}"],
        compensating_path="operator_skip_optional",
        operator_override=operator_override,
        decision_confidence=1.0,
        seq=len(prior.get("entries") or []) + 1,
    )
    updated = supersede_entry(
        prior if isinstance(prior, dict) else empty_omit_ledger(),
        subject_id=str(line_id),
        kind="gap_line_skip",
        replacement=entry,
    )
    return write_omit_ledger(ctx, updated)
