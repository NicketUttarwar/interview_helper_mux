"""Re-entry guard + sanitary-hash fast path for sanitize writes."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from typing import Any, Iterator


_CTX_FLAG = "_artifact_sanitize_reentry"


def sanitary_content_hash(doc: dict[str, Any] | None, *, keys: list[str] | None = None) -> str:
    """Stable hash of the authority surface of a doc (excluding _meta.sanitize)."""
    if not isinstance(doc, dict):
        return "empty"
    payload: dict[str, Any] = {}
    if keys:
        for k in keys:
            if k in doc:
                payload[k] = doc[k]
    else:
        payload = {k: v for k, v in doc.items() if k != "_meta"}
    try:
        raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    except Exception:
        raw = str(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def stamp_sanitize_meta(
    doc: dict[str, Any],
    *,
    ok: bool,
    source: str,
    actions_n: int = 0,
    extra: dict[str, Any] | None = None,
    content_keys: list[str] | None = None,
) -> dict[str, Any]:
    out = dict(doc)
    meta = dict(out.get("_meta") or {}) if isinstance(out.get("_meta"), dict) else {}
    stamp: dict[str, Any] = {
        "ok": bool(ok),
        "source": source,
        "actions": int(actions_n),
        "hash": sanitary_content_hash(out, keys=content_keys),
    }
    if extra:
        stamp.update(extra)
    meta["sanitize"] = stamp
    out["_meta"] = meta
    return out


def stamp_matches(doc: dict[str, Any] | None, *, content_keys: list[str] | None = None) -> bool:
    if not isinstance(doc, dict):
        return False
    meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
    stamp = meta.get("sanitize") if isinstance(meta.get("sanitize"), dict) else {}
    if stamp.get("ok") is not True:
        return False
    expected = str(stamp.get("hash") or "")
    if not expected:
        return False
    return expected == sanitary_content_hash(doc, keys=content_keys)


def in_sanitize_reentry(ctx: Any) -> bool:
    return bool(getattr(ctx, _CTX_FLAG, False))


@contextmanager
def sanitize_reentry_guard(ctx: Any) -> Iterator[bool]:
    """Yield True if this is a nested re-entry (caller should no-op)."""
    if in_sanitize_reentry(ctx):
        yield True
        return
    try:
        setattr(ctx, _CTX_FLAG, True)
        yield False
    finally:
        try:
            setattr(ctx, _CTX_FLAG, False)
        except Exception:
            pass
