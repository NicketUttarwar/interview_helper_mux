"""Dispatch state-delta guard and per-re-entry attempt memo (plan §5.2 / §5.3).

Two mechanisms, one artifact (``operator/dispatch_memo.json``):

* **no-delta** (§5.2) — every dispatch records the hash set of the stage's declared
  hard inputs. A re-dispatch whose hash set is identical to the last *successful*
  attempt, whose outputs are still on disk, is refused: unchanged inputs cannot
  produce a different outcome. This is the ~7 h ``mix`` ⇄ ``junction_snip_qa``
  ping-pong (55 excess dispatches in exec_11871).
* **attempt memo** (§5.3) — a stage attempted in this walk whose state is unchanged,
  in a run that has not progressed since, is not re-offered on the next driver
  re-entry. This is the 148 ``delivery_walk_to_master`` + 63
  ``analysis_fill_delivery_prereqs`` re-entries re-walking the same remaining set.

**The trap this module avoids:** 45 of 90 contracts declare no hard inputs. Hashing
an empty set would make every dispatch of those stages look identical and refuse
them all. So an empty input set means the guard is **inactive** for that stage, and
stages known to thrash get an explicit fallback input set below.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

MEMO_REL = "operator/dispatch_memo.json"
_LARGE_FILE_BYTES = 8 * 1024 * 1024
_CHUNK = 1024 * 1024

# Hard inputs for stages whose contract declares none yet (§1.1: 45/90 hollow).
# Deliberately over-inclusive: an extra input can only *weaken* the guard (more
# deltas), while a missing one could refuse a legitimate re-run. A stage's own
# outputs are stripped, and the counterpart's report is never an input — that is
# what makes the mix ⇄ junction fixpoint hold.
FALLBACK_HARD_INPUTS: dict[str, tuple[str, ...]] = {
    "mix": (
        "master/edl.json",
        "master/selection.json",
        "master/transitions.json",
        "understanding/sound_design_plan.json",
        "understanding/omit_ledger.json",
        "sound_design/assets/*.wav",
        "vo_pickup/*.wav",
    ),
    "junction_snip_qa": (
        "master/assembly.wav",
        "master/edl.json",
    ),
    "master_finalize": (
        "master/assembly.wav",
        "master/edl.json",
        "master/junction_snip_qa.json",
    ),
    "assembly_preview": (
        "master/edl.json",
        "vo_pickup/*.wav",
    ),
    "edl": (
        "master/selection.json",
        "master/transitions.json",
        "understanding/gap_report.json",
        "understanding/omit_ledger.json",
        "understanding/nugget_layup_plan.json",
        "segments/manifest.json",
        "vo_pickup/*.wav",
    ),
    "transitions": (
        "master/selection.json",
        "master/narrative_plan.json",
        "segments/manifest.json",
    ),
    "vernacular_segment_sanitize": (
        "segments/manifest.json",
        "transcript/full.json",
    ),
    "speaker_roles": (
        "transcript/full.json",
        "understanding/source_topology.json",
    ),
}

# Declared convergence metrics (§2.2): stages that legitimately iterate pass a
# changed input each cycle by construction. Their counter artifact joins the hash
# set, so a cycle that advances the counter is a real delta and a cycle that does
# not is correctly refused. This is the sanctioned alternative to weakening the rule.
CONVERGENCE_INPUTS: dict[str, tuple[str, ...]] = {
    # junction ladder: recut/fuse/omit passes bump the residual generation.
    "junction_snip_qa": ("operator/delivery_residuals.json",),
    # narrative remutate cycles are counted before each re-offer.
    "edl_narrative_audit": ("operator/narrative_audit_cycle.json",),
    # fuse rounds are the pre-ranking convergence metric.
    "connector_fuse_pass": ("analysis/connector_fuse_rounds.json",),
    "connector_fuse_pass_pre_ranking": ("analysis/connector_fuse_rounds_pre_ranking.json",),
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _env_on(name: str, *, default: bool = True) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def no_delta_enabled() -> bool:
    return _env_on("MUX_DISPATCH_NO_DELTA")


def memo_enabled() -> bool:
    return _env_on("MUX_DISPATCH_MEMO")


# ---------------------------------------------------------------------------
# input hashing
# ---------------------------------------------------------------------------

def _stage_outputs(stage: str) -> set[str]:
    outs: set[str] = set()
    try:
        from interview_mux.stage_contract import load_contract

        contract = load_contract(stage)
        if contract is not None:
            outs |= {o.path for o in contract.outputs if o.path}
    except Exception:
        pass
    try:
        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

        primary = STAGE_ARTIFACT_DISK_PATHS.get(stage)
        if primary:
            outs.add(primary)
    except Exception:
        pass
    return outs


def hard_input_paths(ctx: RunContext, stage: str) -> tuple[str, ...]:
    """Declared hard inputs for ``stage`` unioned with the fallback set, else empty.

    Contract *and* fallback, never contract instead of fallback: the fallback table
    is over-inclusive on purpose, so letting a freshly populated contract replace it
    could shrink the hash set — the one direction that refuses a legitimate re-run.
    An empty tuple means "guard inactive for this stage", never "nothing changed".
    """
    paths: list[str] = []
    declared: set[str] = set()
    try:
        from interview_mux.stage_contract import evaluate_when, load_contract

        contract = load_contract(stage)
        if contract is not None:
            for dep in contract.inputs:
                if not dep.path:
                    continue
                declared.add(dep.path)
                if not dep.hard:
                    continue
                try:
                    if not evaluate_when(dep.when, ctx):
                        continue
                except Exception:
                    pass
                paths.append(dep.path)
    except Exception:
        paths = []
        declared = set()
    paths.extend(FALLBACK_HARD_INPUTS.get(stage) or ())
    if not paths:
        return ()
    paths.extend(CONVERGENCE_INPUTS.get(stage) or ())
    # A read-modify-write artifact (`vernacular_segment_sanitize` resplitting
    # `segments/manifest.json`) is both an output and a real input: its pre-state
    # decides the outcome, so only outputs the contract does *not* claim to read
    # are stripped.
    own = _stage_outputs(stage) - declared
    return tuple(sorted({p for p in paths if p and p not in own}))


def _file_digest(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "absent"
    h = hashlib.sha256()
    h.update(f"{size}:".encode())
    try:
        with path.open("rb") as fh:
            if size <= _LARGE_FILE_BYTES:
                for block in iter(lambda: fh.read(_CHUNK), b""):
                    h.update(block)
            else:
                # Long audio: size + head/tail keeps the digest content-derived
                # without re-reading hundreds of MB on every dispatch.
                h.update(fh.read(_CHUNK))
                fh.seek(max(0, size - _CHUNK))
                h.update(fh.read(_CHUNK))
    except OSError:
        return "unreadable"
    return h.hexdigest()[:16]


def _entry_digest(ctx: RunContext, rel: str) -> str:
    """Committed state only (§8.6) — never a peer stage's un-promoted staging."""
    root = ctx.final_path()
    if "*" in rel:
        try:
            matches = sorted(p for p in root.glob(rel) if p.is_file())
        except Exception:
            matches = []
        if not matches:
            return "absent"
        h = hashlib.sha256()
        for match in matches:
            h.update(f"{match.relative_to(root)}:{_file_digest(match)}\n".encode())
        return h.hexdigest()[:16]
    path = root.joinpath(*rel.split("/"))
    if path.is_dir():
        h = hashlib.sha256()
        for child in sorted(p for p in path.rglob("*") if p.is_file()):
            h.update(f"{child.relative_to(root)}:{_file_digest(child)}\n".encode())
        return h.hexdigest()[:16]
    if not path.exists():
        return "absent"
    return _file_digest(path)


