"""Safe commits for intentional multi-writer shared JSON paths.

``understanding/content_brief.json`` and ``segments/boundaries.json`` are
co-produced by ordered stages (handoff / refine), not single-signer lands.
They must **not** join ``SHARED_PATH_PRODUCER_STAGES`` unpaid gating.

Choke point: ``RunContext.write_json`` calls ``guard_shared_path_on_write`` so
literal and ``write_json(rel)`` variable sites both get meta safety.

Ownership ALLOW remains the write authority SSOT. A-05
``SHARED_PATH_CO_PRODUCERS`` stays a narrower unmark peer set on purpose.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from interview_mux.run_context import RunContext

CONTENT_BRIEF_REL = "understanding/content_brief.json"
BOUNDARIES_REL = "segments/boundaries.json"

# Paths that get meta merge on every write_json.
SHARED_PATH_COMMIT_RELS: frozenset[str] = frozenset(
    {
        CONTENT_BRIEF_REL,
        BOUNDARIES_REL,
    }
)

# Sacred body fields: non-claim / reanchor must not empty these when disk had them.
CONTENT_BRIEF_SACRED_KEYS: frozenset[str] = frozenset({"thesis", "topics"})
BOUNDARIES_SACRED_KEYS: frozenset[str] = frozenset({"boundaries"})

_OPTS_ATTR = "_shared_path_write_opts"
_DISK_CACHE_ATTR = "_shared_path_disk_cache"


def persist_allow_stages(rel: str) -> frozenset[str]:
    """Stages with an ALLOW persist row for ``rel`` (empty if ownership unavailable)."""
    path = str(rel or "").replace("\\", "/").lstrip("/")
    try:
        from interview_mux.artifact_ownership import ALLOW

        return frozenset(
            str(a.stage)
            for a in ALLOW
            if a.path == path and a.verb == "persist" and str(a.stage or "").strip()
        )
    except Exception:
        return frozenset()


def producer_claim_ok(rel: str, producer: str) -> bool:
    """True when ``producer`` is an ALLOW persist co-producer for ``rel``.

    Use instead of hard-equality to a single stage (e.g. ``boundary_detection``)
    so hitch/fuse/resplit claims do not look like unpaid / orphan land.
    """
    path = str(rel or "").replace("\\", "/").lstrip("/")
    if path not in SHARED_PATH_COMMIT_RELS:
        return False
    prod = str(producer or "").strip()
    if not prod:
        return False
    return prod in persist_allow_stages(path)


def merge_shared_path_meta(
    incoming: dict[str, Any],
    *,
    disk: dict[str, Any] | None,
    stage_key: str | None = None,
    claim_producer: bool = True,
    clear_stale: bool = True,
) -> dict[str, Any]:
    """Merge ``_meta`` for a shared-path rewrite without wiping the claim.

    Rules (footgun-aware):
    - Start from disk ``_meta``, overlay incoming ``_meta``
    - ``clear_stale`` drops ``stale`` / ``stale_reason`` (intentional rewrite)
    - ``claim_producer`` + non-empty ``stage_key`` → stamp ``producer_stage``
    - else keep disk ``producer_stage`` when incoming wiped it
    """
    out = dict(incoming) if isinstance(incoming, dict) else {}
    disk_meta = (
        dict(disk.get("_meta") or {})
        if isinstance(disk, dict) and isinstance(disk.get("_meta"), dict)
        else {}
    )
    incoming_meta = (
        dict(out.get("_meta") or {}) if isinstance(out.get("_meta"), dict) else {}
    )
    meta = {**disk_meta, **incoming_meta}
    if clear_stale:
        meta.pop("stale", None)
        meta.pop("stale_reason", None)
    sk = str(stage_key or "").strip()
    if claim_producer and sk:
        meta["producer_stage"] = sk
    else:
        prior = str(disk_meta.get("producer_stage") or "").strip()
        cur = str(meta.get("producer_stage") or "").strip()
        if prior and not cur:
            meta["producer_stage"] = prior
    out["_meta"] = meta
    return out


def protect_sacred_fields(
    incoming: dict[str, Any],
    *,
    disk: dict[str, Any] | None,
    rel: str,
) -> dict[str, Any]:
    """Restore sacred keys from disk when incoming empties them."""
    if not isinstance(disk, dict) or not isinstance(incoming, dict):
        return incoming if isinstance(incoming, dict) else {}
    out = dict(incoming)
    path = str(rel or "").replace("\\", "/").lstrip("/")
    if path == CONTENT_BRIEF_REL:
        for key in CONTENT_BRIEF_SACRED_KEYS:
            if key not in disk:
                continue
            disk_val = disk.get(key)
            cur = out.get(key)
            empty = cur is None or cur == "" or cur == []
            if empty and disk_val not in (None, "", []):
                out[key] = disk_val
    elif path == BOUNDARIES_REL:
        disk_rows = disk.get("boundaries")
        cur_rows = out.get("boundaries")
        if isinstance(disk_rows, list) and disk_rows and (
            not isinstance(cur_rows, list) or not cur_rows
        ):
            out["boundaries"] = disk_rows
    return out


def _read_disk_cached(ctx: RunContext, path: str) -> dict[str, Any] | None:
    """One disk read per path per write_json call stack (avoids double prepare)."""
    cache = getattr(ctx, _DISK_CACHE_ATTR, None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(ctx, _DISK_CACHE_ATTR, cache)
    if path in cache:
        return cache[path]
    disk: dict[str, Any] | None = None
    if ctx.artifact_exists(path):
        try:
            raw = ctx.read_json(path)
            if isinstance(raw, dict):
                disk = raw
        except Exception:
            disk = None
    cache[path] = disk
    return disk


def prepare_shared_path_doc(
    ctx: RunContext,
    rel: str,
    doc: dict[str, Any],
    *,
    stage_key: str | None = None,
    claim_producer: bool = True,
    clear_stale: bool = True,
    protect_sacred: bool = False,
    disk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply meta merge (+ optional sacred protect) against live disk."""
    path = str(rel or "").replace("\\", "/").lstrip("/")
    if disk is None:
        disk = _read_disk_cached(ctx, path)
    out = dict(doc) if isinstance(doc, dict) else {}
    if protect_sacred:
        out = protect_sacred_fields(out, disk=disk, rel=path)
    return merge_shared_path_meta(
        out,
        disk=disk,
        stage_key=stage_key,
        claim_producer=claim_producer,
        clear_stale=clear_stale,
    )


