"""Persisted identical-failure supervisor — stop the same heal at 3, survive restarts.

Progress ledger (Wave 0.3): telemetry always; hard halt only when
``not forensics_mode()`` **and** ``is_structural_halt_class``. Advisory classes
sanitize/skip-with-ledger and continue other axes. Driver fail keys upsert via
``upsert_fail_key`` — the in-memory driver map is a cache only.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

IDENTICAL_FAILURES_REL = "operator/identical_failures.json"
DEFAULT_HALT_AFTER = 3
# Stages where identical-failure ×3 means "product incomplete" during forensics — not stop.
EDL_REPAIR_STAGES: frozenset[str] = frozenset(
    {"edl", "edl_narrative_audit", "delivery", "g1_vo_pickup", "g1"}
)
PRODUCT_FINGERPRINT_META_KEY = "identical_halts_product_fingerprint"

FailureKind = Literal["reason", "class", "fail_key"]

# Ship-critical / structural — ×3 may hard-halt outside forensics.
STRUCTURAL_HALT_CLASSES: frozenset[str] = frozenset(
    {
        "vo_seated_coverage",
        "edl_vo_coverage_repair",
        "vo_contract_repair",
        "fingerprint_mismatch",
        "assembly_not_rendered_from_current_edl",
        "finalize_input_missing",
        "post_master_quality_missing",
        "incomplete_cut_unresolved",
        "layup_coverage",
        "layup_stale",
        "missing_g1_pickup",
        "framing_vo_unseated",
        "seed_order_prereq",
        "pmq_incomplete_ship_walk",
        "never_touch_cta",
        "never_touch_zeroed_keep",
        "overlapping_source_range",
        "selection_edl_order_drift",
        "opening_slot_conflict",
        "high_gap_unframed",
    }
)

# Advisory — ledger + continue other axes; never hard-halt on class alone.
ADVISORY_FAILURE_CLASSES: frozenset[str] = frozenset(
    {
        "listen_delight_floors",
        "hitch_listen_restage",
        "mmaudio_qa_missing",
        "sdp_theme_wavs_missing",
        "musicgen_theme_failed",
        "redundant_framing_transitions",
        "pending_write_barrier",
        "upstream_stale_rerun",
        "air_script_omit_sync",
        "episode_close_outro",
        "vo_audibility_drift",
        "opening_orientation_inaudible",
    }
)

_COUNT_SUFFIX_RE = re.compile(r"\sx\d+\b", flags=re.IGNORECASE)
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T[\d:.]+Z?")
_HEX_RE = re.compile(r"\b[a-f0-9]{8,}\b", flags=re.IGNORECASE)
_SEG_BRACKET_RE = re.compile(r"\[seg_[a-z0-9_]+\]", flags=re.IGNORECASE)
_SEAM_PAIR_RE = re.compile(
    r"seg_[a-z0-9_]+\s*(?:→|->)\s*seg_[a-z0-9_]+",
    flags=re.IGNORECASE,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def forensics_mode() -> bool:
    """Forensics runs patch product code and re-run EDL — ×3 halt is telemetry only."""
    raw = str(os.environ.get("MUX_FORENSICS") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def is_structural_halt_class(error_class: str) -> bool:
    """True when ×3 of this class may hard-halt outside forensics.

    Unknown / empty classes default to structural (fail-closed for halt honesty).
    Advisory classes never hard-halt — sanitize/skip-with-ledger and continue.
    """
    ec = str(error_class or "").strip().lower()
    if not ec:
        return True
    if ec in ADVISORY_FAILURE_CLASSES:
        return False
    if ec in STRUCTURAL_HALT_CLASSES:
        return True
    return True


def halt_after(*, cfg: dict[str, Any] | None = None) -> int:
    root = cfg if isinstance(cfg, dict) else merged_config()
    try:
        san = root.get("artifact_sanitize") if isinstance(root, dict) else None
        if isinstance(san, dict) and san.get("halt_after") is not None:
            return max(1, int(san.get("halt_after")))
    except (TypeError, ValueError):
        pass
    raw = (root.get("resilience") or {}) if isinstance(root, dict) else {}
    try:
        n = int(raw.get("identical_failure_halt_after") or DEFAULT_HALT_AFTER)
    except (TypeError, ValueError):
        n = DEFAULT_HALT_AFTER
    return max(1, n)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def product_code_fingerprint(*, repo_root: Path | None = None) -> str:
    """Short fingerprint of the installed product — changes when code changes."""
    root = repo_root or _repo_root()
    try:
        cp = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if cp.returncode == 0:
            head = cp.stdout.strip()
            if head:
                dirty = subprocess.run(
                    ["git", "-C", str(root), "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                suffix = ""
                if dirty.returncode == 0 and dirty.stdout.strip():
                    suffix = "+" + hashlib.sha256(dirty.stdout.encode()).hexdigest()[:8]
                return (head + suffix)[:48]
    except Exception:
        pass
    h = hashlib.sha256()
    for base in (root / "src" / "interview_mux", root / "tools" / "full_auto_driver.py"):
        if base.is_file():
            st = base.stat()
            h.update(f"{base.name}:{st.st_mtime_ns}:{st.st_size}\n".encode())
        elif base.is_dir():
            for path in sorted(base.rglob("*.py")):
                try:
                    st = path.stat()
                except OSError:
                    continue
                rel = path.relative_to(root)
                h.update(f"{rel}:{st.st_mtime_ns}:{st.st_size}\n".encode())
    return h.hexdigest()[:16]


def normalize_reason(reason: str) -> str:
    text = " ".join(str(reason or "").strip().split())
    text = _TS_RE.sub("<ts>", text)
    text = _COUNT_SUFFIX_RE.sub("", text)
    text = _SEG_BRACKET_RE.sub("[<seg>]", text)
    text = _SEAM_PAIR_RE.sub("<pair>", text)
    text = _HEX_RE.sub("<id>", text)
    return text[:240].strip().lower()


def fail_key_signature(fail_key: str) -> str:
    """Stable ledger signature for a driver ``fail_key`` (same hash as ``record_failure``)."""
    key = str(fail_key or "").strip()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def failure_signature(
    *,
    failed_stage: str,
    producer: str = "",
    reason: str = "",
) -> str:
    key = "|".join(
        [
            str(failed_stage or "").strip(),
            str(producer or "").strip(),
            normalize_reason(reason),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _empty_doc() -> dict[str, Any]:
    return {"version": 1, "updated_at": _utc_now(), "signatures": {}, "order": []}


def read_identical_failures(ctx: RunContext) -> dict[str, Any]:
    path = Path(ctx.run_dir) / IDENTICAL_FAILURES_REL
    if not path.is_file():
        return _empty_doc()
    try:
        data = ctx.read_json(IDENTICAL_FAILURES_REL)
    except Exception:
        return _empty_doc()
    if not isinstance(data, dict):
        return _empty_doc()
    data.setdefault("version", 1)
    data.setdefault("signatures", {})
    data.setdefault("order", [])
    return data


def _write(ctx: RunContext, doc: dict[str, Any]) -> None:
    dest = Path(ctx.run_dir) / IDENTICAL_FAILURES_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(dest, doc)


def failure_signature_by_class(
    *,
    failed_stage: str,
    error_class: str,
    predicate_token: str = "",
) -> str:
    """B-04: signature = predicate + class + stage when predicate present."""
    parts = [
        str(failed_stage or "").strip(),
        str(error_class or "").strip(),
    ]
    pred = str(predicate_token or "").strip()
    if pred:
        parts = [pred, *parts]
    key = "|".join(parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]



def _predicate_token_for(ctx: RunContext, stage: str) -> str:
    try:
        from interview_mux.thrash_hardening import stage_predicate_token

        return stage_predicate_token(ctx, stage)
    except Exception:
        return ""


def _cascade_suppressed_row(
    *,
    sig: str,
    failed_stage: str,
    producer: str = "",
    error_class: str = "",
    reason: str = "",
    prev: dict[str, Any],
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "signature": sig,
        "failed_stage": str(failed_stage or ""),
        "count": int(prev.get("count") or 0),
        "halt_after": halt_after(),
        "halt": False,
        "cascade_suppressed": True,
        "updated_at": _utc_now(),
    }
    if producer:
        out["producer"] = str(producer)
    if error_class:
        out["error_class"] = str(error_class)
        out["producer"] = str(error_class or producer or "")
    if reason:
        out["reason"] = normalize_reason(reason)
    return out


_PREDICATE_UNCHANGED_MARKERS = (
    "batch_fill",
    "filled_by",
    "predicate_unchanged",
    "hollow-refuse",
    "coverage_cap",
    "vo_unsanitary",
    "coverage exhaust",
    "coverage-exhaust",
    "still_missing",
    "missing_framing batch_fill",
)


def predicate_is_unchanged_rewrite(reason: str = "", token: str = "") -> bool:
    """Wave 2b: same hollow-refuse rewrite is not ESR progress (mtime ≠ new work)."""
    blob = f"{reason} {token}".lower()
    return any(m in blob for m in _PREDICATE_UNCHANGED_MARKERS)


def _finalize_halt_stamp(
    ctx: RunContext,
    row: dict[str, Any],
    prev: dict[str, Any],
) -> None:
    """HC-2: new halt follows ESR freshness (1B); a stamped halt stays (3A)."""
    if bool(prev.get("halt")):
        row["halt"] = True
        row.pop("esr_softened", None)
        row.pop("esr_error", None)
        return
    if not row.get("halt"):
        return
    reason = str(row.get("reason") or "")
    token = str(row.get("predicate_token") or "")
    if predicate_is_unchanged_rewrite(reason, token):
        # Wave 2b: rewrite of the same hollow-refuse primary is not ESR progress.
        return
    try:
        from interview_mux.execution_status import may_hard_halt

        pin = str(row.get("failed_stage") or row.get("resume_attempted") or "")
        if not may_hard_halt(ctx, pin=pin, predicate_token=token):
            row["halt"] = False
            row["esr_softened"] = True
    except Exception:
        # Fail-closed for HARD: prefer wait over false sticky
        row["halt"] = False
        row["esr_softened"] = True
        row["esr_error"] = True


def _mirror_forensics_error(ctx: RunContext, row: dict[str, Any]) -> None:
    """Always capture forensics error detail when MUX_FORENSICS is on."""
    try:
        if not forensics_mode():
            return
        from interview_mux.forensics_error_ledger import record_from_identical_failure_row

        record_from_identical_failure_row(ctx, row)
    except Exception:
        pass


def record_failure(
    ctx: RunContext,
    *,
    kind: FailureKind,
    failed_stage: str = "",
    producer: str = "",
    reason: str = "",
    error_class: str = "",
    fail_key: str = "",
    resume_attempted: str = "",
    predicate_token: str = "",
    count: int | None = None,
) -> dict[str, Any]:
    """Sole writer for identical-failure ledger increments (kinds: reason|class|fail_key)."""
    kind_key = str(kind or "").strip().lower()
    if kind_key not in {"reason", "class", "fail_key"}:
        raise ValueError(f"record_failure: unknown kind {kind!r}")

    if kind_key == "class":
        cls = str(error_class or producer or "").strip()
        try:
            from interview_mux.execution_contract import failure_in_active_policy_cascade

            if failure_in_active_policy_cascade(
                ctx, failed_stage=failed_stage, producer=cls
            ):
                sig = failure_signature_by_class(
                    failed_stage=failed_stage,
                    error_class=cls,
                    predicate_token=predicate_token,
                )
                doc = read_identical_failures(ctx)
                prev = dict((doc.get("signatures") or {}).get(sig) or {})
                row = _cascade_suppressed_row(
                    sig=sig,
                    failed_stage=failed_stage,
                    error_class=cls,
                    prev=prev,
                )
                _mirror_forensics_error(ctx, row)
                return row
        except Exception:
            pass
        sig = failure_signature_by_class(
            failed_stage=failed_stage,
            error_class=cls,
            predicate_token=predicate_token
            or _predicate_token_for(ctx, failed_stage),
        )
        doc = read_identical_failures(ctx)
        signatures = dict(doc.get("signatures") or {})
        prev = dict(signatures.get(sig) or {})
        n = int(prev.get("count") or 0) + 1
        limit = halt_after()
        stage = str(failed_stage or "")
        structural = is_structural_halt_class(cls)
        row = {
            "signature": sig,
            "kind": "class",
            "failed_stage": stage,
            "error_class": cls,
            "producer": cls,
            "resume_attempted": str(resume_attempted or prev.get("resume_attempted") or ""),
            "count": n,
            "halt_after": limit,
            # Advisory classes: telemetry only — never hard-halt (Wave 0.3).
            "halt": bool(structural and n >= limit),
            "structural": structural,
            "updated_at": _utc_now(),
            "first_seen_at": str(prev.get("first_seen_at") or _utc_now()),
            "predicate_token": str(
                predicate_token
                or prev.get("predicate_token")
                or _predicate_token_for(ctx, stage)
                or ""
            ).strip(),
        }
        signatures[sig] = row
        order = [s for s in (doc.get("order") or []) if s != sig]
        order.append(sig)
        doc["signatures"] = signatures
        doc["order"] = order[-200:]
        doc["updated_at"] = _utc_now()
        _write(ctx, doc)
        try:
            ctx.log(
                f"class_failure {failed_stage}/{cls} x{n}/{limit} halt={row['halt']}",
                level="warning" if row["halt"] else "info",
                stage=str(failed_stage or None),
                detail={"signature": sig, "error_class": cls, "resume": resume_attempted},
            )
        except Exception:
            pass
        _mirror_forensics_error(ctx, row)
        return row

    if kind_key == "fail_key":
        key = str(fail_key or "").strip()
        sig = fail_key_signature(key)
        doc = read_identical_failures(ctx)
        signatures = dict(doc.get("signatures") or {})
        prev = dict(signatures.get(sig) or {})
        limit = halt_after()
        n = max(int(prev.get("count") or 0), int(count if count is not None else 0))
        stage = str(failed_stage or "").strip() or str(key).split(":")[0]
        row = {
            "signature": sig,
            "kind": "fail_key",
            "fail_key": key,
            "failed_stage": stage,
            "producer": str(producer or prev.get("producer") or ""),
            "reason": normalize_reason(reason or key),
            "raw_reason": str(reason or key or "")[:400],
            "resume_attempted": str(resume_attempted or prev.get("resume_attempted") or ""),
            "count": n,
            "halt_after": limit,
            "halt": n >= limit,
            "updated_at": _utc_now(),
            "first_seen_at": str(prev.get("first_seen_at") or _utc_now()),
        }
        token = str(
            predicate_token
            or prev.get("predicate_token")
            or _predicate_token_for(ctx, stage)
            or ""
        ).strip()
        if token:
            row["predicate_token"] = token
        _finalize_halt_stamp(ctx, row, prev)
        signatures[sig] = row
        order = [s for s in (doc.get("order") or []) if s != sig]
        order.append(sig)
        doc["signatures"] = signatures
        doc["order"] = order[-200:]
        doc["updated_at"] = _utc_now()
        _write(ctx, doc)
        _mirror_forensics_error(ctx, row)
        return row

    # kind == "reason"
    try:
        from interview_mux.publishability_boundary import failure_in_active_repair_cascade

        if failure_in_active_repair_cascade(
            ctx, failed_stage=failed_stage, producer=producer
        ):
            sig = failure_signature(
                failed_stage=failed_stage, producer=producer, reason=reason
            )
            doc = read_identical_failures(ctx)
            prev = dict((doc.get("signatures") or {}).get(sig) or {})
            row = _cascade_suppressed_row(
                sig=sig,
                failed_stage=failed_stage,
                producer=producer,
                reason=reason,
                prev=prev,
            )
            _mirror_forensics_error(ctx, row)
            return row
    except Exception:
        pass
    try:
        from interview_mux.execution_contract import failure_in_active_policy_cascade

        if failure_in_active_policy_cascade(
            ctx, failed_stage=failed_stage, producer=producer
        ):
            sig = failure_signature(
                failed_stage=failed_stage, producer=producer, reason=reason
            )
            doc = read_identical_failures(ctx)
            prev = dict((doc.get("signatures") or {}).get(sig) or {})
            row = _cascade_suppressed_row(
                sig=sig,
                failed_stage=failed_stage,
                producer=producer,
                reason=reason,
                prev=prev,
            )
            _mirror_forensics_error(ctx, row)
            return row
    except Exception:
        pass
    sig = failure_signature(
        failed_stage=failed_stage, producer=producer, reason=reason
    )
    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    prev = dict(signatures.get(sig) or {})
    n = int(prev.get("count") or 0) + 1
    limit = halt_after()
    stage = str(failed_stage or "")
    row = {
        "signature": sig,
        "kind": "reason",
        "failed_stage": stage,
        "producer": str(producer or ""),
        "reason": normalize_reason(reason),
        "raw_reason": str(reason or "")[:400],
        "resume_attempted": str(resume_attempted or prev.get("resume_attempted") or ""),
        "count": n,
        "halt_after": limit,
        "halt": n >= limit,
        "updated_at": _utc_now(),
        "first_seen_at": str(prev.get("first_seen_at") or _utc_now()),
        "predicate_token": str(
            predicate_token
            or prev.get("predicate_token")
            or _predicate_token_for(ctx, stage)
            or ""
        ).strip(),
    }
    _finalize_halt_stamp(ctx, row, prev)
    signatures[sig] = row
    order = [s for s in (doc.get("order") or []) if s != sig]
    order.append(sig)
    doc["signatures"] = signatures
    doc["order"] = order[-200:]
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    try:
        ctx.log(
            f"identical_failure {failed_stage} x{n}/{limit} halt={row['halt']}",
            level="warning" if row["halt"] else "info",
            stage=str(failed_stage or None),
            detail={"signature": sig, "producer": producer, "resume": resume_attempted},
        )
    except Exception:
        pass
    _mirror_forensics_error(ctx, row)
    return row


def record_class_failure(
    ctx: RunContext,
    *,
    failed_stage: str,
    error_class: str,
    resume_attempted: str = "",
) -> dict[str, Any]:
    """Increment the persisted counter for a classified (stage, error_class) pair."""
    predicate = ""
    try:
        from interview_mux.delivery_guardrails import residual_ledger_generation

        gen = residual_ledger_generation(ctx)
        predicate = f"err:{error_class}|gen:{gen}"
    except Exception:
        predicate = f"err:{error_class}"
    return record_failure(
        ctx,
        kind="class",
        failed_stage=failed_stage,
        error_class=error_class,
        resume_attempted=resume_attempted,
        predicate_token=predicate,
    )


def record_identical_failure(
    ctx: RunContext,
    *,
    failed_stage: str,
    producer: str = "",
    reason: str = "",
    resume_attempted: str = "",
) -> dict[str, Any]:
    """Increment the persisted counter for this signature. Returns the row + halt flag."""
    return record_failure(
        ctx,
        kind="reason",
        failed_stage=failed_stage,
        producer=producer,
        reason=reason,
        resume_attempted=resume_attempted,
    )


def _strip_pred_prefix(key: str) -> str:
    """Normalize fail keys so `_pred:` is never nested (`_pred:_pred:…`)."""
    base = str(key or "").strip()
    while base.startswith("_pred:"):
        base = base[len("_pred:") :]
    return base


def hydrate_driver_fail_counts(ctx: RunContext) -> dict[str, int | str]:
    """Reload driver fail_key counters (+ optional _pred tokens) after restart."""
    doc = read_identical_failures(ctx)
    out: dict[str, int | str] = {}
    for row in (doc.get("signatures") or {}).values():
        if not isinstance(row, dict):
            continue
        key = _strip_pred_prefix(str(row.get("fail_key") or "").strip())
        if not key:
            continue
        out[key] = int(row.get("count") or 0)
        token = row.get("predicate_token")
        if isinstance(token, str) and token:
            out[f"_pred:{key}"] = token
    # Normalize any already-nested in-memory keys from older disks / callers.
    nested = [k for k in list(out) if str(k).startswith("_pred:_pred:")]
    for bad in nested:
        token = out.pop(bad)
        base = _strip_pred_prefix(bad)
        if base:
            out[f"_pred:{base}"] = token
    return out


def upsert_fail_key(
    ctx: RunContext,
    fail_key: str,
    count: int,
    *,
    failed_stage: str = "",
    producer: str = "",
    reason: str = "",
    resume_attempted: str = "",
    predicate_token: str = "",
) -> dict[str, Any]:
    """Set the persisted counter for a driver fail_key (absolute count, keepalive-safe)."""
    return record_failure(
        ctx,
        kind="fail_key",
        fail_key=fail_key,
        count=count,
        failed_stage=failed_stage,
        producer=producer,
        reason=reason,
        resume_attempted=resume_attempted,
        predicate_token=predicate_token,
    )



def is_halted(ctx: RunContext, signature: str) -> bool:
    """Halt authority is operator/identical_failures.json only (never legacy mirror).

    Forensics mode → always False (campaign patch-and-resume). Advisory
    ``error_class`` rows stay telemetry-only even at ×3.

    HC-2: a stamped ``halt: true`` stands even if ESR sees a newer mtime.
    Unstamped count≥limit still waits while ESR says producer progress is fresh.
    """
    if forensics_mode():
        return False
    doc = read_identical_failures(ctx)
    row = (doc.get("signatures") or {}).get(signature) or {}
    if row.get("cascade_suppressed"):
        return False
    error_class = str(row.get("error_class") or "").strip()
    if error_class and not is_structural_halt_class(error_class):
        return False
    # RC3: also honor live policy cascade (in-memory suppress never persisted).
    try:
        from interview_mux.execution_contract import failure_in_active_policy_cascade

        failed_stage = str(row.get("failed_stage") or "")
        cascade_cls = error_class or str(row.get("producer") or "")
        if failed_stage and cascade_cls and failure_in_active_policy_cascade(
            ctx, failed_stage=failed_stage, producer=cascade_cls
        ):
            return False
    except Exception:
        pass
    # HC-2 3A: a stamped halt stands (mtime/ESR must not un-halt).
    if bool(row.get("halt")):
        return True
    # HC-2 1B: unstamped ×3 still waits while producer progress is fresh.
    try:
        from interview_mux.execution_status import may_hard_halt

        pin = str(row.get("failed_stage") or row.get("resume_attempted") or "")
        if pin and not may_hard_halt(
            ctx,
            pin=pin,
            predicate_token=str(row.get("predicate_token") or ""),
        ):
            return False
    except Exception:
        pass
    return int(row.get("count") or 0) >= halt_after()


def is_fail_key_halted(ctx: RunContext, fail_key: str) -> bool:
    """``is_halted`` for a driver fail_key (one authority)."""
    return is_halted(ctx, fail_key_signature(fail_key))



def _zero_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["count"] = 0
    out["halt"] = False
    out["cleared_at"] = _utc_now()
    return out


def clear_all_halts(ctx: RunContext) -> int:
    """Reset every persisted identical-failure counter (forensics / post-patch resume)."""
    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    cleared = 0
    for sig, row in list(signatures.items()):
        if not isinstance(row, dict):
            continue
        signatures[sig] = _zero_row(row)
        cleared += 1
    if not cleared:
        return 0
    doc["signatures"] = signatures
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    return cleared


def _clear_halts_for_stages_unchecked(
    ctx: RunContext, stages: frozenset[str] | set[str]
) -> int:
    stage_set = {str(s or "").strip().lower() for s in stages if s}
    if not stage_set:
        return 0
    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    cleared = 0
    for sig, row in list(signatures.items()):
        if not isinstance(row, dict):
            continue
        stage = str(row.get("failed_stage") or "").strip().lower()
        fail_key = str(row.get("fail_key") or "")
        if stage not in stage_set and not any(
            fail_key.startswith(f"{s}:") for s in stage_set
        ):
            continue
        signatures[sig] = _zero_row(row)
        cleared += 1
    if not cleared:
        return 0
    doc["signatures"] = signatures
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    return cleared


def clear_halts_for_stages(
    ctx: RunContext,
    stages: frozenset[str] | set[str],
    *,
    force: bool = False,
) -> int:
    """Reset halt counters for stages.

    RC6/O8: free clears require ``force=True`` or forensics mode. Otherwise only
    clear when ``stage_predicate_token`` flipped since the halt was stamped.
    """
    if force or forensics_mode():
        return _clear_halts_for_stages_unchecked(ctx, stages)
    return clear_halts_for_stages_if_predicate_flipped(ctx, stages)


def clear_halts_for_stages_if_predicate_flipped(
    ctx: RunContext, stages: frozenset[str] | set[str]
) -> int:
    """T1: clear halt for stage S only when seed/incompleteness token flipped."""
    from interview_mux.thrash_hardening import predicate_flipped, stage_predicate_token

    stage_set = {str(s or "").strip().lower() for s in stages if s}
    if not stage_set:
        return 0
    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    cleared = 0
    for sig, row in list(signatures.items()):
        if not isinstance(row, dict):
            continue
        stage = str(row.get("failed_stage") or "").strip().lower()
        fail_key = str(row.get("fail_key") or "").lower()
        matched = stage in stage_set or any(
            fail_key.startswith(f"{s}:") or f":{s}" in fail_key or s in fail_key
            for s in stage_set
        )
        if not matched:
            # Also match premature class keys containing music_epoch etc.
            if not any(s in fail_key for s in stage_set):
                continue
        prior = row.get("predicate_token")
        # Prefer failed_stage for flip check; fall back to first requested stage.
        check_stage = stage or next(iter(stage_set))
        if not predicate_flipped(ctx, check_stage, prior if isinstance(prior, str) else None):
            # Refresh token so next heal can detect future flips.
            row = dict(row)
            row["predicate_token"] = stage_predicate_token(ctx, check_stage)
            signatures[sig] = row
            continue
        row = dict(row)
        row["count"] = 0
        row["halt"] = False
        row["cleared_at"] = _utc_now()
        row["predicate_token"] = stage_predicate_token(ctx, check_stage)
        signatures[sig] = row
        cleared += 1
        try:
            from interview_mux.thrash_hardening import clear_thrash_on_predicate_flip

            clear_thrash_on_predicate_flip(
                ctx,
                stage=check_stage,
                prior_token=prior if isinstance(prior, str) else None,
            )
        except Exception:
            pass
    doc["signatures"] = signatures
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    return cleared


def clear_halts_matching(
    ctx: RunContext,
    *,
    failed_stage: str = "",
    reason_substr: str = "",
    force: bool = False,
) -> int:
    """Reset halt counters after the root cause of those failures was repaired.

    Without this, a G1/topology heal cannot resume EDL: the supervisor keeps
    ``halt=True`` for the old G1-missing signature and needs_operator loops.

    RC6/O8: free clears require ``force=True`` or forensics. Otherwise only clear
    when the stage predicate flipped since the halt row was stamped.
    """
    from interview_mux.thrash_hardening import predicate_flipped, stage_predicate_token

    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    stage_key = str(failed_stage or "").strip().lower()
    needle = str(reason_substr or "").strip().lower()
    allow_free = force or forensics_mode()
    cleared = 0
    for sig, row in list(signatures.items()):
        if not isinstance(row, dict):
            continue
        stage = str(row.get("failed_stage") or "").strip().lower()
        reason = str(row.get("reason") or row.get("raw_reason") or "").lower()
        if stage_key and stage != stage_key:
            continue
        if needle and needle not in reason:
            continue
        check_stage = stage or stage_key
        prior = row.get("predicate_token")
        if not allow_free and check_stage:
            if not predicate_flipped(
                ctx, check_stage, prior if isinstance(prior, str) else None
            ):
                row = dict(row)
                row["predicate_token"] = stage_predicate_token(ctx, check_stage)
                signatures[sig] = row
                continue
        row = _zero_row(row)
        if check_stage:
            row["predicate_token"] = stage_predicate_token(ctx, check_stage)
        signatures[sig] = row
        cleared += 1
    if not cleared:
        doc["signatures"] = signatures
        doc["updated_at"] = _utc_now()
        _write(ctx, doc)
        return 0
    doc["signatures"] = signatures
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    return cleared


def clear_edl_repair_halts(ctx: RunContext) -> int:
    """Clear identical-failure halts for the EDL repair chain (product-fingerprint flip)."""
    return clear_halts_for_stages(ctx, EDL_REPAIR_STAGES, force=True)


def sync_identical_halts_with_product(
    ctx: RunContext,
    *,
    forensics: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Reset identical-failure counters when product code changes or forensics restarts.

    Forensics: clear stage signatures on every driver start and when the product
    fingerprint changes — patch-and-resume must never inherit a prior ×3 halt.
    Exception: ``seed_order_prereq`` rows whose named producer is still incomplete
    are preserved so forensics cannot wipe a leapfrog thrash counter mid-spin.

    Production full-auto: product fingerprint change clears EDL repair chain only.
    """
    fp = product_code_fingerprint()
    meta: dict[str, Any] = {}
    try:
        if ctx.artifact_exists("run_meta.json"):
            raw = ctx.read_json("run_meta.json")
            if isinstance(raw, dict):
                meta = raw
    except Exception:
        meta = {}
    prev = str(meta.get(PRODUCT_FINGERPRINT_META_KEY) or "")
    product_changed = bool(prev and prev != fp)
    preserved: dict[str, Any] = {}
    if forensics or force:
        if forensics and not force and not product_changed:
            preserved = _preserve_open_seed_order_prereq_rows(ctx)
        cleared = clear_all_halts(ctx)
        if preserved:
            _restore_identical_rows(ctx, preserved)
            cleared = max(0, int(cleared) - len(preserved))
    elif product_changed:
        cleared = clear_edl_repair_halts(ctx)
    else:
        cleared = 0
    memo_cleared = 0
    if forensics or force or product_changed:
        try:
            from interview_mux.dispatch_delta import clear_failed_refused_memo_rows

            memo_cleared = int(clear_failed_refused_memo_rows(ctx) or 0)
        except Exception:
            memo_cleared = 0
        meta[PRODUCT_FINGERPRINT_META_KEY] = fp
        ctx.write_json("run_meta.json", meta, skip_handoff=True)
    return {
        "cleared": cleared,
        "memo_cleared": memo_cleared,
        "fingerprint": fp,
        "previous_fingerprint": prev,
        "product_changed": product_changed,
        "forensics": forensics,
        "force": force,
        "preserved_seed_order": len(preserved),
        "scope": "all" if (forensics or force) else ("edl" if product_changed else "none"),
    }