def input_hash_set(ctx: RunContext, stage: str) -> dict[str, str] | None:
    """``{input_path: digest}`` for the stage's hard inputs, or None when inactive."""
    paths = hard_input_paths(ctx, stage)
    if not paths:
        return None
    return {rel: _entry_digest(ctx, rel) for rel in paths}


def input_digest(ctx: RunContext, stage: str) -> str | None:
    hashes = input_hash_set(ctx, stage)
    if hashes is None:
        return None
    blob = "\n".join(f"{k}={v}" for k, v in sorted(hashes.items()))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def state_token(ctx: RunContext, stage: str) -> str:
    """Witness of "has anything this stage depends on changed?".

    The input digest when the inputs are known; otherwise the stage's own primary
    artifact, so a heal that rewrote it still counts as a delta. Always defined, so
    the attempt memo covers the 40 pipeline stages whose inputs are still unknown —
    unlike the no-delta guard, which refuses even successful stages and therefore
    demands real declared inputs.
    """
    digest = input_digest(ctx, stage)
    if digest is not None:
        return digest
    own = ""
    try:
        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

        own = str(STAGE_ARTIFACT_DISK_PATHS.get(stage) or "")
    except Exception:
        own = ""
    if not own:
        return "no_inputs_known"
    return f"own:{_entry_digest(ctx, own)}"


