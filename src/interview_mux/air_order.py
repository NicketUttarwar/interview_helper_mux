"""Sealed AirOrder generation — one live bundle of lock, clips, glue, and VO keys.

Adapters propose the next generation; ``commit`` writes it atomically or
``rollback`` leaves generation N unchanged. Mix/junction/finalize refuse mixed gens.
"""

from __future__ import annotations

import copy
import hashlib
import shutil
from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

AIR_ORDER_REL = "master/air_order.json"
SNAPSHOT_REL = "master/air_order_snapshot.json"
ROLLBACK_ASSEMBLY_REL = "master/air_order_rollback/assembly.wav"
SELECTION_REL = "master/selection.json"
EDL_REL = "master/edl.json"
RENDER_LEDGER_REL = "master/render_ledger.json"
ASSEMBLY_LEDGER_REL = "master/assembly_ledger.json"

_INPUT_HASH_RELS = (
    "master/transitions.json",
    "understanding/gap_report.json",
    "understanding/sound_design_plan.json",
    "understanding/nugget_layup_plan.json",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ids(doc: dict[str, Any] | None, key: str = "ordered_segment_ids") -> list[str]:
    if not isinstance(doc, dict):
        return []
    return [str(s) for s in (doc.get(key) or []) if s]


def _sha_rel(ctx: RunContext, rel: str) -> str | None:
    path = ctx.final_path(*rel.split("/"))
    if not path.is_file():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return None


def _read_dict(ctx: RunContext, rel: str) -> dict[str, Any] | None:
    if not ctx.artifact_exists(rel):
        return None
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return None
    return doc if isinstance(doc, dict) else None


def _committing(ctx: RunContext) -> bool:
    return bool(getattr(ctx, "_air_order_committing", False))


def _set_committing(ctx: RunContext, value: bool) -> None:
    setattr(ctx, "_air_order_committing", value)


def _write_json(ctx: RunContext, rel: str, data: dict[str, Any]) -> None:
    nested = _committing(ctx)
    if not nested:
        _set_committing(ctx, True)
    try:
        ctx.write_json(rel, data, skip_handoff=True)
    finally:
        if not nested:
            _set_committing(ctx, False)


def generation(ctx: RunContext) -> int:
    live = read_live(ctx)
    try:
        return int(live.get("generation") or 0)
    except (TypeError, ValueError):
        return 0


def read_live(ctx: RunContext) -> dict[str, Any]:
    doc = _read_dict(ctx, AIR_ORDER_REL)
    if isinstance(doc, dict):
        doc.setdefault("version", 1)
        doc.setdefault("generation", 0)
        return doc
    return {
        "version": 1,
        "generation": 0,
        "source": None,
        "ordered_segment_ids": [],
        "speech_clip_ids": [],
        "glue_occupancy": {},
        "vo_keys": [],
        "input_hashes": {},
    }


def propose(ctx: RunContext) -> dict[str, Any]:
    """Snapshot the next candidate generation without writing it."""
    return {
        "generation": generation(ctx) + 1,
        "selection": copy.deepcopy(_read_dict(ctx, SELECTION_REL) or {}),
        "edl": copy.deepcopy(_read_dict(ctx, EDL_REL) or {}),
    }


def snapshot(ctx: RunContext) -> dict[str, Any]:
    """Persist live JSON (+ assembly wav) so ``rollback`` can restore generation N."""
    snap: dict[str, Any] = {
        "version": 1,
        "captured_at": _now(),
        "generation": generation(ctx),
        "selection": _read_dict(ctx, SELECTION_REL),
        "edl": _read_dict(ctx, EDL_REL),
        "air_order": _read_dict(ctx, AIR_ORDER_REL),
        "render_ledger": _read_dict(ctx, RENDER_LEDGER_REL),
        "assembly_ledger": _read_dict(ctx, ASSEMBLY_LEDGER_REL),
        "assembly_copied": False,
    }
    _write_json(ctx, SNAPSHOT_REL, snap)
    src = ctx.final_path("master", "assembly.wav")
    if src.is_file():
        dest = ctx.final_path(*ROLLBACK_ASSEMBLY_REL.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dest)
            snap["assembly_copied"] = True
            _write_json(ctx, SNAPSHOT_REL, snap)
        except OSError:
            pass
    return snap


def rollback(ctx: RunContext) -> dict[str, Any]:
    """Restore the last snapshot. Live show is generation N again."""
    snap = _read_dict(ctx, SNAPSHOT_REL)
    if not isinstance(snap, dict):
        return {"ok": False, "error": "no_snapshot"}
    nested = _committing(ctx)
    if not nested:
        _set_committing(ctx, True)
    try:
        for rel, key in (
            (SELECTION_REL, "selection"),
            (EDL_REL, "edl"),
            (AIR_ORDER_REL, "air_order"),
            (RENDER_LEDGER_REL, "render_ledger"),
            (ASSEMBLY_LEDGER_REL, "assembly_ledger"),
        ):
            doc = snap.get(key)
            if isinstance(doc, dict):
                ctx.write_json(rel, doc, skip_handoff=True)
        if snap.get("assembly_copied"):
            src = ctx.final_path(*ROLLBACK_ASSEMBLY_REL.split("/"))
            dest = ctx.final_path("master", "assembly.wav")
            if src.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
    finally:
        if not nested:
            _set_committing(ctx, False)
    return {"ok": True, "generation": snap.get("generation")}


def _exclude_unseated(
    selection: dict[str, Any],
    clip_ids: list[str],
    *,
    source: str,
) -> dict[str, Any]:
    from interview_mux.order_hash import bump_order_lock

    sel_ids = _ids(selection)
    clip_set = set(clip_ids)
    drop = [sid for sid in sel_ids if sid not in clip_set]
    out = dict(selection)
    out["ordered_segment_ids"] = list(clip_ids)
    excl = list(out.get("excluded_segment_ids") or [])
    have = {
        str(row.get("segment_id") if isinstance(row, dict) else row)
        for row in excl
    }
    for sid in drop:
        if sid not in have:
            excl.append({"segment_id": sid, "reason": "edl_unseated"})
            have.add(sid)
    out["excluded_segment_ids"] = excl
    return bump_order_lock(out, source=source)


def _vo_keys(edl: dict[str, Any] | None) -> list[dict[str, Any]]:
    keys: list[dict[str, Any]] = []
    if not isinstance(edl, dict):
        return keys
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict) or str(clip.get("type") or "") != "vo_pickup":
            continue
        keys.append(
            {
                "line_id": str(clip.get("line_id") or ""),
                "script_hash": str(clip.get("script_hash") or ""),
                "speaker_id": str(
                    clip.get("voice_speaker_id") or clip.get("speaker_id") or ""
                ),
                "wav_rel": str(clip.get("source_path") or ""),
            }
        )
    return keys


