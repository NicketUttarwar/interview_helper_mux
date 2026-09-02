"""Persisted identical-failure supervisor — stop the same heal at 3, survive restarts."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

IDENTICAL_FAILURES_REL = "operator/identical_failures.json"
DEFAULT_HALT_AFTER = 3
# Stages where identical-failure ×3 means "product incomplete" during forensics — not stop.
EDL_REPAIR_STAGES: frozenset[str] = frozenset(
    {"edl", "edl_narrative_audit", "delivery", "g1_vo_pickup", "g1"}
)
PRODUCT_FINGERPRINT_META_KEY = "identical_halts_product_fingerprint"

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


def halt_after(*, cfg: dict[str, Any] | None = None) -> int:
    root = cfg if isinstance(cfg, dict) else merged_config()
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
) -> str:
    key = "|".join(
        [
            str(failed_stage or "").strip(),
            str(error_class or "").strip(),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def record_class_failure(
    ctx: RunContext,
    *,
    failed_stage: str,
    error_class: str,
    resume_attempted: str = "",
) -> dict[str, Any]:
    """Increment the persisted counter for a classified (stage, error_class) pair."""
    try:
        from interview_mux.execution_contract import failure_in_active_policy_cascade

        if failure_in_active_policy_cascade(
            ctx, failed_stage=failed_stage, producer=error_class
        ):
            sig = failure_signature_by_class(failed_stage=failed_stage, error_class=error_class)
            doc = read_identical_failures(ctx)
            prev = dict((doc.get("signatures") or {}).get(sig) or {})
            return {
                "signature": sig,
                "failed_stage": str(failed_stage or ""),
                "error_class": str(error_class or ""),
                "count": int(prev.get("count") or 0),
                "halt_after": halt_after(),
                "halt": False,
                "cascade_suppressed": True,
                "updated_at": _utc_now(),
            }
    except Exception:
        pass
    sig = failure_signature_by_class(failed_stage=failed_stage, error_class=error_class)
    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    prev = dict(signatures.get(sig) or {})
    count = int(prev.get("count") or 0) + 1
    limit = halt_after()
    row = {
        "signature": sig,
        "failed_stage": str(failed_stage or ""),
        "error_class": str(error_class or ""),
        "producer": str(error_class or ""),
        "resume_attempted": str(resume_attempted or prev.get("resume_attempted") or ""),
        "count": count,
        "halt_after": limit,
        "halt": count >= limit,
        "updated_at": _utc_now(),
        "first_seen_at": str(prev.get("first_seen_at") or _utc_now()),
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
            f"class_failure {failed_stage}/{error_class} x{count}/{limit} halt={row['halt']}",
            level="warning" if row["halt"] else "info",
            stage=str(failed_stage or None),
            detail={"signature": sig, "error_class": error_class, "resume": resume_attempted},
        )
    except Exception:
        pass
    return row


def record_identical_failure(
    ctx: RunContext,
    *,
    failed_stage: str,
    producer: str = "",
    reason: str = "",
    resume_attempted: str = "",
) -> dict[str, Any]:
    """Increment the persisted counter for this signature. Returns the row + halt flag."""
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
            return {
                "signature": sig,
                "failed_stage": str(failed_stage or ""),
                "producer": str(producer or ""),
                "reason": normalize_reason(reason),
                "count": int(prev.get("count") or 0),
                "halt_after": halt_after(),
                "halt": False,
                "cascade_suppressed": True,
                "updated_at": _utc_now(),
            }
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
            return {
                "signature": sig,
                "failed_stage": str(failed_stage or ""),
                "producer": str(producer or ""),
                "reason": normalize_reason(reason),
                "count": int(prev.get("count") or 0),
                "halt_after": halt_after(),
                "halt": False,
                "cascade_suppressed": True,
                "updated_at": _utc_now(),
            }
    except Exception:
        pass
    sig = failure_signature(
        failed_stage=failed_stage, producer=producer, reason=reason
    )
    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    prev = dict(signatures.get(sig) or {})
    count = int(prev.get("count") or 0) + 1
    limit = halt_after()
    row = {
        "signature": sig,
        "failed_stage": str(failed_stage or ""),
        "producer": str(producer or ""),
        "reason": normalize_reason(reason),
        "raw_reason": str(reason or "")[:400],
        "resume_attempted": str(resume_attempted or prev.get("resume_attempted") or ""),
        "count": count,
        "halt_after": limit,
        "halt": count >= limit,
        "updated_at": _utc_now(),
        "first_seen_at": str(prev.get("first_seen_at") or _utc_now()),
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
            f"identical_failure {failed_stage} x{count}/{limit} halt={row['halt']}",
            level="warning" if row["halt"] else "info",
            stage=str(failed_stage or None),
            detail={"signature": sig, "producer": producer, "resume": resume_attempted},
        )
    except Exception:
        pass
    return row


def upsert_fail_key(
    ctx: RunContext,
    fail_key: str,
    count: int,
    *,
    failed_stage: str = "",
    producer: str = "",
    reason: str = "",
    resume_attempted: str = "",
) -> dict[str, Any]:
    """Set the persisted counter for a driver fail_key (absolute count, keepalive-safe)."""
    sig = hashlib.sha256(str(fail_key or "").encode("utf-8")).hexdigest()[:16]
    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    prev = dict(signatures.get(sig) or {})
    limit = halt_after()
    n = max(int(prev.get("count") or 0), int(count or 0))
    stage = failed_stage or str(fail_key).split(":")[0]
    row = {
        "signature": sig,
        "fail_key": str(fail_key or ""),
        "failed_stage": stage,
        "producer": str(producer or prev.get("producer") or ""),
        "reason": normalize_reason(reason or fail_key),
        "raw_reason": str(reason or fail_key or "")[:400],
        "resume_attempted": str(resume_attempted or prev.get("resume_attempted") or ""),
        "count": n,
        "halt_after": limit,
        "halt": n >= limit,
        "updated_at": _utc_now(),
        "first_seen_at": str(prev.get("first_seen_at") or _utc_now()),
    }
    signatures[sig] = row
    order = [s for s in (doc.get("order") or []) if s != sig]
    order.append(sig)
    doc["signatures"] = signatures
    doc["order"] = order[-200:]
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    return row


def is_halted(ctx: RunContext, signature: str) -> bool:
    if forensics_mode():
        return False
    doc = read_identical_failures(ctx)
    row = (doc.get("signatures") or {}).get(signature) or {}
    if row.get("cascade_suppressed"):
        return False
    return bool(row.get("halt")) or int(row.get("count") or 0) >= halt_after()


def halted_rows(ctx: RunContext) -> list[dict[str, Any]]:
    doc = read_identical_failures(ctx)
    out: list[dict[str, Any]] = []
    for sig in doc.get("order") or []:
        row = (doc.get("signatures") or {}).get(sig)
        if isinstance(row, dict) and row.get("halt"):
            out.append(row)
    return out


def clear_all_halts(ctx: RunContext) -> int:
    """Reset every persisted identical-failure counter (forensics / post-patch resume)."""
    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    cleared = 0
    for sig, row in list(signatures.items()):
        if not isinstance(row, dict):
            continue
        row = dict(row)
        row["count"] = 0
        row["halt"] = False
        row["cleared_at"] = _utc_now()
        signatures[sig] = row
        cleared += 1
    if not cleared:
        return 0
    doc["signatures"] = signatures
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    return cleared


def clear_halts_for_stages(ctx: RunContext, stages: frozenset[str] | set[str]) -> int:
    """Reset all halt counters for the given stages (any reason / fail_key)."""
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
        row = dict(row)
        row["count"] = 0
        row["halt"] = False
        row["cleared_at"] = _utc_now()
        signatures[sig] = row
        cleared += 1
    if not cleared:
        return 0
    doc["signatures"] = signatures
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    return cleared


def clear_halts_matching(
    ctx: RunContext,
    *,
    failed_stage: str = "",
    reason_substr: str = "",
) -> int:
    """Reset halt counters after the root cause of those failures was repaired.

    Without this, a G1/topology heal cannot resume EDL: the supervisor keeps
    `halt=True` for the old G1-missing signature and needs_operator loops.
    """
    doc = read_identical_failures(ctx)
    signatures = dict(doc.get("signatures") or {})
    stage_key = str(failed_stage or "").strip().lower()
    needle = str(reason_substr or "").strip().lower()
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
        row = dict(row)
        row["count"] = 0
        row["halt"] = False
        row["cleared_at"] = _utc_now()
        signatures[sig] = row
        cleared += 1
    if not cleared:
        return 0
    doc["signatures"] = signatures
    doc["updated_at"] = _utc_now()
    _write(ctx, doc)
    return cleared


def clear_edl_repair_halts(ctx: RunContext) -> int:
    """Clear identical-failure halts for the EDL repair chain."""
    return clear_halts_for_stages(ctx, EDL_REPAIR_STAGES)


def sync_identical_halts_with_product(
    ctx: RunContext,
    *,
    forensics: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Reset identical-failure counters when product code changes or forensics restarts.

    Forensics: clear **all** stage signatures on every driver start and when the product
    fingerprint changes — patch-and-resume must never inherit a prior ×3 halt.

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
    if forensics or force:
        cleared = clear_all_halts(ctx)
    elif product_changed:
        cleared = clear_edl_repair_halts(ctx)
    else:
        cleared = 0
    if forensics or force or product_changed:
        meta[PRODUCT_FINGERPRINT_META_KEY] = fp
        ctx.write_json("run_meta.json", meta, skip_handoff=True)
    return {
        "cleared": cleared,
        "fingerprint": fp,
        "previous_fingerprint": prev,
        "product_changed": product_changed,
        "forensics": forensics,
        "force": force,
        "scope": "all" if (forensics or force) else ("edl" if product_changed else "none"),
    }