@contextmanager
def shared_path_write_opts(
    ctx: RunContext,
    *,
    claim_producer: bool | None = None,
    clear_stale: bool | None = None,
    protect_sacred: bool | None = None,
) -> Iterator[None]:
    """Override default guard policy for the next ``write_json`` on shared paths."""
    prev = getattr(ctx, _OPTS_ATTR, None)
    opts: dict[str, Any] = {}
    if claim_producer is not None:
        opts["claim_producer"] = bool(claim_producer)
    if clear_stale is not None:
        opts["clear_stale"] = bool(clear_stale)
    if protect_sacred is not None:
        opts["protect_sacred"] = bool(protect_sacred)
    setattr(ctx, _OPTS_ATTR, opts)
    # Fresh disk cache for this write opts scope.
    setattr(ctx, _DISK_CACHE_ATTR, {})
    try:
        yield
    finally:
        if prev is None:
            try:
                delattr(ctx, _OPTS_ATTR)
            except Exception:
                setattr(ctx, _OPTS_ATTR, None)
        else:
            setattr(ctx, _OPTS_ATTR, prev)
        try:
            delattr(ctx, _DISK_CACHE_ATTR)
        except Exception:
            setattr(ctx, _DISK_CACHE_ATTR, {})


def guard_shared_path_on_write(
    ctx: RunContext,
    rel: str,
    data: dict[str, Any],
    *,
    stage_key: str | None = None,
) -> dict[str, Any]:
    """Single choke-point guard for brief/boundaries (used by ``write_json``).

    Defaults:
    - claim when ``stage_key`` is an ALLOW persist producer and write is not an
      intentional stale stamp
    - clear stale unless incoming ``_meta.stale`` is set (lifecycle stamps)
    - protect sacred when not claiming, or on content_brief_reanchor
    """
    path = str(rel or "").replace("\\", "/").lstrip("/")
    if path not in SHARED_PATH_COMMIT_RELS or not isinstance(data, dict):
        return data
    opts = getattr(ctx, _OPTS_ATTR, None)
    if not isinstance(opts, dict):
        opts = {}
    incoming_meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
    intentional_stale = bool(incoming_meta.get("stale"))
    sk = str(stage_key or "").strip()
    allow = persist_allow_stages(path)
    if "claim_producer" in opts:
        claim = bool(opts["claim_producer"])
    else:
        claim = bool(sk) and sk in allow and not intentional_stale
    if "clear_stale" in opts:
        clear_stale = bool(opts["clear_stale"])
    else:
        clear_stale = not intentional_stale
    if "protect_sacred" in opts:
        protect = bool(opts["protect_sacred"])
    else:
        protect = (not claim) or (
            path == CONTENT_BRIEF_REL and sk == "content_brief_reanchor"
        )
    return prepare_shared_path_doc(
        ctx,
        path,
        data,
        stage_key=sk or None,
        claim_producer=claim,
        clear_stale=clear_stale,
        protect_sacred=protect,
    )


