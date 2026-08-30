"""Dimension → stage remutate for listen_delight floors (no soft-pass)."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

REMUTATE_REL = "mastering/listen_delight_remutate.json"
MAX_ATTEMPTS = 2

_DIM_STAGES: dict[str, list[str]] = {
    "nugget_retention": [
        "full_master_ranking",
        "nugget_layup_compose",
        "edl",
        "mix",
        "listen_delight_audit",
    ],
    "cut_integrity": ["edl", "junction_snip_qa", "mix", "listen_delight_audit"],
    "conversation_fit": ["edl", "mix", "listen_delight_audit"],
    "sonic_weave": ["mix", "listen_delight_audit"],
    "mode_coherence": ["gap_framing_compose", "edl", "mix", "listen_delight_audit"],
    "finishability": ["full_master_ranking", "edl", "mix", "listen_delight_audit"],
    # recommendability is a composite of other dims. Ranking/EDL/mix remutate
    # cannot raise it independently (exec_1970 looped 70+ attempts).
}


def plan_listen_delight_remutate(
    ctx: RunContext, *, failed_dimensions: list[str]
) -> dict[str, Any]:
    prior = (
        ctx.read_json(REMUTATE_REL)
        if ctx.artifact_exists(REMUTATE_REL)
        else {}
    )
    attempt = int((prior or {}).get("attempt") or 0) + 1
    stages: list[str] = []
    for dim in failed_dimensions or []:
        mapped = _DIM_STAGES.get(str(dim))
        if not mapped:
            continue
        for sid in mapped:
            if sid not in stages:
                stages.append(sid)
    assembly_ready = ctx.artifact_exists("master/assembly_preview.wav") or ctx.is_done("edl")
    failed_set = {str(x) for x in (failed_dimensions or [])}
    if assembly_ready and "cut_integrity" not in failed_set:
        # Ranking/layup rewind cannot raise retention without destroying seated air.
        # Finish MusicGen/SFX + mix, then re-audit. cut_integrity must rewind EDL.
        skip = {
            "full_master_ranking",
            "nugget_layup_compose",
            "gap_framing_compose",
            "edl",
        }
        stages = [s for s in stages if s not in skip]
        if not ctx.is_done("mmaudio_sfx"):
            lead = ["mmaudio_sfx", "mix", "listen_delight_audit"]
        else:
            lead = ["mix", "listen_delight_audit"]
        stages = lead + [s for s in stages if s not in lead]
    elif assembly_ready and "cut_integrity" in failed_set:
        lead = ["edl", "junction_snip_qa", "mix", "listen_delight_audit"]
        stages = lead + [s for s in stages if s not in lead]
    plan = {
        "version": 1,
        "attempt": attempt,
        "max_attempts": MAX_ATTEMPTS,
        "failed_dimensions": list(failed_dimensions or []),
        "from_stages": stages,
        "from_stage": stages[0] if stages else None,
        "exhausted": attempt > MAX_ATTEMPTS or not stages,
    }
    ctx.write_json(REMUTATE_REL, plan)
    return plan


def apply_listen_delight_remutate(
    ctx: RunContext, plan: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Pack under-duration selection for nugget_retention and clear stage markers."""
    doc = plan or (
        ctx.read_json(REMUTATE_REL) if ctx.artifact_exists(REMUTATE_REL) else None
    )
    if not isinstance(doc, dict) or doc.get("exhausted"):
        return {"ok": False, "reason": "exhausted_or_missing"}

    try:
        from interview_mux.homunculus.issues import emit_issue
        from interview_mux.homunculus.runtime import is_homunculus_run, recovery_allowed

        if is_homunculus_run(ctx) and not recovery_allowed(ctx, "listen_delight_audit"):
            emit_issue(
                ctx,
                kind="listen_delight_remutate",
                source="listen_delight_remutate",
                stage_id="listen_delight_audit",
                implicated=list(doc.get("from_stages") or ["listen_delight_audit"]),
                evidence={"failed_dimensions": doc.get("failed_dimensions")},
            )
            return {"ok": False, "reason": "awaiting_homunculus_analysis"}
    except Exception:
        pass

    notes: list[str] = []
    failed = {str(x) for x in (doc.get("failed_dimensions") or [])}
    assembly_ready = ctx.artifact_exists("master/assembly_preview.wav") or ctx.is_done("edl")
    if (
        "nugget_retention" in failed
        and not assembly_ready
        and ctx.artifact_exists("master/selection.json")
    ):
        try:
            from interview_mux.creative_delivery import enforce_creative_selection_edit

            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                packed = enforce_creative_selection_edit(
                    ctx, sel, stage="listen_delight_remutate"
                )
                if isinstance(packed, dict):
                    ctx.write_json("master/selection.json", packed)
                    notes.append("packed_selection_for_nugget_retention")
        except Exception as exc:
            notes.append(f"pack_failed:{exc}")

    cleared: list[str] = []
    from_stage = str(doc.get("from_stage") or "")
    preserve_edl = (
        from_stage in {"mmaudio_sfx", "mix", "listen_delight_audit"}
        or (assembly_ready and "nugget_retention" in failed)
    ) and "cut_integrity" not in failed
    for sid in doc.get("from_stages") or []:
        if preserve_edl and sid in {
            "full_master_ranking",
            "nugget_layup_compose",
            "edl",
            "assembly_preview",
        }:
            continue
        marker = ctx.run_dir / ".stage_done" / str(sid)
        if marker.is_file():
            marker.unlink(missing_ok=True)
            cleared.append(str(sid))
    extra_clear = (
        ("mix", "junction_snip_qa", "listen_delight_audit")
        if preserve_edl
        else ("edl", "assembly_preview", "mix", "junction_snip_qa", "listen_delight_audit")
    )
    for sid in extra_clear:
        marker = ctx.run_dir / ".stage_done" / sid
        if marker.is_file():
            marker.unlink(missing_ok=True)
            if sid not in cleared:
                cleared.append(sid)

    ctx.log(
        f"listen_delight remutate attempt {doc.get('attempt')}: "
        f"dims={doc.get('failed_dimensions')} cleared={cleared[:8]} notes={notes}",
        level="warning",
        stage="listen_delight_audit",
    )
    return {
        "ok": True,
        "cleared": cleared,
        "from_stage": doc.get("from_stage"),
        "notes": notes,
    }