# ---------------------------------------------------------------------------
# memo artifact
# ---------------------------------------------------------------------------

def progress_token(ctx: RunContext) -> str:
    """Cheap monotone witness of run progress: which stages are marked done.

    A memo entry only suppresses a re-offer while this token is unchanged. Any real
    progress elsewhere in the run invalidates every "nothing happened" conclusion,
    so the memo can never permanently hide a stage.
    """
    marker_dir = ctx.final_path(".stage_done")
    try:
        names = sorted(p.name for p in marker_dir.iterdir() if p.is_file())
    except OSError:
        names = []
    master = "1" if ctx.final_path("master", "master.wav").is_file() else "0"
    blob = f"{master}|" + ",".join(names)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def read_memo(ctx: RunContext) -> dict[str, Any]:
    path = Path(ctx.run_dir) / MEMO_REL
    if not path.is_file():
        return {"version": 1, "updated_at": _now(), "stages": {}}
    try:
        doc = ctx.read_json(MEMO_REL)
    except Exception:
        doc = None
    if not isinstance(doc, dict):
        return {"version": 1, "updated_at": _now(), "stages": {}}
    doc.setdefault("version", 1)
    doc.setdefault("stages", {})
    return doc


def _write_memo(ctx: RunContext, doc: dict[str, Any]) -> None:
    from interview_mux.file_store import write_json as fs_write_json

    dest = Path(ctx.run_dir) / MEMO_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(dest, doc)


def memo_row(ctx: RunContext, stage: str) -> dict[str, Any]:
    row = (read_memo(ctx).get("stages") or {}).get(str(stage or ""))
    return dict(row) if isinstance(row, dict) else {}


def _live_product_stamps() -> tuple[str, str]:
    """Product + ownership matrix stamps used to invalidate stale attempt memos."""
    try:
        from interview_mux.identical_failures import product_code_fingerprint

        fp = str(product_code_fingerprint() or "")
    except Exception:
        fp = ""
    try:
        from interview_mux.artifact_ownership import matrix_version

        mv = str(matrix_version() or "")
    except Exception:
        mv = ""
    return fp, mv