def commit_content_brief_doc(
    ctx: RunContext,
    doc: dict[str, Any],
    *,
    stage_key: str | None = None,
    claim_producer: bool = True,
    clear_stale: bool = True,
    protect_sacred: bool | None = None,
    skip_handoff: bool = False,
) -> Any:
    """Persist content brief via ``write_json`` with explicit shared-path opts."""
    protect = (
        bool(protect_sacred)
        if protect_sacred is not None
        else (not claim_producer or str(stage_key or "") == "content_brief_reanchor")
    )
    with shared_path_write_opts(
        ctx,
        claim_producer=claim_producer,
        clear_stale=clear_stale,
        protect_sacred=protect,
    ):
        return ctx.write_json(
            CONTENT_BRIEF_REL,
            doc,
            stage_key=stage_key,
            skip_handoff=skip_handoff,
        )


def commit_boundaries_doc(
    ctx: RunContext,
    doc: dict[str, Any],
    *,
    stage_key: str | None = None,
    claim_producer: bool = True,
    clear_stale: bool = True,
    protect_sacred: bool | None = None,
    skip_handoff: bool = False,
) -> Any:
    """Persist boundaries via ``write_json`` with explicit shared-path opts."""
    protect = bool(protect_sacred) if protect_sacred is not None else (not claim_producer)
    with shared_path_write_opts(
        ctx,
        claim_producer=claim_producer,
        clear_stale=clear_stale,
        protect_sacred=protect,
    ):
        return ctx.write_json(
            BOUNDARIES_REL,
            doc,
            stage_key=stage_key,
            skip_handoff=skip_handoff,
        )


# Back-compat alias used by older write_validated hook / tests.
def apply_shared_path_meta_on_write(
    ctx: RunContext,
    rel_path: str,
    doc: dict[str, Any],
    *,
    stage_key: str | None = None,
) -> dict[str, Any]:
    """Deprecated alias — prefer ``guard_shared_path_on_write`` / write_json hook."""
    return guard_shared_path_on_write(ctx, rel_path, doc, stage_key=stage_key)


__all__ = [
    "BOUNDARIES_REL",
    "CONTENT_BRIEF_REL",
    "CONTENT_BRIEF_SACRED_KEYS",
    "BOUNDARIES_SACRED_KEYS",
    "SHARED_PATH_COMMIT_RELS",
    "apply_shared_path_meta_on_write",
    "commit_boundaries_doc",
    "commit_content_brief_doc",
    "guard_shared_path_on_write",
    "merge_shared_path_meta",
    "persist_allow_stages",
    "prepare_shared_path_doc",
    "producer_claim_ok",
    "protect_sacred_fields",
    "shared_path_write_opts",
]
