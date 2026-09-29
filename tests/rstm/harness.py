"""Execute one RSTM cell as a contract/incompleteness/seed-prereq check (mocked)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.homunculus.runtime import _seed_prereq_block
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

try:
    from tests.rstm.mutations import MUTATIONS
    from tests.rstm.residual_cluster_scorecard import (
        DONE_WHEN_CATALOG,
        INLINE_SMOKES,
        inline_names_for,
        proof_notes,
        run_inline_smoke,
    )
except ModuleNotFoundError:
    from mutations import MUTATIONS  # type: ignore
    from residual_cluster_scorecard import (  # type: ignore
        DONE_WHEN_CATALOG,
        INLINE_SMOKES,
        inline_names_for,
        proof_notes,
        run_inline_smoke,
    )

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "rstm-results"
CELLS_DIR = RESULTS_DIR / "cells"

GATE_LIKE = {
    "G0",
    "G_Framing",
    "G1",
    "G_Listen",
    "G_Publish",
    "preclean_offer",
    "timeline_optimizer",
    "clear_from",
    "pending_shadow",
    "committed_master",
}


@dataclass
class CellResult:
    cell_id: str
    status: str  # PASS | FAIL | BLOCKED_BY_HEAD | SCOPE_CONTRACT_ONLY | ERROR
    tier: str
    notes: list[str] = field(default_factory=list)
    confirmed_clusters: list[str] = field(default_factory=list)
    executed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "status": self.status,
            "tier": self.tier,
            "notes": self.notes,
            "confirmed_clusters": self.confirmed_clusters,
            "executed_at": self.executed_at
            or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }


def _apply_mutation(ctx: RunContext, mutation: str) -> None:
    if "+" in mutation:
        for part in mutation.split("+"):
            fn = MUTATIONS.get(part)
            if fn:
                fn(ctx)
        return
    fn = MUTATIONS.get(mutation)
    if fn:
        fn(ctx)


def _stage_ids(stages: list[str]) -> list[str]:
    return [s for s in stages if s not in GATE_LIKE and not s.startswith("G")]


def run_cell(ctx: RunContext, cell: dict[str, Any]) -> CellResult:
    """Contract-level execution for one matrix cell."""
    cell_id = str(cell["cell_id"])
    tier = str(cell["tier"])
    stages = list(cell.get("stages") or [])
    mutation = str(cell.get("mutation") or "M1_none")
    cluster = str(cell.get("cluster") or "")
    res = CellResult(cell_id=cell_id, status="PASS", tier=tier)
    res.executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        _apply_mutation(ctx, mutation)
        real = _stage_ids(stages)

        # Wave 8 residual Done-when scorecard cells
        if tier == "RC-DW":
            catalog_id = cluster or (stages[0] if stages else "")
            row = DONE_WHEN_CATALOG.get(catalog_id)
            if row is None:
                res.status = "FAIL"
                res.notes.append(f"unknown_catalog_id:{catalog_id}")
                return res
            notes = proof_notes(catalog_id)
            res.notes.extend(notes)
            inline_names = inline_names_for(catalog_id)
            if inline_names:
                for name in inline_names:
                    if name not in INLINE_SMOKES:
                        res.status = "FAIL"
                        res.notes.append(f"inline_unregistered:{name}")
                        return res
                    try:
                        run_inline_smoke(name, ctx)
                        res.notes.append(f"inline_ok:{name}")
                    except Exception as exc:
                        res.status = "FAIL"
                        res.notes.append(f"inline_fail:{name}:{type(exc).__name__}:{exc}")
                        return res
                res.status = "PASS"
                return res
            res.status = "SCOPE_CONTRACT_ONLY"
            res.notes.append("named_proofs_external")
            return res

        # Gate / INV symbolic cells — mode honesty smoke only
        if tier in {"GATE", "INV"} or (stages and stages[0] in GATE_LIKE):
            mode = str(cell.get("mode") or "invariant")
            if mode == "partial" and stages and stages[0] in {"G_Publish", "G_Framing"}:
                res.notes.append("partial_must_not_auto_upload_or_skip_sticky_framing")
            res.status = "SCOPE_CONTRACT_ONLY"
            res.notes.append("gate_or_inv_symbolic")
            return res

        if not real:
            res.status = "SCOPE_CONTRACT_ONLY"
            res.notes.append("no_real_stages")
            return res

        primary = real[0]

        # D1 / hollow-done: mark done without primary artifact → incompleteness should fire if mapped
        if tier == "D1" or mutation.startswith("M5"):
            done = ctx.run_dir / ".stage_done" / primary
            done.parent.mkdir(parents=True, exist_ok=True)
            done.write_text("rstm\n")
            rel = STAGE_ARTIFACT_DISK_PATHS.get(primary)
            if rel:
                art = ctx.run_dir / str(rel)
                if art.exists():
                    art.unlink()
                else:
                    # ensure missing
                    pass
                reason = stage_artifact_incompleteness(ctx, primary)
                if reason is None and primary in list(ANALYSIS_ORDER) + list(DELIVERY_ORDER):
                    # Analysis stages often lack incompleteness — catalog P0
                    if primary in ANALYSIS_ORDER or primary not in {
                        "vo_synthesize",
                        "edl",
                        "nugget_layup_compose",
                        "selection_order_sanitize",
                        "gap_report_sanitize",
                        "air_contract_sanitize",
                        "sound_design_plan",
                        "sfx_prompt_craft",
                        "mmaudio_sfx",
                        "music_palette_compose",
                        "missing_framing",
                        "gap_framing_compose",
                    }:
                        res.status = "FAIL"
                        res.confirmed_clusters.append("hollow-done-coverage")
                        res.notes.append(
                            f"hollow_done_no_incompleteness stage={primary} primary={rel}"
                        )
                elif reason:
                    res.notes.append(f"incompleteness_ok:{reason[:80]}")

        # Seed-front: B should be blocked when A incomplete
        if len(real) >= 2 and real[0] != real[1]:
            a, b = real[0], real[1]
            # ensure A incomplete (no stage_done)
            (ctx.run_dir / ".stage_done" / a).unlink(missing_ok=True)
            # mark all before A done so earliest incomplete is A (best-effort)
            order = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
            if a in order and b in order:
                ai = order.index(a)
                for sid in order[:ai]:
                    p = ctx.run_dir / ".stage_done" / sid
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text("rstm_prior\n")
                blocked = _seed_prereq_block(ctx, b)
                if blocked is None and order.index(b) > ai:
                    # May be legal atypical — only fail if seed-adjacent expect block
                    if tier in {"D2-SEED", "D2-SKIP1"} and order.index(b) == ai + 1:
                        res.status = "FAIL"
                        res.confirmed_clusters.append("homunculus-dispatch-prereq")
                        res.notes.append(f"seed_prereq_missing a={a} b={b}")
                    elif tier.startswith("D2") and blocked is None:
                        res.notes.append(f"no_block a={a} b={b} (may be atypical ok)")
                elif blocked == a:
                    res.notes.append(f"seed_block_ok:{blocked}")
                elif blocked:
                    res.notes.append(f"seed_block_other:{blocked}")

        # Repeat cell: same stage twice — incompleteness/resume honesty
        if len(real) >= 2 and real[0] == real[1]:
            res.notes.append("repeat_path")
            if mutation.startswith("M5") or mutation.startswith("M8"):
                reason = stage_artifact_incompleteness(ctx, real[0])
                if reason is None and real[0] == "vo_synthesize":
                    # VO without wav should be incomplete when seated — try mark
                    res.notes.append("vo_repeat_check")

        # Uncommitted master honesty
        if "M9_uncommitted_master" in mutation or mutation == "M9_uncommitted_master":
            try:
                from interview_mux.delivery_guardrails import ship_path_ready
                from interview_mux.delivery_invariants import committed_master_wav

                wav = (ctx.run_dir / "master" / "master.wav").exists()
                ready, reason = ship_path_ready(ctx)
                committed = committed_master_wav(ctx)
                if wav and not committed and ready:
                    res.status = "FAIL"
                    res.confirmed_clusters.append("committed-master-honesty")
                    res.notes.append("ship_path_ready_true_with_bare_wav")
                elif wav and not committed and reason == "master_uncommitted":
                    res.notes.append("ship_path_blocks_uncommitted_ok")
                else:
                    res.notes.append(
                        f"ship_path_ready={ready} reason={reason!r} "
                        f"wav={wav} committed={committed}"
                    )
            except Exception as exc:
                res.notes.append(f"ship_path_ready_exc:{type(exc).__name__}")

        # Empty schema skip
        if "M3_hollow_object" in mutation or mutation == "M3_hollow_object":
            try:
                from interview_mux.prompt_validation import (
                    STAGE_ARTIFACT_SCHEMAS,
                    validate_stage_artifacts,
                )

                # Prefer a stage that actually has a schema binding.
                stage_key = "speaker_roles"
                if "mastering_plan_synthesize" in STAGE_ARTIFACT_SCHEMAS:
                    stage_key = "mastering_plan_synthesize"
                elif STAGE_ARTIFACT_SCHEMAS:
                    stage_key = next(iter(STAGE_ARTIFACT_SCHEMAS))
                errs = validate_stage_artifacts(stage_key, {})
                if errs == [] or errs is None:
                    res.confirmed_clusters.append("schema-hollow-gate")
                    if res.status == "PASS":
                        res.status = "FAIL"
                    res.notes.append("empty_artifact_skips_schema")
                else:
                    res.notes.append(f"empty_artifact_rejected:{errs[0][:80]}")
            except Exception as exc:
                res.notes.append(f"schema_check:{type(exc).__name__}:{exc}")

        if cluster and res.status == "FAIL" and cluster not in res.confirmed_clusters:
            res.confirmed_clusters.append(cluster)

        # Depth 3/4 without full impl → contract only if no fail yet and only seed notes
        if tier.startswith("D3") or tier.startswith("D4"):
            if res.status == "PASS" and not any("hollow_done" in n for n in res.notes):
                # still ran seed checks; mark contract scope if nothing substantive
                if not res.notes:
                    res.status = "SCOPE_CONTRACT_ONLY"
                    res.notes.append("multi_hop_contract_only")

    except Exception as exc:
        res.status = "ERROR"
        res.notes.append(f"{type(exc).__name__}:{exc}")

    return res


def persist_result(result: CellResult) -> Path:
    CELLS_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-+]+", "_", result.cell_id)
    # Cell ids run to ~150 chars. A flat 180-char truncation still overflows
    # the Windows 260-char path limit once CELLS_DIR is deep (a checkout in a
    # user profile or a synced folder is enough), and a FileNotFoundError out
    # of write_text is an unhelpful way to discover that. Budget against the
    # real directory length, and append a digest whenever the readable part is
    # cut so two distinct cells cannot collide on one file. cell_id is stored
    # inside the JSON, so shortening the name loses nothing.
    # Cap at the original 180 where the path allows it, so existing (macOS)
    # filenames are untouched, and only shorten further when 260 would overflow.
    stem_budget = min(180, 250 - len(str(CELLS_DIR)) - len(".json"))
    if stem_budget < 24:
        stem_budget = 24
    if len(safe) > stem_budget:
        digest = hashlib.sha1(result.cell_id.encode("utf-8")).hexdigest()[:10]
        keep = max(8, stem_budget - len(digest) - 1)
        safe = f"{safe[:keep]}-{digest}"
    path = CELLS_DIR / f"{safe}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path