def record_attempt(
    ctx: RunContext,
    stage: str,
    *,
    outcome: str,
    digest: str | None = None,
    source: str = "",
) -> dict[str, Any]:
    """Record this dispatch attempt. ``outcome`` ∈ started|done|failed|refused."""
    sid = str(stage or "")
    if not sid:
        return {}
    doc = read_memo(ctx)
    stages = dict(doc.get("stages") or {})
    prev = dict(stages.get(sid) or {})
    if digest is None:
        digest = input_digest(ctx, sid)
    product_fp, matrix_ver = _live_product_stamps()
    row: dict[str, Any] = {
        "stage": sid,
        "input_digest": digest,
        "state_token": state_token(ctx, sid),
        "outcome": str(outcome or ""),
        "source": str(source or ""),
        "progress_token": progress_token(ctx),
        "product_fingerprint": product_fp,
        "matrix_version": matrix_ver,
        "attempts": int(prev.get("attempts") or 0) + (1 if outcome == "started" else 0),
        "transient_failures": (
            int(prev.get("transient_failures") or 0) + 1
            if outcome == "failed_transient"
            else (0 if outcome == "done" else int(prev.get("transient_failures") or 0))
        ),
        "updated_at": _now(),
        "first_seen_at": str(prev.get("first_seen_at") or _now()),
    }
    if outcome == "done":
        row["last_done_digest"] = digest
    else:
        row["last_done_digest"] = prev.get("last_done_digest")
    stages[sid] = row
    doc["stages"] = stages
    doc["updated_at"] = _now()
    _write_memo(ctx, doc)
    return row


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

def _outputs_present(ctx: RunContext, stage: str) -> bool:
    try:
        from interview_mux.homunculus.agenda import stage_outputs_present

        return bool(stage_outputs_present(ctx, stage))
    except Exception:
        return False


def no_delta_refusal(
    ctx: RunContext,
    stage: str,
) -> tuple[str, dict[str, Any]] | None:
    """Refuse a re-dispatch whose hard inputs are byte-identical to the last success.

    Guarded three ways so it can never strand a run:
    1. inactive when the stage has no known hard inputs (hollow contract, no fallback);
    2. only refuses when the previous identical-digest attempt reached ``done``;
    3. only refuses while that attempt's outputs are still on disk — a stage whose
       outputs went missing is productive to re-run even with unchanged inputs.
    """
    if not no_delta_enabled():
        return None
    digest = input_digest(ctx, stage)
    if digest is None:
        return None
    row = memo_row(ctx, stage)
    if not row:
        return None
    if str(row.get("last_done_digest") or "") != digest:
        return None
    if not _outputs_present(ctx, stage):
        return None
    return "no_delta", {
        "stage": stage,
        "input_digest": digest,
        "inputs": hard_input_paths(ctx, stage),
        "last_attempt_at": row.get("updated_at"),
    }


MAX_TRANSIENT_RETRIES = 3


def memo_skip(ctx: RunContext, stage: str) -> tuple[str, dict[str, Any]] | None:
    """Refuse to re-offer a stage already attempted at this state with no progress.

    Product / ownership matrix changes (or a legacy memo missing those stamps) must
    not permanently refuse a producer that failed under a prior ALLOW or code finger-
    print — otherwise a patch-and-continue forensics resume is stranded behind
    ``own:absent`` with unchanged ``.stage_done``.
    """
    if not memo_enabled():
        return None
    row = memo_row(ctx, stage)
    if not row:
        return None
    outcome = str(row.get("outcome") or "")
    if outcome == "failed_transient":
        # Retry a network/provider failure at the same state, a few times; a
        # dead network must still end the walk rather than loop forever.
        if int(row.get("transient_failures") or 0) <= MAX_TRANSIENT_RETRIES:
            return None
        outcome = "failed"
    if outcome not in {"failed", "refused"}:
        return None
    live_fp, live_mv = _live_product_stamps()
    stamped_fp = str(row.get("product_fingerprint") or "")
    stamped_mv = str(row.get("matrix_version") or "")
    # Missing stamp = mismatch (legacy rows written before this field existed).
    if stamped_fp != live_fp or stamped_mv != live_mv:
        return None
    token = state_token(ctx, stage)
    if str(row.get("state_token") or "") != token:
        return None
    if str(row.get("progress_token") or "") != progress_token(ctx):
        return None
    # Incomplete multi-shard producers must not strand behind a refused memo when
    # incompleteness still pins resume to this stage (exec_13198 layup shard 1/2).
    # Narrow to shards_pending — generic incompleteness must still honor the memo.
    try:
        from interview_mux.stage_completion import (
            parse_resume_stage_from_reason,
            stage_artifact_incompleteness,
        )

        reason = stage_artifact_incompleteness(ctx, stage) or ""
        if (
            "shards_pending" in reason
            and parse_resume_stage_from_reason(reason) == stage
        ):
            return None
    except Exception:
        pass
    return "attempt_memo", {
        "stage": stage,
        "state_token": token,
        "prior_outcome": row.get("outcome"),
        "progress_token": row.get("progress_token"),
        "product_fingerprint": stamped_fp,
        "matrix_version": stamped_mv,
    }


