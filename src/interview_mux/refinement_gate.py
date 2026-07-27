"""L1 runtime gate — activate or skip refinement passes (full auto)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.refinement_agenda import load_agenda
from interview_mux.refinement_catalog import (
    class_for_pass,
    get_pass,
    is_blacklisted,
    is_whitelisted,
    refinement_cfg,
)
from interview_mux.refinement_identity import cfi_for_pass
from interview_mux.refinement_ledger import can_run_refinement
from interview_mux.refinement_policy import is_simple_tape
from interview_mux.refinement_succession import is_unlocked, mutex_blocked
from interview_mux.run_context import RunContext

PLAN_REL = "understanding/refinement_plan.json"
SNAPSHOT_ROOT = "understanding/refinement_snapshots"


def load_plan(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(PLAN_REL):
        return {"run_id": ctx.run_id, "schema_version": 1, "passes": []}
    doc = ctx.read_json(PLAN_REL)
    return doc if isinstance(doc, dict) else {"run_id": ctx.run_id, "schema_version": 1, "passes": []}


def update_refinement_plan(ctx: RunContext, decision: dict[str, Any]) -> None:
    doc = load_plan(ctx)
    passes = [p for p in (doc.get("passes") or []) if p.get("pass_id") != decision.get("pass_id")]
    passes.append(decision)
    doc["passes"] = passes
    doc["run_id"] = ctx.run_id
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    ctx.write_json(PLAN_REL, doc)


def compute_input_hash(ctx: RunContext, rel_paths: list[str]) -> str:
    h = hashlib.sha256()
    for rel in sorted(rel_paths):
        h.update(rel.encode("utf-8"))
        if not ctx.artifact_exists(rel):
            h.update(b"MISSING")
            continue
        try:
            raw = ctx.read_path(rel).read_bytes()
        except Exception:
            doc = ctx.read_json(rel) if rel.endswith(".json") else None
            raw = json.dumps(doc, sort_keys=True, default=str).encode("utf-8") if doc else b""
        h.update(raw)
    return h.hexdigest()[:16]


def freeze_inputs(ctx: RunContext, pass_id: str, rel_paths: list[str]) -> str:
    snap_dir = ctx.path(SNAPSHOT_ROOT, pass_id, "inputs")
    snap_dir.mkdir(parents=True, exist_ok=True)
    meta = {"paths": [], "at": datetime.now(timezone.utc).isoformat()}
    for rel in rel_paths:
        entry: dict[str, Any] = {"rel": rel, "present": ctx.artifact_exists(rel)}
        if ctx.artifact_exists(rel) and rel.endswith(".json"):
            try:
                doc = ctx.read_json(rel)
                dest = snap_dir / Path(rel).name
                dest.write_text(json.dumps(doc, indent=2, default=str) + "\n", encoding="utf-8")
                entry["snapshot"] = str(dest.relative_to(ctx.path()))
            except Exception as exc:
                entry["error"] = str(exc)
        meta["paths"].append(entry)
    digest = compute_input_hash(ctx, rel_paths)
    meta["input_hash"] = digest
    ctx.write_json(f"{SNAPSHOT_ROOT}/{pass_id}/meta.json", meta)
    return digest


def _prior_hash(ctx: RunContext, pass_id: str) -> str | None:
    rel = f"{SNAPSHOT_ROOT}/{pass_id}/meta.json"
    if not ctx.artifact_exists(rel):
        return None
    meta = ctx.read_json(rel)
    if isinstance(meta, dict) and meta.get("input_hash"):
        return str(meta["input_hash"])
    return None


def decide_pass(ctx: RunContext, pass_id: str) -> dict[str, Any]:
    """Full-auto activate|skip decision."""
    row = get_pass(pass_id)
    cfi = cfi_for_pass(pass_id)
    cfi_id = cfi.cfi_id if cfi else ""
    class_id = class_for_pass(pass_id) or ""
    base = {
        "pass_id": pass_id,
        "cfi_id": cfi_id,
        "agenda_class": class_id,
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }

    if not refinement_cfg().get("enabled", True):
        return {**base, "status": "skip", "gate": "disabled", "rationale": "refinement_passes disabled", "reason_code": "disabled"}

    if is_blacklisted(stage_id=pass_id, cfi_id=cfi_id or None):
        return {**base, "status": "skip", "gate": "blacklist", "rationale": "blacklisted", "reason_code": "blacklist"}

    if not is_whitelisted(pass_id):
        return {**base, "status": "skip", "gate": "whitelist", "rationale": "not on whitelist", "reason_code": "not_whitelisted"}

    if cfi_id and not can_run_refinement(ctx, cfi_id):
        return {
            **base,
            "status": "skip",
            "gate": "cap",
            "rationale": "second-run cap reached for CFI",
            "reason_code": "cap",
        }

    if is_simple_tape(ctx):
        return {
            **base,
            "status": "skip",
            "gate": "simple_tape",
            "rationale": "simple_tape_profile",
            "reason_code": "simple_tape",
        }

    agenda = load_agenda(ctx)
    if agenda:
        eligible = set(agenda.get("eligible_classes") or [])
        if class_id and class_id not in eligible and class_id != "gap_vo":
            # gap_vo apply helpers may still run after skip-copy via flow integrity
            if pass_id not in ("selection_framing_apply",):
                return {
                    **base,
                    "status": "skip",
                    "gate": "agenda",
                    "rationale": f"class {class_id} not eligible",
                    "reason_code": "not_eligible",
                }
        if class_id == "gap_vo" and "gap_vo" not in eligible and pass_id == "gap_framing_recompose":
            return {
                **base,
                "status": "skip",
                "gate": "agenda",
                "rationale": "gap_vo not eligible",
                "reason_code": "not_eligible",
            }

    if not is_unlocked(ctx, pass_id):
        return {
            **base,
            "status": "skip",
            "gate": "succession",
            "rationale": "succession unlock not satisfied",
            "reason_code": "succession_locked",
        }

    if mutex_blocked(ctx, pass_id):
        return {
            **base,
            "status": "skip",
            "gate": "mutex",
            "rationale": "mutual exclusion with another refine",
            "reason_code": "mutex",
        }

    req = list((row or {}).get("required_artifacts") or [])
    missing = [p for p in req if not ctx.artifact_exists(p)]
    # Soft: draft may be named gap_report.json still
    if "understanding/gap_report.draft.json" in missing and ctx.artifact_exists("understanding/gap_report.json"):
        missing = [p for p in missing if p != "understanding/gap_report.draft.json"]
    if missing:
        return {
            **base,
            "status": "skip",
            "gate": "deterministic",
            "rationale": f"missing artifacts: {missing}",
            "reason_code": "missing_artifacts",
            "signals": {"missing": missing},
        }

    digest = compute_input_hash(ctx, req) if req else ""
    prior = _prior_hash(ctx, pass_id)
    if prior and digest and prior == digest and ctx.artifact_exists("understanding/gap_report.json"):
        # Only skip on hash match when a prior refinement snapshot exists AND final already set
        if ctx.is_done(pass_id):
            return {
                **base,
                "status": "skip",
                "gate": "input_hash",
                "rationale": "no_new_evidence",
                "reason_code": "no_new_evidence",
                "input_hash": digest,
            }

    decision = {
        **base,
        "status": "activate",
        "gate": "deterministic",
        "rationale": "eligible with new evidence",
        "reason_code": "activate",
        "input_hash": digest,
        "signals": {},
    }
    # Comprehension / topic signals (informational)
    if pass_id == "gap_framing_recompose" and ctx.artifact_exists("master/selection.json"):
        decision["signals"]["has_selection"] = True
    if pass_id == "ranking_refine" and ctx.artifact_exists("master/coverage_audit.json"):
        cov = ctx.read_json("master/coverage_audit.json")
        holes = (cov or {}).get("uncovered_topics") if isinstance(cov, dict) else None
        if holes:
            decision["signals"]["topic_holes"] = True
        elif agenda and "ranking" not in set(agenda.get("eligible_classes") or []):
            return {
                **base,
                "status": "skip",
                "gate": "deterministic",
                "rationale": "no topic holes",
                "reason_code": "no_topic_holes",
            }

    update_refinement_plan(ctx, decision)
    ctx.log(
        f"Refinement gate {pass_id}: {decision['status']} ({decision['reason_code']})",
        level="info",
        stage=pass_id,
        action_id="refinement_gate",
        detail=decision,
    )
    return decision