def _glue_occupancy(ctx: RunContext, edl: dict[str, Any] | None) -> dict[str, Any]:
    """One owner per air target: orientation > gap interviewer > transition > layup."""
    occupancy: dict[str, Any] = {}
    gap = _read_dict(ctx, "understanding/gap_report.json") or {}
    try:
        from interview_mux.opening_orientation import is_episode_orientation
    except Exception:
        def is_episode_orientation(_ln: dict[str, Any]) -> bool:  # type: ignore[misc]
            return False

    def _prio(line: dict[str, Any]) -> int:
        if is_episode_orientation(line):
            return 0
        origin = str(line.get("origin") or line.get("source") or "").lower()
        if "layup" in origin or str(line.get("line_id") or "").startswith("vo_layup"):
            return 3
        return 1

    for line in gap.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        if line.get("skipped_optional") or line.get("air_script_omit") or line.get("skip"):
            continue
        target = str(
            line.get("targets_segment_id")
            or line.get("target_segment_id")
            or line.get("before_segment_id")
            or ""
        )
        if not target:
            continue
        row = occupancy.get(target)
        cand = {
            "owner": "episode_orientation"
            if is_episode_orientation(line)
            else ("nugget_layup" if _prio(line) >= 3 else "gap_interviewer"),
            "line_id": str(line.get("line_id") or ""),
            "priority": _prio(line),
        }
        if row is None or int(cand["priority"]) < int(row.get("priority") or 99):
            occupancy[target] = cand

    if isinstance(edl, dict):
        for clip in edl.get("clips") or []:
            if not isinstance(clip, dict) or str(clip.get("type") or "") != "transition":
                continue
            after = str(clip.get("after_segment_id") or "")
            before = str(clip.get("before_segment_id") or "")
            key = f"{after}->{before}" if after and before else after or before
            if key and key not in occupancy:
                occupancy[key] = {
                    "owner": "transition",
                    "line_id": str(clip.get("line_id") or ""),
                    "priority": 2,
                }
    return occupancy