def forget_incomplete_stage_rows(ctx: RunContext) -> int:
    """Drop the memo rows of stages that are not seed-complete (ISSUES 127).

    A row is what lets the door refuse a stage: "inputs unchanged since the
    last success", "already attempted at this state". Both are only worth
    honouring for a stage whose result stands. The engine's second wind calls
    this so its one re-entry can run whatever was left incomplete.
    """
    doc = read_memo(ctx)
    stages = dict(doc.get("stages") or {})
    if not stages:
        return 0
    try:
        from interview_mux.delivery_guardrails import seed_stage_complete
    except Exception:
        return 0
    kept: dict[str, Any] = {}
    cleared = 0
    for sid, row in stages.items():
        try:
            complete = bool(seed_stage_complete(ctx, str(sid)))
        except Exception:
            complete = False
        if complete:
            kept[sid] = row
        else:
            cleared += 1
    if cleared:
        doc["stages"] = kept
        doc["updated_at"] = _now()
        _write_memo(ctx, doc)
    return cleared


def clear_failed_refused_memo_rows(ctx: RunContext) -> int:
    """Drop failed/refused attempt-memo rows (forensics restart / product flip).

    A single post-patch failure must not permanently refuse the producer for the
    rest of the campaign — identical-halts already clear on forensics restart;
    memo must match that contract.
    """
    doc = read_memo(ctx)
    stages = dict(doc.get("stages") or {})
    if not stages:
        return 0
    kept: dict[str, Any] = {}
    cleared = 0
    for sid, row in stages.items():
        if not isinstance(row, dict):
            continue
        if str(row.get("outcome") or "") in {"failed", "failed_transient", "refused"}:
            cleared += 1
            continue
        kept[sid] = row
    if not cleared:
        return 0
    doc["stages"] = kept
    doc["updated_at"] = _now()
    _write_memo(ctx, doc)
    return cleared


