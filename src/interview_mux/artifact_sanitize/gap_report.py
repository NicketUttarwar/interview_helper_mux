"""Sanitize understanding/gap_report.json (W1 — no seat/omit authority).

Seat clamp + omit-flag sync live in air_contract (W3). This module only does
shape/dedupe/rebase/opening grammar/scaffolding/lock stamp/coverage refuse.
"""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_sanitize.halt import sanitize_refused_message
from interview_mux.artifact_sanitize.reentry import (
    sanitize_reentry_guard,
    stamp_matches,
    stamp_sanitize_meta,
)
from interview_mux.artifact_sanitize.types import SanitizeResult

REL = "understanding/gap_report.json"
_CONTENT_KEYS = ["interviewer_lines", "gaps", "opening_orientation"]


def _selection_order(ctx: Any) -> list[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return []
    try:
        sel = ctx.read_json("master/selection.json")
    except Exception:
        return []
    if not isinstance(sel, dict):
        return []
    return [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]


def _selection_lock_token(ctx: Any) -> str:
    if not ctx.artifact_exists("master/selection.json"):
        return ""
    try:
        sel = ctx.read_json("master/selection.json")
    except Exception:
        return ""
    if not isinstance(sel, dict):
        return ""
    lock = sel.get("order_lock") if isinstance(sel.get("order_lock"), dict) else {}
    return str(sel.get("order_content_hash") or lock.get("order_content_hash") or "")


def _line_target(row: dict[str, Any]) -> str:
    return str(
        row.get("targets_segment_id")
        or row.get("target_segment_id")
        or row.get("after_segment_id")
        or row.get("segment_id")
        or ""
    )


def _is_orientation(row: dict[str, Any]) -> bool:
    if row.get("episode_orientation") is True:
        return True
    lid = str(row.get("line_id") or "").lower()
    return "orientation" in lid or lid.startswith("vo_orient")


def _is_required_line(row: dict[str, Any]) -> bool:
    if row.get("required") is True:
        return True
    if _is_orientation(row):
        return True
    cat = str(row.get("line_category") or "").lower()
    return cat in {"episode_orientation", "episode_preface"}


def _scaffolding_codes(text: str) -> set[str]:
    """Live hard-structure + name-attribution codes (not dead spoken_scaffolding)."""
    try:
        from interview_mux.spoken_meta_lint import (
            is_hard_structure_violation,
            spoken_structure_hits,
        )

        hits = spoken_structure_hits(text) or []
    except Exception:
        return set()
    codes = {str(h) for h in hits}
    return {
        c
        for c in codes
        if is_hard_structure_violation(c) or c == "spoken_name_attribution"
    }


def _strip_scaffolding(row: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Rewrite required scaffold hits; omit optional lines. Never omit required."""
    text = str(row.get("text") or row.get("script") or "")
    if not text.strip():
        return row, False
    codes = _scaffolding_codes(text)
    if not codes:
        return row, False
    out = dict(row)
    if _is_required_line(row):
        try:
            from interview_mux.spoken_meta_lint import rewrite_speaker_role_labels

            healed = rewrite_speaker_role_labels(text)
        except Exception:
            healed = text
        changed = False
        if healed != text:
            out["text"] = healed
            if "script" in out:
                out["script"] = healed
            changed = True
            text = healed
        # Remaining hits stay active (do not omit) so sanitize/ensure refuse.
        if _scaffolding_codes(text):
            return out, True
        return out, changed
    out["skipped_optional"] = True
    out["omit"] = True
    out["skip_reason"] = out.get("skip_reason") or "sanitize_scaffolding"
    return out, True


def sanitize_gap_report(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    actions: list[dict[str, Any]] = []
    errors: list[str] = []
    out = dict(doc or {})

    if stamp_matches(out, content_keys=_CONTENT_KEYS):
        return SanitizeResult(
            doc=out,
            ok=True,
            errors=[],
            artifact_rel=REL,
            metrics={"skipped": "sanitary_hash_match"},
        )

    # 1. shape
    lines = out.get("interviewer_lines")
    if lines is None:
        out["interviewer_lines"] = []
        lines = out["interviewer_lines"]
        actions.append({"action": "init_interviewer_lines"})
    if not isinstance(lines, list):
        errors.append("interviewer_lines not a list")
        return SanitizeResult(doc=out, ok=False, errors=errors, artifact_rel=REL)

    gaps = out.get("gaps")
    if gaps is not None and not isinstance(gaps, list):
        errors.append("gaps not a list")
        return SanitizeResult(doc=out, ok=False, errors=errors, artifact_rel=REL)

    order = _selection_order(ctx)
    order_set = set(order)

    # 1b. Drop omit stubs missing schema-required fields (tier-D mint class).
    # opening_orientation.omitted remains the durable waive; phantom rows with
    # only line_id/delivery block pre-flush commit.
    _SCHEMA_REQ = ("gap_type", "text", "targets_segment_id", "placement", "delivery")
    healed: list[dict[str, Any]] = []
    for row in lines:
        if not isinstance(row, dict):
            continue
        omitted = bool(
            row.get("skipped_optional")
            or row.get("air_script_omit")
            or row.get("omit")
        )
        missing = [k for k in _SCHEMA_REQ if k not in row or row.get(k) is None]
        # text may be "" for omitted; key must exist. gap_type/targets/placement/delivery must be non-empty strings.
        if "text" in missing:
            pass
        else:
            for k in ("gap_type", "targets_segment_id", "placement", "delivery"):
                if k not in missing and not str(row.get(k) or "").strip():
                    missing.append(k)
        if omitted and missing:
            actions.append(
                {
                    "action": "drop_incomplete_omit_stub",
                    "line_id": str(row.get("line_id") or ""),
                    "missing": missing[:8],
                }
            )
            continue
        healed.append(row)
    if len(healed) != len(lines):
        out["interviewer_lines"] = healed
        lines = healed

    # 2. dedupe lines
    seen_ids: set[str] = set()
    seen_sig: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in lines:
        if not isinstance(row, dict):
            continue
        lid = str(row.get("line_id") or "").strip()
        tgt = _line_target(row)
        text = str(row.get("text") or row.get("script") or "").strip().lower()
        if lid and lid in seen_ids:
            actions.append({"action": "dedupe_line_id", "line_id": lid})
            continue
        sig = (text, tgt, str(row.get("placement") or ""))
        if text and sig in seen_sig:
            actions.append({"action": "dedupe_text_target", "line_id": lid or tgt})
            continue
        if lid:
            seen_ids.add(lid)
        if text:
            seen_sig.add(sig)
        deduped.append(row)
    if len(deduped) != len(lines):
        out["interviewer_lines"] = deduped
        lines = deduped

    # 3. rebase / drop off-air (non-orientation)
    if order_set:
        kept: list[dict[str, Any]] = []
        dropped = 0
        try:
            from interview_mux.gap_framing import rebase_gap_lines_to_selection

            rebased = rebase_gap_lines_to_selection(ctx, {"interviewer_lines": lines})
            if isinstance(rebased, dict) and isinstance(rebased.get("interviewer_lines"), list):
                lines = list(rebased["interviewer_lines"])
                actions.append({"action": "rebase_gap_lines_to_selection"})
        except TypeError:
            raise
        except Exception:
            pass
        for row in lines:
            if not isinstance(row, dict):
                continue
            if _is_orientation(row):
                kept.append(row)
                continue
            tgt = _line_target(row)
            if tgt and tgt not in order_set:
                dropped += 1
                continue
            kept.append(row)
        if dropped:
            actions.append({"action": "drop_lines_off_air", "count": dropped})
        out["interviewer_lines"] = kept
        lines = kept

        if isinstance(gaps, list):
            g_kept = []
            g_drop = 0
            for g in gaps:
                if not isinstance(g, dict):
                    continue
                after = str(g.get("after_segment_id") or g.get("after") or "")
                before = str(g.get("before_segment_id") or g.get("before") or "")
                if after and after not in order_set and before and before not in order_set:
                    g_drop += 1
                    continue
                g_kept.append(g)
            if g_drop:
                out["gaps"] = g_kept
                actions.append({"action": "drop_gaps_off_air", "count": g_drop})

    # 4. opening grammar — at most one orientation
    orient_idxs = [i for i, r in enumerate(lines) if isinstance(r, dict) and _is_orientation(r)]
    if len(orient_idxs) > 1:
        keep_i = orient_idxs[0]
        new_lines = []
        for i, r in enumerate(lines):
            if i in orient_idxs and i != keep_i:
                actions.append({"action": "drop_extra_orientation", "line_id": r.get("line_id")})
                continue
            new_lines.append(r)
        out["interviewer_lines"] = new_lines
        lines = new_lines

    # 5. scaffolding strip (omit optional only; rewrite/refuse required)
    scrubbed: list[dict[str, Any]] = []
    for row in lines:
        if not isinstance(row, dict):
            continue
        fixed, changed = _strip_scaffolding(row)
        if changed:
            if fixed.get("omit") or fixed.get("skipped_optional"):
                actions.append(
                    {
                        "action": "omit_scaffolding",
                        "line_id": fixed.get("line_id"),
                    }
                )
            else:
                actions.append(
                    {
                        "action": "rewrite_scaffolding",
                        "line_id": fixed.get("line_id"),
                    }
                )
        scrubbed.append(fixed)
    out["interviewer_lines"] = scrubbed
    lines = scrubbed

    # Active scaffolding remaining → refuse
    for row in lines:
        if not isinstance(row, dict):
            continue
        if row.get("skipped_optional") or row.get("omit"):
            continue
        still = _scaffolding_codes(str(row.get("text") or row.get("script") or ""))
        if still:
            errors.append(
                f"scaffolding_active:{row.get('line_id') or _line_target(row)}"
            )

    # 6. coverage refuse — compose-thin only (F7)
    try:
        from interview_mux.artifact_sanitize.config import sanitize_section

        min_cov = float(
            (sanitize_section("gap").get("min_layup_coverage"))
            or (sanitize_section("layup").get("min_layup_coverage"))
            or 0.70
        )
    except Exception:
        min_cov = 0.70
    authority = bool(out.get("nugget_layup_authority"))
    if authority and order:
        active = [
            r
            for r in lines
            if isinstance(r, dict)
            and not r.get("skipped_optional")
            and not r.get("omit")
            and not _is_orientation(r)
        ]
        # Only refuse when compose marked partial / thin — not after Pass B omits.
        compose_thin = bool(out.get("_meta", {}).get("compose_thin")) if isinstance(
            out.get("_meta"), dict
        ) else False
        status = str(out.get("status") or out.get("compose_status") or "").lower()
        if compose_thin or status in {"partial", "blocked", "incomplete"}:
            cov = len(active) / max(1, len(order))
            if cov < min_cov:
                errors.append(f"layup_coverage_below_floor:{cov:.3f}<{min_cov}")

    # 7. stamp
    lock = _selection_lock_token(ctx)
    out = stamp_sanitize_meta(
        out,
        ok=not errors,
        source="artifact_sanitize.gap_report",
        actions_n=len(actions),
        extra={"selection_order_hash": lock},
        content_keys=_CONTENT_KEYS,
    )

    if not isinstance(out.get("interviewer_lines"), list) and not isinstance(
        out.get("gaps"), list
    ):
        errors.append("gap_report missing gaps and interviewer_lines")

    return SanitizeResult(
        doc=out,
        actions=actions,
        ok=not errors,
        errors=errors,
        artifact_rel=REL,
        metrics={"actions": len(actions), "selection_lock": lock[:16]},
    )


def gap_doc_sanitary_errors(ctx: Any, doc: Any) -> list[str]:
    """W1 errors for an in-memory gap_report (HF-5 courtesy / Pass-2 refuse)."""
    from interview_mux.artifact_sanitize.config import block_consumers_on_unsanitary

    if not block_consumers_on_unsanitary():
        return []
    if not isinstance(doc, dict):
        return [f"{REL} invalid"]
    if stamp_matches(doc, content_keys=_CONTENT_KEYS):
        meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
        stamp = meta.get("sanitize") if isinstance(meta.get("sanitize"), dict) else {}
        if stamp.get("ok") is True:
            return []
    result = sanitize_gap_report(ctx, dict(doc))
    if result.ok and not result.actions:
        return []
    if not result.ok:
        return list(result.errors or ["gap sanitize refused"])
    return [
        "gap_needs_sanitize:"
        + ",".join(str(a.get("action") or "") for a in (result.actions or [])[:6])
    ]


def gap_sanitary_errors(ctx: Any) -> list[str]:
    from interview_mux.artifact_sanitize.config import block_consumers_on_unsanitary

    if not block_consumers_on_unsanitary():
        return []
    if not ctx.artifact_exists(REL):
        return [f"{REL} missing"]
    try:
        doc = ctx.read_json(REL)
    except Exception as exc:
        return [f"{REL} unreadable: {exc}"]
    return gap_doc_sanitary_errors(ctx, doc)


def commit_gap_report_doc(
    ctx: Any,
    doc: dict[str, Any],
    *,
    reason: str = "",
    skip_handoff: bool = False,
    stage_key: str | None = None,
) -> SanitizeResult:
    """Write + sanitize gap_report (sole preferred persist path for repair modules)."""
    from interview_mux.artifact_sanitize.one_writer import (
        admitting,
        begin_admit,
        end_admit,
    )
    from interview_mux.artifact_sanitize.reentry import sanitary_content_hash

    nested_admit = admitting(ctx)
    if not nested_admit:
        begin_admit(ctx)

    prior_gap: Any = None
    try:
        if ctx.artifact_exists(REL):
            prior_gap = ctx.read_json(REL)
    except Exception:
        prior_gap = None

    try:
        from interview_mux.seat_authority import frozen_seat_write_allowed

        enda_reason = str(reason or stage_key or "").strip()
        if not frozen_seat_write_allowed(ctx, REL, reason=enda_reason):
            kept = prior_gap if isinstance(prior_gap, dict) else dict(doc)
            return SanitizeResult(
                doc=kept,
                ok=True,
                metrics={"skipped": "seat_freeze_not_enda"},
            )
    except ImportError:
        pass

    try:
        with sanitize_reentry_guard(ctx) as nested:
            if nested:
                _persist_gap_disk(ctx, doc, skip_handoff=skip_handoff, stage_key=stage_key)
                _cascade_gap_spoken(ctx, prior_gap, doc, stage_key=stage_key or reason)
                return SanitizeResult(doc=doc, ok=True, metrics={"skipped": "reentry"})
            before_hash = sanitary_content_hash(doc, keys=_CONTENT_KEYS)
            result = sanitize_gap_report(ctx, dict(doc))
            from interview_mux.artifact_sanitize.audit import write_sanitize_audit

            write_sanitize_audit(
                ctx, result, stage_key="gap_report", mode=reason or "commit"
            )
            out = result.doc if result.ok and isinstance(result.doc, dict) else dict(doc)
            # One disk write — sanitized when ok; otherwise input (still sole writer).
            _persist_gap_disk(ctx, out, skip_handoff=skip_handoff, stage_key=stage_key)
            after_hash = sanitary_content_hash(out, keys=_CONTENT_KEYS)
            try:
                from interview_mux.thrash_hardening import note_authority_undo_attempt

                undo = note_authority_undo_attempt(
                    ctx,
                    artifact=REL,
                    action_class=str(stage_key or reason or "commit_gap_report"),
                    content_hash=after_hash,
                )
                if undo.get("halt"):
                    raise RuntimeError(
                        f"authority_undo_thrash:{REL}: "
                        + str(undo.get("reason") or "oscillation")
                    )
            except RuntimeError:
                raise
            except Exception:
                pass
            try:
                from interview_mux.artifact_sanitize.invalidate import (
                    maybe_invalidate_after_sanitize,
                )

                maybe_invalidate_after_sanitize(
                    ctx,
                    REL,
                    before_hash=before_hash,
                    after_hash=after_hash,
                    ok=result.ok,
                    actions_n=len(result.actions or []),
                )
            except Exception:
                pass
            _cascade_gap_spoken(ctx, prior_gap, out, stage_key=stage_key or reason)
            if not result.ok:
                # Still report refuse, but document is on disk (availability).
                return SanitizeResult(
                    doc=out,
                    ok=False,
                    errors=list(result.errors or []),
                    actions=list(result.actions or []),
                    artifact_rel=REL,
                    metrics={**(result.metrics or {}), "persisted_unsanitary": True},
                )
            return SanitizeResult(
                doc=out,
                ok=True,
                errors=[],
                actions=list(result.actions or []),
                artifact_rel=REL,
                metrics=dict(result.metrics or {}),
            )
    finally:
        if not nested_admit:
            end_admit(ctx)


def _persist_gap_disk(
    ctx: Any,
    doc: dict[str, Any],
    *,
    skip_handoff: bool,
    stage_key: str | None,
) -> None:
    """Persist gap under admit — prefer mirrored/schema path when possible."""
    # file_store bypasses schema so repair modules can persist cleaned shape
    # without requiring full LLM schema. Callers already hold _one_writer_admit.
    from interview_mux.file_store import write_json as fs_write_json

    if skip_handoff:
        try:
            from interview_mux.write_staging import write_mirrored_json

            write_mirrored_json(ctx, REL, doc)
            return
        except Exception:
            pass
    fs_write_json(ctx.path(REL), doc)


def _cascade_gap_spoken(
    ctx: Any,
    prior_gap: Any,
    new_report: dict[str, Any],
    *,
    stage_key: str | None,
) -> None:
    if int(getattr(ctx, "_vo_synth_lease", 0) or 0) > 0:
        return
    try:
        from interview_mux.vo_synthesis_audit import (
            maybe_propagate_gap_spoken_text_change,
            _SPOKEN_TEXT_CASCADE_STAGES,
        )

        maybe_propagate_gap_spoken_text_change(
            ctx,
            prior_report=prior_gap if isinstance(prior_gap, dict) else None,
            new_report=new_report,
            stage=stage_key or "gap_report_write",
        )
    except Exception as exc:
        consumers_done = False
        try:
            from interview_mux.vo_synthesis_audit import _SPOKEN_TEXT_CASCADE_STAGES

            consumers_done = any(ctx.is_done(sid) for sid in _SPOKEN_TEXT_CASCADE_STAGES)
        except Exception:
            consumers_done = False
        if consumers_done:
            raise RuntimeError(
                f"spoken text cascade failed (fail-closed; consumers exist): {exc}"
            ) from exc
        try:
            ctx.log(
                f"spoken text cascade failed (non-fatal): {exc}",
                level="warning",
                stage=stage_key or "gap_report_write",
            )
        except Exception:
            pass


def run_gap_report_sanitize(ctx: Any) -> None:
    """Delivery stage after nugget_layup_compose."""
    from interview_mux.artifact_sanitize.reentry import sanitary_content_hash
    from interview_mux.file_store import write_json as fs_write_json

    with sanitize_reentry_guard(ctx) as nested:
        if nested:
            return
        framing_yes = False
        try:
            from interview_mux.gap_vo_gates import gap_framing_enabled

            framing_yes = bool(gap_framing_enabled(ctx))
        except Exception:
            framing_yes = False
        if not ctx.artifact_exists(REL):
            # Framing skip: empty sanitary stub may complete.
            # GRS-B2: framing Yes → seed empty stub for evidence but refuse done.
            doc: dict[str, Any] = {
                "version": 1,
                "interviewer_lines": [],
                "gaps": [],
                "_meta": {
                    "producer": "gap_report_sanitize_empty_seed",
                    "empty_stub": True,
                    "framing_enabled": framing_yes,
                },
            }
            before_hash = ""
        else:
            loaded = ctx.read_json(REL)
            if not isinstance(loaded, dict):
                raise RuntimeError("gap_report_sanitize: gap_report invalid")
            doc = loaded
            before_hash = sanitary_content_hash(doc, keys=_CONTENT_KEYS)
        result = sanitize_gap_report(ctx, doc)
        from interview_mux.artifact_sanitize.audit import write_sanitize_audit

        write_sanitize_audit(ctx, result, stage_key="gap_report_sanitize", mode="stage")
        if not result.ok:
            raise RuntimeError(
                sanitize_refused_message("gap_report", result.errors)
            )
        fs_write_json(ctx.path(REL), result.doc)
        after_hash = sanitary_content_hash(result.doc, keys=_CONTENT_KEYS)
        try:
            from interview_mux.artifact_sanitize.invalidate import (
                maybe_invalidate_after_sanitize,
            )

            maybe_invalidate_after_sanitize(
                ctx,
                REL,
                before_hash=before_hash,
                after_hash=after_hash,
                ok=result.ok,
                actions_n=len(result.actions or []),
            )
        except Exception:
            pass
        from interview_mux.stage_completion import heal_or_raise

        heal_or_raise(ctx, "gap_report_sanitize")