def _resolve_glue_slots(ctx: RunContext) -> list[str]:
    notes: list[str] = []
    try:
        from interview_mux.opening_adjacency_repair import (
            suppress_opening_layup_when_orientation_owns_slot,
        )

        notes.extend(suppress_opening_layup_when_orientation_owns_slot(ctx) or [])
    except Exception:
        pass
    return notes


def _stamp_gen(doc: dict[str, Any], gen: int) -> dict[str, Any]:
    out = dict(doc)
    out["air_order_generation"] = int(gen)
    return out


def _input_hashes(ctx: RunContext) -> dict[str, str | None]:
    return {rel: _sha_rel(ctx, rel) for rel in _INPUT_HASH_RELS}


def _reconcile(
    ctx: RunContext,
    selection: dict[str, Any] | None,
    edl: dict[str, Any] | None,
    *,
    source: str,
    exclude_unseated: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    from interview_mux.order_hash import (
        bump_order_lock,
        copy_order_lock_if_clips_match,
        edl_speech_clip_ids,
        order_drift_heal_action,
        stamp_order_hash,
    )

    sel = dict(selection) if isinstance(selection, dict) else None
    edl_out = dict(edl) if isinstance(edl, dict) else None
    if sel is None and edl_out is None:
        return None, None, "ok"
    action = "ok"
    if sel is not None and edl_out is not None:
        action = order_drift_heal_action(sel, edl_out)
        clip_ids = edl_speech_clip_ids(edl_out)
        if action == "exclude_unseated" and exclude_unseated and clip_ids:
            sel = _exclude_unseated(sel, clip_ids, source=source)
            edl_out = copy_order_lock_if_clips_match(sel, edl_out)
            action = "exclude_unseated"
        elif action == "stamp":
            if not sel.get("order_lock"):
                sel = bump_order_lock(sel, source=source)
            sel = stamp_order_hash(sel)
            edl_out = copy_order_lock_if_clips_match(sel, edl_out)
        elif action == "ok" and clip_ids:
            try:
                edl_out = copy_order_lock_if_clips_match(sel, edl_out)
            except ValueError:
                pass
        elif action == "rebuild":
            raise ValueError(
                "selection_edl_order_drift: speech clip order diverges from "
                "ordered_segment_ids — rebuild EDL from selection (run_edl) "
                "before commit"
            )
    elif sel is not None:
        if not sel.get("order_lock"):
            sel = bump_order_lock(sel, source=source)
        sel = stamp_order_hash(sel)
    elif edl_out is not None:
        edl_out = stamp_order_hash(edl_out)
    return sel, edl_out, action


def commit(
    ctx: RunContext,
    *,
    selection: dict[str, Any] | None = None,
    edl: dict[str, Any] | None = None,
    source: str = "air_order",
    exclude_unseated: bool = True,
    snapshot_first: bool = True,
) -> dict[str, Any]:
    """Write a sealed generation. On failure the caller should ``rollback``."""
    if (
        snapshot_first
        and not _committing(ctx)
        and not getattr(ctx, "_air_order_hold_snapshot", False)
    ):
        snapshot(ctx)
    glue_notes = _resolve_glue_slots(ctx)
    sel_in = selection if isinstance(selection, dict) else _read_dict(ctx, SELECTION_REL)
    edl_in = edl if isinstance(edl, dict) else _read_dict(ctx, EDL_REL)
    sel_out, edl_out, action = _reconcile(
        ctx,
        sel_in,
        edl_in,
        source=source,
        exclude_unseated=exclude_unseated,
    )
    gen = generation(ctx) + 1
    if isinstance(sel_out, dict):
        sel_out = _stamp_gen(sel_out, gen)
    if isinstance(edl_out, dict):
        try:
            from interview_mux.media_ip_cta import clamp_edl_speech_away_from_never_touch

            edl_out, _ = clamp_edl_speech_away_from_never_touch(ctx, edl_out)
        except Exception:
            pass
        edl_out = _stamp_gen(edl_out, gen)
    occupancy = _glue_occupancy(ctx, edl_out)
    from interview_mux.order_hash import edl_speech_clip_ids

    clip_ids = edl_speech_clip_ids(edl_out) if isinstance(edl_out, dict) else []
    ordered = _ids(sel_out)
    bundle = {
        "version": 1,
        "generation": gen,
        "source": source,
        "committed_at": _now(),
        "action": action,
        "ordered_segment_ids": ordered,
        "speech_clip_ids": clip_ids,
        "glue_occupancy": occupancy,
        "glue_notes": glue_notes[:24],
        "vo_keys": _vo_keys(edl_out),
        "input_hashes": _input_hashes(ctx),
        "air_order_generation": gen,
    }
    _set_committing(ctx, True)
    try:
        if isinstance(sel_out, dict):
            from interview_mux.air_order_boundary import commit_selection_mutation

            sel_out = commit_selection_mutation(
                ctx,
                sel_out,
                producer="air_order",
                stage_key=source,
                checkpoint_mode="detect",
                skip_handoff=True,
                skip_checkpoint=False,
            )
        if isinstance(edl_out, dict):
            ctx.write_json(EDL_REL, edl_out, skip_handoff=True)
        ctx.write_json(AIR_ORDER_REL, bundle, skip_handoff=True)
    finally:
        _set_committing(ctx, False)
    return bundle


def write_live_edl(
    ctx: RunContext,
    edl: dict[str, Any],
    *,
    source: str = "edl",
) -> dict[str, Any]:
    """Production EDL persist — bumps generation (or no-ops while already committing)."""
    from interview_mux.artifact_sanitize.one_writer import (
        admitting,
        begin_admit,
        end_admit,
    )

    nested_admit = admitting(ctx)
    if not nested_admit:
        begin_admit(ctx)
    try:
        edl_out = edl
        before_token = ""
        try:
            if ctx.artifact_exists(EDL_REL):
                prev = ctx.read_json(EDL_REL)
                from interview_mux.thrash_hardening import edl_content_authority_token

                before_token = edl_content_authority_token(
                    prev if isinstance(prev, dict) else None
                )
        except Exception:
            before_token = ""
        try:
            from interview_mux.media_ip_cta import clamp_edl_speech_away_from_never_touch

            edl_out, _nt_rows = clamp_edl_speech_away_from_never_touch(ctx, edl)
        except Exception:
            edl_out = edl
        if _committing(ctx):
            ctx.write_json(EDL_REL, edl_out, skip_handoff=True)
            return read_live(ctx)
        live = commit(ctx, edl=edl_out, source=source)
        # EDL rewrite without content change must not look unseated / force remaster.
        src_l = str(source or "").lower()
        if src_l not in {"mix", "stamp_after_mix", "master_finalize"}:
            try:
                from interview_mux.thrash_hardening import maybe_bump_seating_for_edl_rewrite

                maybe_bump_seating_for_edl_rewrite(
                    ctx,
                    before_token=before_token,
                    after_edl=edl_out if isinstance(edl_out, dict) else None,
                    source=source,
                )
            except Exception:
                pass
        return live
    finally:
        if not nested_admit:
            end_admit(ctx)


def write_live_selection(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    source: str = "selection",
) -> dict[str, Any]:
    from interview_mux.artifact_sanitize.one_writer import (
        admitting,
        begin_admit,
        end_admit,
    )

    nested_admit = admitting(ctx)
    if not nested_admit:
        begin_admit(ctx)
    try:
        if _committing(ctx):
            ctx.write_json(SELECTION_REL, selection, skip_handoff=True)
            return read_live(ctx)
        return commit(ctx, selection=selection, source=source)
    finally:
        if not nested_admit:
            end_admit(ctx)


def stamp_after_mix(ctx: RunContext) -> dict[str, Any]:
    """Tag render_ledger + air_order with the live generation after a successful mix."""
    live = read_live(ctx)
    gen = int(live.get("generation") or 0)
    ledger = _read_dict(ctx, RENDER_LEDGER_REL)
    if isinstance(ledger, dict) and gen:
        ledger = dict(ledger)
        ledger["air_order_generation"] = gen
        _write_json(ctx, RENDER_LEDGER_REL, ledger)
        live["assembly_sha"] = ledger.get("assembly")
    else:
        live["assembly_sha"] = None
    live["mix_stamped_at"] = _now()
    live["air_order_generation"] = gen
    _write_json(ctx, AIR_ORDER_REL, live)
    return live


def live_generation_matches(ctx: RunContext) -> bool:
    live = read_live(ctx)
    gen = int(live.get("generation") or 0)
    if not gen:
        return True
    edl = _read_dict(ctx, EDL_REL) or {}
    sel = _read_dict(ctx, SELECTION_REL) or {}
    try:
        edl_gen = int(edl.get("air_order_generation") or 0)
        sel_gen = int(sel.get("air_order_generation") or 0)
    except (TypeError, ValueError):
        return False
    if edl_gen and edl_gen != gen:
        return False
    if sel_gen and sel_gen != gen:
        return False
    return True


def mix_wav_fresh_versus_edl(ctx: RunContext) -> bool:
    """True when final ``master/assembly.wav`` exists and is not older than live EDL."""
    asm = ctx.final_path("master", "assembly.wav")
    edl = ctx.final_path("master", "edl.json")
    if not asm.is_file() or not edl.is_file():
        return False
    try:
        asm_m = asm.stat().st_mtime
        edl_m = edl.stat().st_mtime
    except OSError:
        return False
    return asm_m + 1.0 >= edl_m


def mix_outputs_seated(ctx: RunContext) -> bool:
    """Mix-done: flushed wav + live EDL, not autopsy commitment.

    Junction / finalize still use ``mix_committed_for_live_gen``.
    """
    if not mix_wav_fresh_versus_edl(ctx):
        return False
    if not live_generation_matches(ctx):
        return False
    sel = _read_dict(ctx, SELECTION_REL)
    edl = _read_dict(ctx, EDL_REL)
    if not isinstance(sel, dict):
        return True
    sel_ids = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
    if not sel_ids:
        return True
    from interview_mux.order_hash import edl_speech_clip_ids, get_order_lock, order_drift_heal_action

    if (
        order_drift_heal_action(sel, edl if isinstance(edl, dict) else None)
        not in {"ok", "stamp"}
    ):
        return False
    lock = get_order_lock(sel) or {}
    lock_ids = [str(s) for s in (lock.get("ordered_segment_ids") or []) if s]
    clip_ids = edl_speech_clip_ids(edl if isinstance(edl, dict) else {})
    seated = lock_ids or sel_ids
    if clip_ids and seated and clip_ids != seated:
        return False
    return True


def mix_stale_versus_live(ctx: RunContext) -> bool:
    """True when assembly is not the mix of the live AirOrder generation."""
    if not ctx.artifact_exists("master/assembly.wav") or not ctx.artifact_exists(EDL_REL):
        return False
    if not live_generation_matches(ctx):
        return True
    try:
        from interview_mux.seam_autopsy import verify_commitment

        result = verify_commitment(ctx)
    except Exception:
        return False
    if not isinstance(result, dict):
        return False
    if result.get("status") == "committed":
        return False
    reasons = [str(r) for r in (result.get("reasons") or [])]
    return "assembly_not_rendered_from_current_edl" in reasons


def mix_committed_for_live_gen(ctx: RunContext) -> bool:
    if not ctx.artifact_exists("master/assembly.wav"):
        return False
    if mix_stale_versus_live(ctx):
        return False
    try:
        from interview_mux.seam_autopsy import verify_commitment

        result = verify_commitment(ctx)
    except Exception:
        return False
    return isinstance(result, dict) and result.get("status") == "committed"


def assert_consumer(ctx: RunContext, stage: str) -> None:
    """Fail closed when mix/junction/finalize would read a mixed generation."""
    sel = _read_dict(ctx, SELECTION_REL)
    edl = _read_dict(ctx, EDL_REL)
    if sel is None or edl is None:
        return
    from interview_mux.order_hash import order_drift_heal_action

    action = order_drift_heal_action(sel, edl)
    if action in {"rebuild", "exclude_unseated"}:
        raise SystemExit(
            "selection_edl_order_drift: speech clip order diverges from "
            f"ordered_segment_ids (heal={action}) — sealed commit required before {stage}"
        )
    if stage in {"mix", "junction_snip_qa", "master_finalize"} and not live_generation_matches(
        ctx
    ):
        live = generation(ctx)
        edl_gen = (edl or {}).get("air_order_generation")
        raise SystemExit(
            "assembly_not_rendered_from_current_edl: air_order generation mismatch "
            f"(live={live} edl={edl_gen}) — remaster mix from the sealed EDL"
        )
    if stage in {"junction_snip_qa", "master_finalize"}:
        try:
            from interview_mux.seam_autopsy import verify_commitment

            result = verify_commitment(ctx)
        except Exception:
            result = {}
        reasons = (
            [str(r) for r in (result.get("reasons") or [])] if isinstance(result, dict) else []
        )
        if isinstance(result, dict) and result.get("status") == "committed":
            return
        if "selection_edl_order_drift" in reasons:
            raise SystemExit(
                "selection_edl_order_drift: verify_commitment reasons=" + ",".join(reasons)
            )
        if "assembly_not_rendered_from_current_edl" in reasons or mix_stale_versus_live(ctx):
            raise SystemExit(
                "assembly_not_rendered_from_current_edl: verify_commitment reasons="
                + ",".join(reasons)
            )