def resume_after_intervene(
    ctx: RunContext, *, stages: tuple[str, ...] | list[str] | set[str] | None = None
) -> dict[str, Any]:
    """Clear failed attempt rows and sticky halts for product-patched stages.

    ``stages=None`` clears every failed/refused row and sticky attempt, which is
    the appropriate scope when a forensics restart cannot identify one patch
    target. Successful memo rows are retained.
    """
    wanted = {str(stage).strip() for stage in (stages or ()) if str(stage).strip()}
    doc = read_memo(ctx)
    rows = dict(doc.get("stages") or {})
    kept: dict[str, Any] = {}
    memo_cleared = 0
    for sid, row in rows.items():
        failed = isinstance(row, dict) and str(row.get("outcome") or "") in {
            "failed",
            "failed_transient",
            "refused",
        }
        if failed and (not wanted or sid in wanted):
            memo_cleared += 1
            continue
        kept[sid] = row
    if memo_cleared:
        doc["stages"] = kept
        doc["updated_at"] = _now()
        _write_memo(ctx, doc)

    sticky_cleared = 0
    sticky_rel = "operator/sticky_heal.json"
    if ctx.artifact_exists(sticky_rel):
        try:
            sticky = ctx.read_json(sticky_rel)
        except Exception:
            sticky = None
        if isinstance(sticky, dict):
            attempts = dict(sticky.get("attempts") or {})
            retained: dict[str, Any] = {}
            for key, row in attempts.items():
                pin = str((row or {}).get("pin") or "") if isinstance(row, dict) else ""
                if not wanted or pin in wanted:
                    sticky_cleared += 1
                else:
                    retained[key] = row
            active = sticky.get("active_halt")
            active_pin = (
                str(active.get("pin") or "") if isinstance(active, dict) else ""
            )
            sticky["attempts"] = retained
            if isinstance(active, dict) and (not wanted or active_pin in wanted):
                sticky.pop("active_halt", None)
            sticky["updated_at"] = __import__("time").time()
            ctx.write_json(sticky_rel, sticky, skip_handoff=True)

    # Selection bus refuse + authority-undo halt strand layup after a CTA omit
    # patch (exec_13198 selection_commit_refused ↔ hash_oscillation).
    refused_cleared = 0
    try:
        from interview_mux.air_order_boundary import clear_selection_commit_refused

        for sid in sorted(wanted or {"nugget_layup_compose"}):
            before = ctx.artifact_exists("operator/selection_commit_refused.json")
            clear_selection_commit_refused(ctx, stage_key=sid)
            if before:
                refused_cleared += 1
    except Exception:
        refused_cleared = 0
    undo_cleared = 0
    if not wanted or wanted & {
        "nugget_layup_compose",
        "selection_order_sanitize",
        "full_master_ranking",
        "selection_framing_apply",
    }:
        undo_rel = "operator/authority_undo.json"
        if ctx.artifact_exists(undo_rel):
            try:
                doc_u = ctx.read_json(undo_rel)
            except Exception:
                doc_u = None
            if isinstance(doc_u, dict):
                arts = dict(doc_u.get("artifacts") or {})
                if "master/selection.json" in arts:
                    arts.pop("master/selection.json", None)
                    undo_cleared = 1
                active_u = (
                    doc_u.get("active_halt")
                    if isinstance(doc_u.get("active_halt"), dict)
                    else {}
                )
                if str((active_u or {}).get("artifact") or "") == "master/selection.json":
                    doc_u.pop("active_halt", None)
                    undo_cleared = 1
                doc_u["artifacts"] = arts
                ctx.write_json(undo_rel, doc_u, skip_handoff=True)
    return {
        "memo_cleared": memo_cleared,
        "sticky_cleared": sticky_cleared,
        "refused_cleared": refused_cleared,
        "undo_cleared": undo_cleared,
        "stages": sorted(wanted),
    }


# Stages whose attempt_memo / identical halt must clear before resuming NAP
# after a never-again patch (exec_13174 leapfrog nest).
_NAP_CONTINUE_HYGIENE_STAGES: frozenset[str] = frozenset(
    {
        "narrative_arc_plan",
        "connector_fuse_pass_pre_ranking",
        "chapter_close_hitch",
        "nugget_layup_compose",
    }
)


def clear_nap_continue_hygiene(ctx: RunContext) -> dict[str, Any]:
    """Clear identical + attempt_memo for NAP seed-front before continue.

    Prevents ``attempt_memo — advancing`` while primary is still missing after a
    code patch. Safe under forensics ``MUX_FRESH=0`` resume.
    """
    stages = set(_NAP_CONTINUE_HYGIENE_STAGES)
    out = resume_after_intervene(ctx, stages=stages)
    try:
        from interview_mux.identical_failures import clear_halts_for_stages

        out["halts_cleared"] = clear_halts_for_stages(ctx, stages, force=True)
    except Exception as exc:
        out["halts_cleared"] = 0
        out["halts_error"] = str(exc)[:160]
    try:

        def _mut(meta: dict[str, Any]) -> None:
            if str(meta.get("needs_operator_stage") or "") in stages:
                meta.pop("needs_operator", None)
                meta.pop("needs_operator_stage", None)
                meta.pop("needs_operator_reason", None)

        ctx.mutate_run_meta(_mut)
    except Exception:
        pass
    return out