def _preserve_open_seed_order_prereq_rows(ctx: RunContext) -> dict[str, Any]:
    """Keep seed_order_prereq counters while the producer is still incomplete."""
    try:
        doc = read_identical_failures(ctx)
    except Exception:
        return {}
    sigs = doc.get("signatures") if isinstance(doc, dict) else None
    if not isinstance(sigs, dict):
        return {}
    keep: dict[str, Any] = {}
    for key, row in sigs.items():
        if not isinstance(row, dict):
            continue
        if str(row.get("error_class") or "") != "seed_order_prereq" and (
            "seed order:" not in str(row.get("reason") or "").lower()
            and "seed_order_prereq" not in str(row.get("fail_key") or "")
        ):
            continue
        producer = str(row.get("producer") or row.get("resume_attempted") or "").strip()
        if not producer or producer in {"budget_exhausted", "homunculus_agenda"}:
            # Try parse from reason text.
            reason = str(row.get("reason") or row.get("raw_reason") or "")
            m = re.search(r"complete ([a-z0-9_]+) before running", reason, re.I)
            producer = m.group(1) if m else ""
        if not producer:
            continue
        incomplete = True
        try:
            from interview_mux.delivery_guardrails import seed_stage_complete

            incomplete = not seed_stage_complete(ctx, producer)
        except Exception:
            try:
                incomplete = not ctx.is_done(producer)
            except Exception:
                incomplete = True
        if incomplete:
            keep[str(key)] = dict(row)
    return keep


def _restore_identical_rows(ctx: RunContext, rows: dict[str, Any]) -> None:
    if not rows:
        return
    try:
        doc = read_identical_failures(ctx)
    except Exception:
        doc = _empty_doc()
    if not isinstance(doc, dict):
        doc = _empty_doc()
    sigs = doc.setdefault("signatures", {})
    order = doc.setdefault("order", [])
    if not isinstance(sigs, dict):
        sigs = {}
        doc["signatures"] = sigs
    if not isinstance(order, list):
        order = []
        doc["order"] = order
    for key, row in rows.items():
        sigs[key] = row
        if key not in order:
            order.append(key)
    doc["updated_at"] = _utc_now()
    try:
        _write(ctx, doc)
    except Exception:
        pass
