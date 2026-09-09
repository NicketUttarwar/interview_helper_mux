"""Shared sanitize-last admit helper for hot authority artifacts."""

from __future__ import annotations

from typing import Any, Callable

from interview_mux.run_context import RunContext

SanitizeFn = Callable[[Any, dict[str, Any]], Any]


def admit_sanitized(
    ctx: RunContext,
    rel: str,
    doc: dict[str, Any],
    *,
    sanitize_fn: SanitizeFn,
    stage_key: str | None = None,
    skip_handoff: bool = False,
    write_committed: bool = False,
    refuse_prefix: str | None = None,
    refuse_if_unsanitary: bool = True,
    content_keys: list[str] | None = None,
    action_class: str | None = None,
) -> dict[str, Any]:
    """Run non-amplifying sanitize then persist; optionally refuse if unsanitary.

    ``sanitize_fn(ctx, doc)`` must return an object with ``.ok``, ``.errors``,
    and ``.doc`` (SanitizeResult) or a ``(doc, ok, errors)`` tuple.
    """
    result = sanitize_fn(ctx, dict(doc))
    if hasattr(result, "ok"):
        ok = bool(result.ok)
        errors = list(getattr(result, "errors", None) or [])
        out = result.doc if isinstance(getattr(result, "doc", None), dict) else dict(doc)
    else:
        out, ok, errors = result  # type: ignore[misc]
        out = out if isinstance(out, dict) else dict(doc)
        ok = bool(ok)
        errors = list(errors or [])
    if refuse_if_unsanitary and not ok:
        prefix = refuse_prefix or f"sanitize_refused:{rel}"
        detail = "; ".join(str(e) for e in errors[:4]) or "unknown"
        raise RuntimeError(f"{prefix}: {detail}")
    rel_n = str(rel or "").replace("\\", "/").strip("/")
    sk = stage_key or rel_n
    if write_committed:
        from interview_mux.write_staging import write_committed_json

        write_committed_json(ctx, rel_n, out, stage_key=sk)
    else:
        ctx.write_json(rel_n, out, stage_key=sk, skip_handoff=skip_handoff)
    try:
        from interview_mux.artifact_sanitize.reentry import sanitary_content_hash
        from interview_mux.thrash_hardening import note_authority_undo_attempt

        undo = note_authority_undo_attempt(
            ctx,
            artifact=rel_n,
            action_class=str(action_class or sk or "admit_sanitized"),
            content_hash=sanitary_content_hash(out, keys=content_keys),
        )
        if undo.get("halt"):
            raise RuntimeError(
                f"authority_undo_thrash:{rel_n}: "
                + str(undo.get("reason") or "oscillation")
            )
    except RuntimeError:
        raise
    except Exception:
        pass
    return out
