"""Product recovery controller — one typed playbook per (stage, signature).

Not an e2e waiver layer. Playbooks produce a legal artifact or escalate.
Budget: structural classes — one attempt per signature; transient classes — up to three.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

RECOVERY_LOG_REL = "operator/recovery_actions.jsonl"
REMEDIATION_LOG_REL = "operator/remediation_log.jsonl"
FRAMING_VO_MAX_OBSERVATIONS = 3

# Explicit consumer → producer for fingerprint restamp (never guess).
# When the error names no producer, heal resumes this producer — never the
# later gate consumer alone (absolute producer-before-consumer for FP class).
FINGERPRINT_PRODUCER_BY_CONSUMER: dict[str, str] = {
    "sonic_context_build": "sonic_context_build",
    "topic_coverage_audit": "content_brief_reanchor",
    "sound_design_palettes": "sound_design_palettes",
    "edl": "full_master_ranking",
    "edl_narrative_audit": "edl",
    "assembly_preview": "edl",
    "mix": "edl",
    "junction_snip_qa": "mix",
    "master_finalize": "junction_snip_qa",
    "vo_synthesize": "vo_line_adjudicate",
    "vo_line_adjudicate": "nugget_layup_compose",
    "transitions": "nugget_layup_compose",
}


def resolve_fingerprint_heal_resume(
    *,
    message: str,
    gate_stage: str = "",
    body_from: str = "",
    mode: str = "delivery",
    ctx: RunContext | None = None,
    named_producers: list[str] | None = None,
) -> str:
    """Always resume the fingerprint producer; never a later gate consumer.

    Resolution order:
    1. Named producers from the error text (or ``named_producers``)
    2. Artifact path in the message → registry / preferred_fill / STAGE path map
    3. ``FINGERPRINT_PRODUCER_BY_CONSUMER[gate]``
    4. Earlier ``body_from`` only when it is not a later consumer than gate
    5. Gate as last resort
    """
    import re

    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    low = str(message or "").lower()
    order = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)

    producers: list[str] = list(named_producers or [])
    if not producers:
        producers.extend(
            p
            for _, p in re.findall(
                r"([a-z0-9_./-]+\.json)\s+fingerprint mismatch[^\n]*?producer\s+([a-z0-9_]+)",
                low,
            )
        )

    paths = re.findall(
        r"([a-z0-9_./-]+\.json)\s+fingerprint mismatch",
        low,
    )
    if not paths:
        paths = re.findall(r"([a-z0-9_./-]+\.json)", low)

    try:
        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

        for rel in paths:
            for sid, path in STAGE_ARTIFACT_DISK_PATHS.items():
                if path == rel:
                    producers.append(sid)
    except Exception:
        pass

    if ctx is not None:
        stored: dict = {}
        try:
            if ctx.artifact_exists("run_meta.json"):
                meta = ctx.read_json("run_meta.json")
                if isinstance(meta, dict):
                    stored = meta.get("artifact_fingerprints") or {}
        except Exception:
            stored = {}
        for rel in paths:
            entry = stored.get(rel) if isinstance(stored, dict) else None
            if isinstance(entry, dict):
                ps = str(entry.get("producer_stage") or "").strip()
                if ps:
                    producers.append(ps)
            try:
                from interview_mux.artifact_completeness import preferred_fill_stage

                fill = preferred_fill_stage(rel, ctx)
                if fill:
                    producers.append(fill)
            except Exception:
                pass

    ranked = [p for p in producers if p in order]
    gate = str(gate_stage or "").strip()
    # HM-2 2A: unnamed sonic/palettes fingerprint self-pins unless the brief is named.
    if gate in {"sonic_context_build", "sound_design_palettes"}:
        if "content_brief.json" in low or "content_brief_reanchor" in low:
            return "content_brief_reanchor"
        return gate
    if ranked:
        return min(ranked, key=lambda p: order.index(p))
    mapped = FINGERPRINT_PRODUCER_BY_CONSUMER.get(gate)
    if mapped and mapped in order:
        return mapped

    body = str(body_from or "").strip()
    # Never prefer a later gate consumer over an earlier body_from candidate.
    if body in order and gate in order and order.index(body) < order.index(gate):
        return body
    if body in order:
        return body
    if gate in order:
        return gate
    return body or gate or ""


@dataclass
class RecoveryResult:
    status: str  # recovered | escalate
    playbook_id: str
    signature: str
    resume_stage: str
    artifacts_written: list[str] = field(default_factory=list)
    detail: str = ""


def classify_error_class(stage_id: str, exc: BaseException) -> str | None:
    """Map a stage exception to a closed error_class (no fuzzy driver substrings)."""
    msg = str(exc).lower()
    stage = str(stage_id or "")
    if stage == "ideal_cuts_materialize" and (
        "no valid cuts after snap" in msg or "bind_mode requires boundaries" in msg
    ):
        return "empty_snap"
    if stage in {"nugget_layup_compose", "gap_framing_recompose"} and "never_touch_cta" in msg:
        return "never_touch_cta"
    if stage in {"nugget_layup_compose", "gap_framing_recompose"} and (
        "layup_coverage" in msg
        or "min_layup_coverage" in msg
        or "nugget layup qc failed" in msg
        or "nugget_layup_qc_failed" in msg
        or "layup authority" in msg
    ):
        return "layup_coverage"
    if stage == "edl" and "preceding framing vo" in msg:
        return "framing_vo_unseated"
    if stage == "edl" and "targets_segment_id" in msg and "does not match gap_report" in msg:
        return "orientation_target_mismatch"
    if stage in {"edl", "mix", "junction_snip_qa", "master_finalize"} and (
        "naked seam" in msg or "naked_seam" in msg
    ):
        return "naked_seam"
    if stage in {"mix", "mmaudio_sfx"} and "mmaudio_qa" in msg:
        return "mmaudio_qa_missing"
    if stage in {"mix", "mmaudio_sfx", "sfx_prompt_craft"} and (
        "missing wav for asset_id" in msg
        or "missing wav for asset" in msg
        or "speech-free theme" in msg
        or "opening_music reserved" in msg
        or "pin mmaudio_sfx" in msg
        or "refusing silent duration" in msg
    ):
        return "sdp_theme_wavs_missing"
    if stage in {"master_finalize", "mix"} and (
        "episode_close_outro" in msg or "missing_episode_close_outro" in msg
    ):
        return "episode_close_outro"
    if stage in {"edl", "mix", "junction_snip_qa", "master_finalize", "gap_framing_recompose"} and (
        "nugget_layup_plan_stale" in msg
        or "stale vs selection" in msg
        or "layup plan stale" in msg
    ):
        return "layup_stale"
    if (
        "hitch_listen_restage" in msg
        or "incomplete_cut_restage_hitch" in msg
    ):
        return "hitch_listen_restage"
    if stage in {"edl", "g1_vo", "g1_vo_pickup"} and (
        "g1 vo pickup missing" in msg or "stale_or_missing_pickup" in msg
    ):
        return "missing_g1_pickup"
    if "listen delight floors" in msg or "listen_delight_floors" in msg:
        return "listen_delight_floors"
    if "fingerprint mismatch" in msg:
        return "fingerprint_mismatch"
    if stage == "speaker_roles" and (
        "rerun_stage" in msg
        and ("diarization" in msg or "speaker_diarization" in msg)
    ):
        return "mixed_diarization"
    if stage in {"edl", "mix"} and "overlapping source range" in msg:
        return "overlapping_source_range"
    if stage == "edl" and "unknown segment_id" in msg:
        return "unknown_nle_split_child"
    if stage == "nugget_layup_compose" and (
        "cta_omit_applied" in msg
        or (
            "rerun_stage" in msg
            and "selection" in msg
            and any(
                token in msg
                for token in (
                    "sponsor",
                    "media_ip",
                    "subscribe",
                    "monetiz",
                    "cta",
                    "outro",
                    "credits",
                    "direct listener",
                )
            )
        )
    ):
        return "selection_cta_omit"
    reason = str(getattr(exc, "reason", "") or "").lower()
    # Include narrative QC stages: exec_11630 #19 prose was
    # "speech clips do not match final selection ordered_segment_ids" on
    # edl_narrative_audit — prior matcher required "speech clip order" only.
    if stage in {
        "edl",
        "edl_narrative",
        "edl_narrative_audit",
        "mix",
        "junction_snip_qa",
        "master_finalize",
    } and (
        "selection_edl_order_drift" in msg
        or "ordered_segment_ids drifted" in msg
        or "speech clip order diverges" in msg
        or "speech clip order" in msg
        or "speech clips do not match" in msg
    ):
        return "selection_edl_order_drift"
    if (
        "assembly_not_rendered_from_current_edl" in msg
        or "air_order generation mismatch" in msg
        or reason == "assembly_not_rendered_from_current_edl"
    ):
        return "assembly_not_rendered_from_current_edl"
    if (
        "opening_slot_conflict" in msg
        or "duplicate opening layup" in msg
        or "opening_orientation_owns_target" in msg
    ):
        return "opening_slot_conflict"
    if (
        reason == "post_master_quality_missing"
        or "post_master_quality_missing" in msg
        or "post-master quality artifact is missing" in msg
    ):
        return "post_master_quality_missing"
    if "high_gap_unframed" in msg or (
        "high gap segment" in msg and "no interviewer line" in msg
    ):
        return "high_gap_unframed"
    if type(exc).__name__ == "PublishabilityBlocked":
        blocked_class = str(getattr(exc, "error_class", "") or "").strip()
        if blocked_class:
            return blocked_class
    # Stringified publishability / junction residual blocks (plain RuntimeError).
    if (
        "incomplete_cut_unresolved" in msg
        or "critical_incomplete_cut_residuals" in msg
        or (
            "publishability blocked" in msg
            and "pre_mix" in msg
            and ("incomplete_cut" in msg or "on_a_roll" in msg or "critical_residuals" in msg)
        )
        or (
            stage in {"mix", "junction_snip_qa", "master_finalize"}
            and "critical_residuals" in msg
            and ("on_a_roll" in msg or "junction" in msg)
        )
    ):
        return "incomplete_cut_unresolved"
    # Broad VO coverage → always classify to seated coverage (resume vo_synthesize).
    # Keep skip/omit on the contract ladder (checked first).
    if "vo contract" in msg or (
        "seated synthesize" in msg
        and ("skip/omit" in msg or "skipped_optional" in msg)
    ):
        return "vo_contract_repair"
    if "missing from gap_report" in msg or "missing from gap" in msg:
        return "vo_contract_repair"
    if (
        "vo coverage not rendered" in msg
        or "seated synthesize vo not rendered" in msg
        or "seated synthesize vo missing" in msg
        or ("seated synthesize" in msg and "missing wav" in msg)
        or "synthetic vo does not match" in msg
        or ("synthesized gap line" in msg and "missing wav" in msg)
        or "gap vo lines missing wav" in msg
        or "transition pairs missing wav" in msg
        or "transition pairs still missing wav" in msg
        or (
            "vo" in msg
            and "coverage" in msg
            and any(tok in msg for tok in ("missing", "stale", "not rendered", "wav"))
        )
        or (
            stage in {"edl", "edl_narrative_audit", "mix", "master_finalize", "assembly_preview"}
            and "stage input check blocked" in msg
            and "vo" in msg
        )
    ):
        return "vo_seated_coverage"
    # Narrow producer pins — seed/finalize before catch-alls.
    if "seed order:" in msg and "complete " in msg and "before running" in msg:
        return "seed_order_prereq"
    if "redundant with framing" in msg or "redundant_framing" in msg:
        return "redundant_framing_transitions"
    if stage in {"master_finalize", "mix", "junction_snip_qa"} and (
        ("assembly_ledger" in msg and "missing" in msg)
        or ("seam_autopsy" in msg and "missing" in msg)
        or "edl.json missing" in msg
        or ("render_ledger" in msg and "missing" in msg)
    ):
        return "finalize_input_missing"
    # Multi-blocker "stale upstream X, Y" must clear every producer — do this
    # before assembly-only remap so transitions+assembly don't drop a pin.
    if "stale upstream" in msg or "marked stale" in msg:
        return "upstream_stale_rerun"
    if "assembly_stale_versus_edl" in msg or (
        "delivery epoch" in msg and "assembly_stale" in msg
    ):
        return "assembly_not_rendered_from_current_edl"
    if "air_script" in msg and "drift" in msg:
        return "air_script_omit_sync"
    return None


CLASSIFIED_PLAYBOOKS = frozenset(
    {
        "empty_snap",
        "never_touch_cta",
        "layup_coverage",
        "orientation_target_mismatch",
        "unknown_nle_split_child",
        "overlapping_source_range",
        "framing_vo_unseated",
        "naked_seam",
        "mmaudio_qa_missing",
        "sdp_theme_wavs_missing",
        "episode_close_outro",
        "missing_g1_pickup",
        "layup_stale",
        "hitch_listen_restage",
        "listen_delight_floors",
        "fingerprint_mismatch",
        "mixed_diarization",
        "selection_cta_omit",
        "selection_edl_order_drift",
        "assembly_not_rendered_from_current_edl",
        "opening_slot_conflict",
        "post_master_quality_missing",
        "high_gap_unframed",
        "never_touch_zeroed_keep",
        "vo_audibility_drift",
        "opening_orientation_inaudible",
        "pending_write_barrier",
        "musicgen_theme_failed",
        "incomplete_cut_unresolved",
        "pmq_incomplete_ship_walk",
        "vo_seated_coverage",
        "vo_contract_repair",
        "upstream_stale_rerun",
        "air_script_omit_sync",
        "seed_order_prereq",
        "finalize_input_missing",
        "redundant_framing_transitions",
    }
)

TRANSIENT_ERROR_CLASSES = frozenset(
    {
        "vo_seated_coverage",
        "vo_contract_repair",
        "mmaudio_qa_missing",
        "sdp_theme_wavs_missing",
        "musicgen_theme_failed",
        "upstream_stale_rerun",
        "seed_order_prereq",
        "finalize_input_missing",
    }
)


def has_classified_playbook(error_class: str | None) -> bool:
    return bool(error_class) and error_class in CLASSIFIED_PLAYBOOKS


def signature_key(stage_id: str, error_class: str) -> str:
    return f"{stage_id}:{error_class}"


def _log_path(ctx: RunContext) -> Path:
    dest = Path(ctx.run_dir) / RECOVERY_LOG_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def _read_actions(ctx: RunContext) -> list[dict[str, Any]]:
    path = _log_path(ctx)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _parse_signature_key(signature: str) -> tuple[str, str]:
    parts = str(signature or "").split(":", 1)
    if len(parts) != 2:
        return "", ""
    return parts[0].strip(), parts[1].strip()


def _recovery_log_count(ctx: RunContext, signature: str) -> int:
    return sum(
        1 for row in _read_actions(ctx) if str(row.get("signature") or "") == signature
    )


def _identical_failure_count(ctx: RunContext, stage_id: str, error_class: str) -> int:
    if not stage_id or not error_class:
        return 0
    from interview_mux.identical_failures import failure_signature_by_class, read_identical_failures

    halt_sig = failure_signature_by_class(failed_stage=stage_id, error_class=error_class)
    row = (read_identical_failures(ctx).get("signatures") or {}).get(halt_sig) or {}
    return int(row.get("count") or 0)


def _mirror_recovery_to_identical_failures(
    ctx: RunContext,
    signature: str,
    *,
    resume_attempted: str = "",
) -> None:
    """R12c: mirror recovery log attempts into identical_failures.json."""
    stage_id, error_class = _parse_signature_key(signature)
    if not error_class or not has_classified_playbook(error_class):
        return
    from interview_mux.identical_failures import record_class_failure

    target = _recovery_log_count(ctx, signature)
    ident = _identical_failure_count(ctx, stage_id, error_class)
    while ident < target:
        record_class_failure(
            ctx,
            failed_stage=stage_id,
            error_class=error_class,
            resume_attempted=resume_attempted,
        )
        ident += 1


def _append_action(ctx: RunContext, row: dict[str, Any]) -> None:
    path = _log_path(ctx)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    sig = str(row.get("signature") or "")
    if sig:
        _mirror_recovery_to_identical_failures(
            ctx,
            sig,
            resume_attempted=str(row.get("resume_stage") or row.get("playbook_id") or ""),
        )
    try:
        from interview_mux.forensics_error_ledger import record_from_recovery_action
        from interview_mux.forensics_minor_fixes import (
            record_from_recovery_action as record_minor_heal,
        )

        record_from_recovery_action(ctx, row)
        record_minor_heal(ctx, row)
    except Exception:
        pass


def append_remediation_log(ctx: RunContext, action: str, detail: str = "") -> None:
    """Append an operator-visible remediation row (omit/heal actions)."""
    path = Path(ctx.run_dir) / REMEDIATION_LOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": str(action or ""),
        "detail": str(detail or "")[:400],
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


_OMIT_PLAYBOOKS = frozenset(
    {
        "stamp_air_script_omits",
        "host_cta_omit",
        "stamp_valueless_skips",
        "skip_never_touch_cta_layups",
    }
)


def recovery_attempt_budget(error_class: str | None) -> int:
    if error_class in {"listen_delight_floors", "pmq_incomplete_ship_walk"}:
        try:
            from interview_mux.listen_delight_remutate import max_remutate_attempts

            return max_remutate_attempts()
        except Exception:
            return 3
    if error_class in TRANSIENT_ERROR_CLASSES:
        return 3
    return 1


def attempt_count(ctx: RunContext, signature: str) -> int:
    stage_id, error_class = _parse_signature_key(signature)
    log_count = _recovery_log_count(ctx, signature)
    if not error_class:
        return log_count
    return max(log_count, _identical_failure_count(ctx, stage_id, error_class))


def already_attempted(ctx: RunContext, signature: str) -> bool:
    return attempt_count(ctx, signature) >= 1


def budget_exhausted(
    ctx: RunContext,
    signature: str,
    error_class: str | None,
) -> bool:
    return attempt_count(ctx, signature) >= recovery_attempt_budget(error_class)


def vo_seats_fingerprint(ctx: RunContext) -> str:
    try:
        from interview_mux.air_script import load_air_script
        from interview_mux.mastering_plan_loader import load_plan_raw

        script = load_air_script(load_plan_raw(ctx)) or {}
        seats = script.get("vo_seats") if isinstance(script.get("vo_seats"), dict) else {}
        blob = json.dumps(seats, sort_keys=True, ensure_ascii=False)
    except Exception:
        blob = ""
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _signature_hash_hits(ctx: RunContext, signature: str, vo_seats_hash: str) -> int:
    n = 0
    for row in _read_actions(ctx):
        if str(row.get("signature") or "") != signature:
            continue
        if str(row.get("vo_seats_hash") or "") != vo_seats_hash:
            continue
        n += 1
    return n


def playbook_stamp_air_script_omits(ctx: RunContext) -> list[str]:
    from interview_mux.air_script import persist_air_script_omits_on_gap_report

    persist_air_script_omits_on_gap_report(ctx)
    written: list[str] = []
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        written.append("mastering/mastering_plan.json")
    if ctx.artifact_exists("understanding/gap_report.json"):
        written.append("understanding/gap_report.json")
    return written


def _result(
    *,
    status: str,
    playbook_id: str,
    signature: str,
    resume_stage: str,
    artifacts: list[str] | None = None,
    detail: str = "",
) -> RecoveryResult:
    return RecoveryResult(
        status=status,
        playbook_id=playbook_id,
        signature=signature,
        resume_stage=resume_stage,
        artifacts_written=list(artifacts or []),
        detail=detail,
    )


def playbook_stamp_valueless_skips(ctx: RunContext) -> list[str]:
    from interview_mux.nugget_layup import (
        PLAN_REL,
        prepare_layup_plan_for_persist,
        publish_layup_plan_to_gap_report,
        stamp_valueless_skips,
    )

    if not ctx.artifact_exists(PLAN_REL):
        return []
    plan = ctx.read_json(PLAN_REL)
    plan, notes = stamp_valueless_skips(ctx, plan if isinstance(plan, dict) else {})
    plan = prepare_layup_plan_for_persist(ctx, plan)
    ctx.write_json(PLAN_REL, plan, stage_key="nugget_layup_compose")
    publish_layup_plan_to_gap_report(ctx, plan)
    return [PLAN_REL] if notes else []


def playbook_orientation_retarget(ctx: RunContext) -> list[str]:
    from interview_mux.opening_orientation import retarget_orientation_to_open

    return retarget_orientation_to_open(ctx)


def playbook_place_episode_close(ctx: RunContext) -> list[str]:
    from interview_mux.listen_quality import place_episode_close_cue

    return place_episode_close_cue(ctx)


def playbook_ensure_mmaudio_qa(ctx: RunContext) -> list[str]:
    from interview_mux.delivery_recovery import ensure_mmaudio_qa_before_mix

    state = ensure_mmaudio_qa_before_mix(ctx, run_if_missing=True)
    if state.get("ok"):
        return [str(state.get("path") or "sound_design/mmaudio_qa.json")]
    return []


def playbook_generate_sdp_theme_wavs(ctx: RunContext) -> list[str]:
    from interview_mux.delivery_recovery import resume_theme_generation
    from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

    missing = missing_sdp_asset_wavs(ctx)
    resume_theme_generation(ctx)
    return [f"missing:{aid}" for aid in missing[:12]]


def playbook_ensure_g1(ctx: RunContext) -> list[str]:
    from interview_mux.delivery_recovery import ensure_g1_pickups

    result = ensure_g1_pickups(ctx)
    if isinstance(result, dict) and result.get("ok"):
        return list(result.get("synthesized") or []) or ["vo_pickup"]
    return []


def playbook_adopt_layup(ctx: RunContext) -> list[str]:
    from interview_mux.nugget_layup import PLAN_REL, adopt_layup_plan_to_selection

    result = adopt_layup_plan_to_selection(ctx, persist=True, stage="recovery_adopt_layup")
    if result.get("ok") and ctx.artifact_exists(PLAN_REL):
        return [PLAN_REL]
    return []


def playbook_hitch_listen_restage(ctx: RunContext) -> list[str]:
    from interview_mux.chapter_close_hitch import LATCH_REL, arm_hitch_listen_restage

    armed = arm_hitch_listen_restage(ctx)
    if armed or ctx.artifact_exists(LATCH_REL):
        return [LATCH_REL]
    return []


def playbook_listen_delight_remutate(ctx: RunContext) -> list[str]:
    from interview_mux.listen_delight import evaluate_listen_delight
    from interview_mux.listen_delight_remutate import (
        REMUTATE_REL,
        apply_listen_delight_remutate,
        plan_listen_delight_remutate,
    )

    result = evaluate_listen_delight(ctx)
    plan = plan_listen_delight_remutate(
        ctx, failed_dimensions=list(result.get("failed_dimensions") or [])
    )
    if plan.get("exhausted"):
        # Cap reached: restore best archived candidate when present, then refuse
        # further remutate (caller escalates — no infinite thrash).
        try:
            from interview_mux.aspirational_quality import (
                apply_best_quality_candidate,
                is_aspirational_enabled,
            )

            pick: dict[str, Any] = {"ok": False, "reason": "aspirational_off"}
            if is_aspirational_enabled(ctx):
                pick = apply_best_quality_candidate(ctx, family="listen_delight")
            doc = dict(plan)
            doc["terminate"] = doc.get("terminate") or "remutate_budget_exhausted"
            doc["pick_best"] = pick
            doc["status"] = "exhausted_terminated"
            ctx.write_json(REMUTATE_REL, doc)
        except Exception:
            pass
        return []
    applied = apply_listen_delight_remutate(ctx, plan)
    if applied.get("ok"):
        return [str(plan.get("from_stage") or "mix")]
    return []


def playbook_mint_reorder_glue(ctx: RunContext) -> list[str]:
    from interview_mux.seam_glue import ensure_seam_glue

    selection = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else {}
    )
    ordered = [
        str(s)
        for s in ((selection or {}).get("ordered_segment_ids") or [])
        if s
    ]
    if not ordered:
        return []
    manifest = (
        ctx.read_json("segments/manifest.json")
        if ctx.artifact_exists("segments/manifest.json")
        else {}
    )
    by_id = {
        str(s.get("segment_id") or ""): s
        for s in ((manifest or {}).get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }
    gap = (
        ctx.read_json("understanding/gap_report.json")
        if ctx.artifact_exists("understanding/gap_report.json")
        else None
    )
    transitions = (
        ctx.read_json("master/transitions.json")
        if ctx.artifact_exists("master/transitions.json")
        else {"transitions": []}
    )
    _bridges, transitions_doc, completeness = ensure_seam_glue(
        ctx,
        ordered=ordered,
        segments_by_id=by_id,
        gap_report=gap if isinstance(gap, dict) else None,
        transitions=transitions if isinstance(transitions, dict) else None,
        soft=False,
    )
    written = ["master/bridge_completeness.json"]
    if isinstance(transitions_doc, dict):
        ctx.write_json("master/transitions.json", transitions_doc)
        written.append("master/transitions.json")
    waived: set[str] = set()
    try:
        from interview_mux.air_script import native_handoff_segment_ids
        from interview_mux.mastering_plan_loader import load_plan_raw

        waived = native_handoff_segment_ids(load_plan_raw(ctx))
    except Exception:
        waived = set()
    if isinstance(completeness, dict) and not completeness.get("complete"):
        leftover = []
        for row in completeness.get("missing") or []:
            if not isinstance(row, dict):
                continue
            dest = str(
                row.get("before_segment_id")
                or row.get("before_id")
                or row.get("to")
                or ""
            )
            if dest and dest not in waived:
                leftover.append(dest)
        if leftover:
            return []
        # Remaining incompleteness is native_handoff / air_breathe — dressed, not missing glue.
        return written
    return written



def _unmark_stages(ctx: RunContext, *stage_ids: str, force: bool = False) -> None:
    for sid in stage_ids:
        if sid == "vo_synthesize" and not force:
            try:
                from interview_mux.delivery_guardrails import (
                    may_rewind_to_vo_synthesize,
                    record_wasted_work,
                )

                if not may_rewind_to_vo_synthesize(ctx):
                    record_wasted_work(
                        ctx,
                        event="refuse_vo_synthesize_rewind",
                        stage="vo_synthesize",
                        detail={"reason": "recovery_unmark"},
                    )
                    continue
            except Exception:
                pass
        (Path(ctx.run_dir) / ".stage_done" / sid).unlink(missing_ok=True)


def playbook_selection_edl_order_drift(ctx: RunContext) -> list[str]:
    from interview_mux.air_order import commit, rollback
    from interview_mux.order_hash import order_drift_heal_action
    from interview_mux.thrash_hardening import edl_content_authority_token
    from interview_mux.timeline_optimizer.config import optimizer_live_mutate_blocked
    from interview_mux.timeline_optimizer.daemon import stop_optimizer_daemon

    # A fuse / overlap union may have absorbed an id whose selection write was
    # refused under freeze — reconcile first, otherwise the rebuild below re-reads
    # a selection that can never match the EDL (exec_11871 seg_073).
    try:
        from interview_mux.edl_overlap_repair import retire_consumed_ids_from_selection

        retire_consumed_ids_from_selection(ctx)
    except Exception:
        pass
    sel = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else None
    )
    edl = ctx.read_json("master/edl.json") if ctx.artifact_exists("master/edl.json") else None
    if (
        isinstance(sel, dict)
        and sel.get("order_authority") == "timeline_optimizer"
        and optimizer_live_mutate_blocked(ctx)
    ):
        rollback(ctx)
        return ["master/selection.json"]
    action = order_drift_heal_action(
        sel if isinstance(sel, dict) else None,
        edl if isinstance(edl, dict) else None,
    )
    # Already aligned — do not burn the single structural EDL attempt on a
    # no-op commit / consumer re-exec (R6: fingerprint flip or escalate).
    if action == "ok":
        return []

    before_token = edl_content_authority_token(edl if isinstance(edl, dict) else None)
    before_sel_hash = (
        str(sel.get("order_content_hash") or "") if isinstance(sel, dict) else ""
    )

    if action == "exclude_unseated":
        commit(ctx, source="recovery_exclude_unseated")
    elif action == "stamp":
        commit(ctx, source="recovery_stamp")
    elif action == "rebuild":
        stop_optimizer_daemon(ctx)
        from interview_mux.stages.assembly import run_edl

        run_edl(ctx)
    else:
        return []

    after_edl = (
        ctx.read_json("master/edl.json") if ctx.artifact_exists("master/edl.json") else None
    )
    after_sel = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else None
    )
    after_token = edl_content_authority_token(
        after_edl if isinstance(after_edl, dict) else None
    )
    after_sel_hash = (
        str(after_sel.get("order_content_hash") or "")
        if isinstance(after_sel, dict)
        else ""
    )
    if after_token == before_token and after_sel_hash == before_sel_hash:
        # No authority fingerprint flip — refuse recovered so caller escalates
        # with the named producer pin instead of silent consumer re-exec.
        return []
    written: list[str] = []
    if ctx.artifact_exists("master/selection.json"):
        written.append("master/selection.json")
    if ctx.artifact_exists("master/edl.json"):
        written.append("master/edl.json")
    return written


def playbook_assembly_not_rendered(ctx: RunContext) -> list[str]:
    from interview_mux.delivery_guardrails import resolve_assembly_stale_resume

    pin = resolve_assembly_stale_resume(ctx)
    if pin == "edl":
        _unmark_stages(ctx, "edl", "mix", "junction_snip_qa", "master_finalize")
    elif pin == "junction_snip_qa":
        _unmark_stages(ctx, "junction_snip_qa", "master_finalize")
    else:
        _unmark_stages(ctx, "mix", "junction_snip_qa", "master_finalize")
    return ["master/edl.json"] if ctx.artifact_exists("master/edl.json") else []


def playbook_seed_order_prereq(ctx: RunContext, exc: BaseException) -> str:
    """Unmark or restamp the named seed-order prereq and return the resume stage.

    ``g1_vo_open`` is pickup-only for *record* holes: never unmark adjudicate into
    a synth loop. Synth-only G1 resumes ``vo_synthesize``.

    Live producers (SDP, music epoch, assembly WAV, sealed adjudicate): restamp
    the done marker and resume the consumer — never replan/regenerate and orphan
    downstream assets (forensics exec_10066 MusicGen thrash).

    Seed A↔B cycles with unchanged fingerprints refuse after detect_seed_cycle.
    """
    import re

    from interview_mux.delivery_guardrails import resolve_vo_synth_seed_resume
    from interview_mux.delivery_invariants import (
        apply_seed_order_heal,
        detect_seed_cycle,
        note_seed_resume,
        record_invariant_heal,
        resolve_g1_vo_open_resume,
    )

    msg = str(exc)
    m = re.search(r"complete\s+(\S+)\s+before", msg, flags=re.IGNORECASE)
    raw = m.group(1).strip() if m else ""
    if raw == "g1_vo_open":
        resume = resolve_g1_vo_open_resume(ctx)
        fp = ""
        try:
            if ctx.artifact_exists("understanding/vo_line_adjudication.json"):
                fp = str(
                    ctx.final_path(
                        "understanding", "vo_line_adjudication.json"
                    ).stat().st_size
                )
        except Exception:
            pass
        note_seed_resume(ctx, from_stage=resume, because_of="g1_vo_open", fingerprint=fp)
        if detect_seed_cycle(
            ctx, from_stage=resume, because_of="g1_vo_open", fingerprint=fp
        ):
            record_invariant_heal(
                ctx,
                kind="seed_cycle_refuse",
                stage=resume,
                detail={"raw": raw},
            )
            # Stay on synth when cycle involves adjudicate↔synth.
            return "vo_synthesize"
        return resume
    pin = resolve_vo_synth_seed_resume(raw, ctx) or raw
    if not pin:
        return pin
    fp = ""
    try:
        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

        rel = STAGE_ARTIFACT_DISK_PATHS.get(pin)
        if rel and ctx.artifact_exists(rel):
            fp = str(ctx.final_path(*rel.split("/")).stat().st_size)
    except Exception:
        pass
    note_seed_resume(ctx, from_stage=pin, because_of=raw or pin, fingerprint=fp)
    if detect_seed_cycle(ctx, from_stage=pin, because_of=raw or pin, fingerprint=fp):
        record_invariant_heal(
            ctx, kind="seed_cycle_refuse", stage=pin, detail={"raw": raw, "msg": msg[:120]}
        )
        m_consumer = re.search(r"before running\s+(\S+)", msg, flags=re.IGNORECASE)
        return (m_consumer.group(1).strip() if m_consumer else pin)
    return apply_seed_order_heal(
        ctx, pin, message=msg, unmark_fn=lambda c, s: _unmark_stages(c, s)
    )


def playbook_finalize_input_missing(ctx: RunContext, exc: BaseException) -> str:
    from interview_mux.delivery_guardrails import finalize_input_producer_pin

    pin = finalize_input_producer_pin(ctx, message=str(exc))
    if pin:
        _unmark_stages(ctx, pin)
    return pin


def playbook_opening_slot_conflict(ctx: RunContext) -> list[str]:
    from interview_mux.opening_adjacency_repair import (
        drop_orphan_opening_vo_when_native_orients,
        suppress_opening_layup_when_orientation_owns_slot,
    )

    suppress_opening_layup_when_orientation_owns_slot(ctx)
    drop_orphan_opening_vo_when_native_orients(ctx)
    if ctx.artifact_exists("master/edl.json"):
        from interview_mux.air_order import commit

        commit(ctx, source="opening_slot_conflict")
    written = []
    if ctx.artifact_exists("understanding/gap_report.json"):
        written.append("understanding/gap_report.json")
    if ctx.artifact_exists("master/edl.json"):
        written.append("master/edl.json")
    return written


def playbook_post_master_quality_missing(ctx: RunContext) -> list[str]:
    from interview_mux.post_master_quality import QUALITY_REL, run_post_master_quality

    run_post_master_quality(ctx, block=False)
    return [QUALITY_REL] if ctx.artifact_exists(QUALITY_REL) else []


def playbook_high_gap_unframed(ctx: RunContext) -> list[str]:
    from interview_mux.artifact_repairs import repair_gap_report
    from interview_mux.high_gap_vo import demote_uncovered_high_gaps

    written: list[str] = []
    repaired: dict[str, Any] | None = None
    if ctx.artifact_exists("understanding/gap_report.json"):
        doc = ctx.read_json("understanding/gap_report.json")
        if isinstance(doc, dict):
            repaired, _notes = repair_gap_report(ctx, doc)
            ctx.write_json("understanding/gap_report.json", repaired)
            written.append("understanding/gap_report.json")
    if repaired is None:
        return written
    # Compose persist already demotes leftovers after fill. Heal must do the
    # same so lint can commit when fill cannot cover (no key / exhausted).
    demoted = demote_uncovered_high_gaps(
        ctx, gap_report=repaired, origin="uncovered_after_fill"
    )
    if demoted and ctx.artifact_exists("understanding/gap_evaluations.json"):
        written.append("understanding/gap_evaluations.json")
    return written


def playbook_skip_never_touch_cta_layups(ctx: RunContext) -> list[str]:
    from interview_mux.nugget_layup import PLAN_REL, skip_never_touch_cta_layups

    plan = ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    out, _notes = skip_never_touch_cta_layups(ctx, plan if isinstance(plan, dict) else {})
    ctx.write_json(PLAN_REL, out)
    return [PLAN_REL]


def playbook_materialize_nle_split_children(ctx: RunContext) -> list[str]:
    from interview_mux.nle_state import materialize_all_nle_split_children

    materialize_all_nle_split_children(ctx)
    return ["segments/manifest.json"] if ctx.artifact_exists("segments/manifest.json") else []


def playbook_merge_overlapping_source_ranges(ctx: RunContext) -> list[str]:
    from interview_mux.edl_overlap_repair import repair_overlapping_source_ranges

    result = repair_overlapping_source_ranges(ctx)
    if not result.get("repaired"):
        return []
    written = ["master/edl.json"] if ctx.artifact_exists("master/edl.json") else []
    if ctx.artifact_exists("segments/manifest.json"):
        written.append("segments/manifest.json")
    return written


def playbook_host_cta_omit(ctx: RunContext) -> list[str]:
    from interview_mux.media_ip_cta import execute_cta_omit_from_needs, heal_on_air_cta_residue

    needs: list[dict[str, Any]] = []
    try:
        from interview_mux.homunculus.issues import read_issues

        for issue in read_issues(ctx):
            ev = issue.get("evidence") or {}
            msg = str(ev.get("message") or "")
            if "cta" in msg.lower() or "media_ip" in msg.lower():
                needs.append({"message": msg})
    except Exception:
        pass
    execute_cta_omit_from_needs(ctx, needs)
    heal_on_air_cta_residue(ctx)
    return ["master/selection.json"] if ctx.artifact_exists("master/selection.json") else []


def playbook_rebuild_edl(ctx: RunContext) -> list[str]:
    from interview_mux.homunculus.agenda import invalidate_downstream
    from interview_mux.stage_completion import edl_vo_bind_unsanitary

    # Snapshot before invalidate — structural clear can drop gap/plan evidence.
    unsanitary = edl_vo_bind_unsanitary(ctx)
    invalidate_downstream(ctx, "edl")
    # HE-2: an existing edl.json is not recovered while VO/bind is unsanitary.
    if unsanitary or edl_vo_bind_unsanitary(ctx):
        return []
    return ["master/edl.json"] if ctx.artifact_exists("master/edl.json") else []


def playbook_never_touch_zeroed_keep(ctx: RunContext) -> list[str]:
    try:
        from interview_mux.media_ip_cta import heal_nle_unplayable_keep_overrides

        heal_nle_unplayable_keep_overrides(ctx)
    except Exception:
        pass
    return playbook_rebuild_edl(ctx)


def playbook_vo_audibility_drift(ctx: RunContext) -> list[str]:
    from interview_mux.air_script import persist_air_script_omits_on_gap_report
    from interview_mux.opening_orientation import retarget_orientation_to_open

    persist_air_script_omits_on_gap_report(ctx)
    retarget_orientation_to_open(ctx)
    return playbook_rebuild_edl(ctx)


def playbook_opening_orientation_inaudible(ctx: RunContext) -> list[str]:
    return playbook_vo_audibility_drift(ctx)


def playbook_pending_write_barrier(ctx: RunContext) -> list[str]:
    from interview_mux.write_staging import stages_with_pending_writes

    pending = stages_with_pending_writes(ctx)
    return [f"pending:{s}" for s in pending]


def playbook_musicgen_theme_failed(ctx: RunContext) -> list[str]:
    from interview_mux.delivery_recovery import resume_theme_generation

    resume_theme_generation(ctx)
    return ["sound_design/assets/"]


def playbook_incomplete_cut_unresolved(ctx: RunContext) -> list[str]:
    from interview_mux.junction_snip_qa import QA_REL

    # Always pin junction — missing committed QA is exactly why mix is blocked.
    _unmark_stages(ctx, "junction_snip_qa", "mix", force=True)
    artifacts = [".stage_done/junction_snip_qa"]
    if ctx.artifact_exists(QA_REL):
        artifacts.append(QA_REL)
    return artifacts


def playbook_vo_seated_coverage(ctx: RunContext) -> list[str]:
    from interview_mux.vo_contract import repair_vo_contract_drift

    changed = repair_vo_contract_drift(ctx)
    _unmark_stages(ctx, "vo_synthesize", force=True)
    artifacts = [".stage_done/vo_synthesize"]
    if changed:
        artifacts.append("understanding/gap_report.json")
    return artifacts


def playbook_vo_contract_repair(ctx: RunContext) -> list[str]:
    from interview_mux.execution_contract import run_vo_contract_ladder

    result = run_vo_contract_ladder(ctx, consumer_stage="vo_contract_repair")
    _unmark_stages(ctx, "vo_line_adjudicate", "vo_synthesize", force=True)
    artifacts = list(result.artifacts)
    if result.contract_ok:
        return artifacts or ["understanding/gap_report.json"]
    return artifacts


def playbook_redundant_framing_transitions(ctx: RunContext) -> list[str]:
    from interview_mux.gap_framing import heal_redundant_framing_transitions

    out = heal_redundant_framing_transitions(ctx)
    if out.get("ok") and out.get("dropped"):
        marker = ctx.run_dir / ".stage_done" / "transitions"
        marker.unlink(missing_ok=True)
        return ["master/transitions.json"]
    return []


def playbook_upstream_stale_rerun(ctx: RunContext, *, consumer_stage: str = "") -> list[str]:
    from interview_mux.delivery_guardrails import upstream_stale_blockers

    stage = consumer_stage or "mix"
    blockers = list(upstream_stale_blockers(ctx, stage))

    def _disk_stale(rel: str) -> bool:
        if not ctx.artifact_exists(rel):
            return False
        try:
            doc = ctx.read_json(rel)
        except Exception:
            return False
        if not isinstance(doc, dict):
            return False
        meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
        return bool(meta.get("stale"))

    # Fallback when consumer is not in STALE_PREFLIGHT_CONSUMERS (or map gap):
    # still pin known stale producers from disk so we never escalate with [].
    if not blockers:
        if _disk_stale("master/transitions.json"):
            blockers.append("transitions")
        if _disk_stale("understanding/gap_report.json"):
            blockers.append("gap_report")
        if _disk_stale("understanding/sound_design_plan.json"):
            blockers.append("sound_design_plan")

    from interview_mux.delivery_guardrails import (
        resolve_assembly_stale_resume,
        resolve_gap_report_stale_producer,
    )

    def _producer_for_blocker(blocker: str) -> str:
        if blocker == "assembly_stale_versus_edl":
            return resolve_assembly_stale_resume(ctx)
        if blocker == "gap_report":
            return resolve_gap_report_stale_producer(ctx)
        if blocker == "sound_design_plan":
            return "sound_design_plan"
        if blocker == "transitions":
            return "transitions"
        return blocker

    producer_rels = {
        "transitions": "master/transitions.json",
        "gap_report": "understanding/gap_report.json",
        "sound_design_plan": "understanding/sound_design_plan.json",
    }
    cleared: list[str] = []
    for blocker in blockers:
        prod = _producer_for_blocker(blocker)
        _unmark_stages(ctx, prod)
        rel = producer_rels.get(blocker)
        if rel and ctx.artifact_exists(rel):
            try:
                doc = ctx.read_json(rel)
                if isinstance(doc, dict):
                    meta = dict(doc.get("_meta") or {})
                    if meta.get("stale"):
                        meta.pop("stale", None)
                        meta.pop("stale_reason", None)
                        doc = dict(doc)
                        doc["_meta"] = meta
                        ctx.write_json(rel, doc, skip_handoff=True)
            except Exception:
                pass
        cleared.append(prod)
    return cleared


def playbook_air_script_omit_sync(ctx: RunContext) -> list[str]:
    return playbook_stamp_air_script_omits(ctx)


def _write_recovery_escalation(
    ctx: RunContext,
    *,
    stage_id: str,
    error_class: str,
    signature: str,
    detail: str,
) -> None:
    """H0e: record recovery budget exhaustion for homunculus stall guard."""
    payload = {
        "stage_id": stage_id,
        "error_class": error_class,
        "signature": signature,
        "detail": detail,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        ctx.write_json("operator/recovery_escalation.json", payload, skip_handoff=True)
    except Exception:
        pass


def handle_stage_failure(
    ctx: RunContext,
    stage_id: str,
    exc: BaseException,
) -> RecoveryResult:
    """Run at most one playbook for this signature, then recovered or escalate."""
    try:
        from interview_mux.homunculus.issues import ingest_catch
        from interview_mux.homunculus.runtime import (
            conductor_owns_control_flow,
            recovery_allowed,
        )

        ingest_catch(
            ctx,
            kind="stage_failure",
            source="recovery_controller",
            stage_id=stage_id,
            implicated=[stage_id],
            evidence={"error_class": type(exc).__name__, "message": str(exc)[:400]},
        )
        early_class = classify_error_class(stage_id, exc)
        # Control flow: escalate to analysis only while a conductor exists to run it.
        if conductor_owns_control_flow(ctx) and not recovery_allowed(
            ctx, stage_id, exc=exc, error_class=early_class
        ):
            return _result(
                status="escalate",
                playbook_id="awaiting_homunculus_analysis",
                signature=signature_key(stage_id, early_class or "unknown"),
                resume_stage=stage_id,
                detail="homunculus_analysis_required",
            )
    except Exception:
        pass
    error_class = classify_error_class(stage_id, exc)
    if not error_class:
        return _result(
            status="escalate",
            playbook_id="none",
            signature=signature_key(stage_id, "unknown"),
            resume_stage=stage_id,
            detail="no_matching_playbook",
        )
    from interview_mux.identical_failures import (
        failure_signature,
        failure_signature_by_class,
        is_halted,
        record_class_failure,
        record_identical_failure,
    )

    if has_classified_playbook(error_class):
        halt_sig = failure_signature_by_class(
            failed_stage=stage_id,
            error_class=error_class,
        )
    else:
        halt_sig = failure_signature(
            failed_stage=stage_id,
            producer=error_class,
            reason=str(exc)[:400],
        )
    if is_halted(ctx, halt_sig):
        resume = stage_id
        try:
            from interview_mux.heal_routing import PLAYBOOK_REGISTRY

            spec = PLAYBOOK_REGISTRY.get(error_class)
            if spec and spec.resume_stage:
                resume = spec.resume_stage
            if error_class == "high_gap_unframed":
                from interview_mux.stage_completion import high_gap_heal_resume_stage

                resume = high_gap_heal_resume_stage(ctx)
            if error_class in {
                "vo_audibility_drift",
                "opening_orientation_inaudible",
                "never_touch_zeroed_keep",
            }:
                from interview_mux.stage_completion import edl_heal_resume_stage

                resume = edl_heal_resume_stage(ctx)
        except Exception:
            pass
        return _result(
            status="escalate",
            playbook_id="identical_failure_halt",
            signature=signature_key(stage_id, error_class),
            resume_stage=resume,
            detail="identical_failures_halted",
        )
    sig = signature_key(stage_id, error_class)
    vo_hash = ""
    if error_class == "framing_vo_unseated":
        vo_hash = vo_seats_fingerprint(ctx)
        hits = _signature_hash_hits(ctx, sig, vo_hash)
        if hits + 1 >= FRAMING_VO_MAX_OBSERVATIONS:
            result = _result(
                status="escalate",
                playbook_id="identical_vo_seats_x3",
                signature=sig,
                resume_stage=stage_id,
                detail="unchanged_vo_seats_hash",
            )
            _append_action(
                ctx,
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "signature": sig,
                    "playbook_id": result.playbook_id,
                    "status": result.status,
                    "detail": result.detail,
                    "vo_seats_hash": vo_hash,
                },
            )
            return result
    elif budget_exhausted(ctx, sig, error_class):
        if error_class == "sdp_theme_wavs_missing":
            resume_on_budget = "mmaudio_sfx"
        elif error_class == "incomplete_cut_unresolved":
            resume_on_budget = "junction_snip_qa"
            _unmark_stages(ctx, "junction_snip_qa", "mix", force=True)
        elif error_class in {
            "opening_orientation_inaudible",
            "vo_audibility_drift",
            "never_touch_zeroed_keep",
        }:
            # R6: budget exhaust must still pin the named producer (not silent
            # consumer re-exec of edl/mix after a no-op first heal).
            try:
                from interview_mux.stage_completion import edl_heal_resume_stage

                resume_on_budget = edl_heal_resume_stage(ctx)
            except Exception:
                resume_on_budget = stage_id
        elif error_class == "selection_edl_order_drift":
            resume_on_budget = "edl"
            try:
                from interview_mux.heal_routing import mix_assembly_seated

                if stage_id in {"mix", "junction_snip_qa", "master_finalize"}:
                    resume_on_budget = (
                        "junction_snip_qa" if mix_assembly_seated(ctx) else "edl"
                    )
            except Exception:
                pass
        elif error_class in {"listen_delight_floors", "pmq_incomplete_ship_walk"}:
            # Remutate cap spent: ship-best then escalate (honest refuse / no thrash).
            resume_on_budget = stage_id
            try:
                from interview_mux.aspirational_quality import (
                    apply_best_quality_candidate,
                    is_aspirational_enabled,
                )
                from interview_mux.listen_delight_remutate import REMUTATE_REL

                pick: dict[str, Any] = {"ok": False, "reason": "aspirational_off"}
                if is_aspirational_enabled(ctx):
                    pick = apply_best_quality_candidate(ctx, family="listen_delight")
                prior = (
                    ctx.read_json(REMUTATE_REL)
                    if ctx.artifact_exists(REMUTATE_REL)
                    else {}
                )
                doc = dict(prior) if isinstance(prior, dict) else {}
                doc["exhausted"] = True
                doc["terminate"] = "recovery_budget_exhausted"
                doc["pick_best"] = pick
                doc["status"] = "exhausted_terminated"
                ctx.write_json(REMUTATE_REL, doc)
            except Exception:
                pass
        else:
            resume_on_budget = stage_id
        result = _result(
            status="escalate",
            playbook_id="budget_exhausted",
            signature=sig,
            resume_stage=resume_on_budget,
            detail="budget_exhausted",
        )
        _append_action(
            ctx,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "signature": sig,
                "playbook_id": result.playbook_id,
                "status": result.status,
                "detail": result.detail,
            },
        )
        if not has_classified_playbook(error_class):
            record_identical_failure(
                ctx,
                failed_stage=stage_id,
                producer=error_class,
                reason=str(exc)[:400],
                resume_attempted=resume_on_budget,
            )
        _write_recovery_escalation(
            ctx,
            stage_id=stage_id,
            error_class=error_class,
            signature=sig,
            detail=result.detail,
        )
        return result

    playbook_id = error_class
    artifacts: list[str] = []
    recovered = False
    detail = ""
    resume_stage = stage_id
    try:
        if error_class == "empty_snap":
            playbook_id = "cuts_empty_snap_demote"
            from interview_mux.ideal_cuts import MATERIALIZED_REL, run_ideal_cuts_materialize

            # In-stage demote writes materialized without raising; re-run once.
            try:
                run_ideal_cuts_materialize(ctx)
            except Exception:
                pass
            recovered = ctx.artifact_exists(MATERIALIZED_REL)
        elif error_class == "layup_coverage":
            playbook_id = "stamp_valueless_skips"
            artifacts = playbook_stamp_valueless_skips(ctx)
            recovered = True
        elif error_class == "orientation_target_mismatch":
            playbook_id = "orientation_retarget_open"
            artifacts = playbook_orientation_retarget(ctx)
            recovered = True
        elif error_class == "framing_vo_unseated":
            playbook_id = "stamp_air_script_omits"
            artifacts = playbook_stamp_air_script_omits(ctx)
            recovered = True
            resume_stage = "edl"
        elif error_class == "naked_seam":
            playbook_id = "seam_mint_reorder"
            artifacts = playbook_mint_reorder_glue(ctx)
            recovered = bool(artifacts)
        elif error_class == "mmaudio_qa_missing":
            playbook_id = "ensure_mmaudio_qa"
            artifacts = playbook_ensure_mmaudio_qa(ctx)
            recovered = bool(artifacts)
            resume_stage = "mmaudio_sfx"
        elif error_class == "sdp_theme_wavs_missing":
            playbook_id = "generate_sdp_theme_wavs"
            artifacts = playbook_generate_sdp_theme_wavs(ctx)
            recovered = True
            from interview_mux.heal_routing import resume_stage_for_error_class

            resume_stage = resume_stage_for_error_class(
                "mmaudio_incomplete", default="mmaudio_sfx"
            )
        elif error_class == "episode_close_outro":
            playbook_id = "place_episode_close_cue"
            artifacts = playbook_place_episode_close(ctx)
            recovered = bool(artifacts)
            if recovered:
                # Cue seeded in music epoch — generate WAV before mix.
                resume_stage = "mmaudio_sfx"
        elif error_class == "missing_g1_pickup":
            playbook_id = "ensure_g1_pickups"
            artifacts = playbook_ensure_g1(ctx)
            recovered = bool(artifacts)
            resume_stage = "vo_synthesize"
        elif error_class == "layup_stale":
            playbook_id = "adopt_layup_to_selection"
            artifacts = playbook_adopt_layup(ctx)
            recovered = bool(artifacts)
            resume_stage = "edl" if recovered else "nugget_layup_compose"
        elif error_class == "hitch_listen_restage":
            playbook_id = "hitch_listen_restage"
            artifacts = playbook_hitch_listen_restage(ctx)
            recovered = bool(artifacts)
            resume_stage = "chapter_close_hitch"
        elif error_class == "listen_delight_floors":
            playbook_id = "listen_delight_remutate"
            artifacts = playbook_listen_delight_remutate(ctx)
            recovered = bool(artifacts)
            resume_stage = "mix"
            try:
                if ctx.artifact_exists("mastering/listen_delight_remutate.json"):
                    plan = ctx.read_json("mastering/listen_delight_remutate.json")
                    if isinstance(plan, dict) and plan.get("from_stage"):
                        resume_stage = str(plan.get("from_stage") or "mix")
            except Exception:
                pass
        elif error_class == "fingerprint_mismatch":
            playbook_id = "fingerprint_restamp_or_rerun"
            producer = resolve_fingerprint_heal_resume(
                message=str(exc),
                gate_stage=stage_id,
                body_from="",
                mode="delivery",
                ctx=ctx,
            ) or FINGERPRINT_PRODUCER_BY_CONSUMER.get(stage_id)
            recovered = bool(producer)
            detail = producer or "no_mapped_producer"
            if producer:
                resume_stage = producer
        elif error_class == "mixed_diarization":
            playbook_id = "speaker_roles_dominant_fallback"
            from interview_mux.speaker_role_evidence import persist_mixed_diarization_fallback

            artifacts = persist_mixed_diarization_fallback(ctx)
            recovered = bool(artifacts)
            if recovered:
                resume_stage = "source_topology_build"
        elif error_class == "never_touch_cta":
            playbook_id = "skip_never_touch_cta_layups"
            artifacts = playbook_skip_never_touch_cta_layups(ctx)
            recovered = True
        elif error_class == "unknown_nle_split_child":
            playbook_id = "materialize_nle_split_children"
            artifacts = playbook_materialize_nle_split_children(ctx)
            recovered = True
            resume_stage = "edl"
        elif error_class == "overlapping_source_range":
            playbook_id = "merge_overlapping_source_ranges"
            artifacts = playbook_merge_overlapping_source_ranges(ctx)
            recovered = bool(artifacts)
            resume_stage = "edl"
        elif error_class == "selection_cta_omit":
            playbook_id = "host_cta_omit"
            artifacts = playbook_host_cta_omit(ctx)
            recovered = True
            resume_stage = "nugget_layup_compose"
        elif error_class == "selection_edl_order_drift":
            playbook_id = "selection_edl_order_drift"
            artifacts = playbook_selection_edl_order_drift(ctx)
            recovered = bool(artifacts)
            resume_stage = "edl"
            try:
                from interview_mux.heal_routing import mix_assembly_seated

                if stage_id in {"mix", "junction_snip_qa", "master_finalize"}:
                    resume_stage = "junction_snip_qa" if mix_assembly_seated(ctx) else "edl"
            except Exception:
                if stage_id in {"mix", "junction_snip_qa", "master_finalize"}:
                    resume_stage = "edl"
        elif error_class == "assembly_not_rendered_from_current_edl":
            playbook_id = "assembly_not_rendered_from_current_edl"
            artifacts = playbook_assembly_not_rendered(ctx)
            recovered = True
            from interview_mux.delivery_guardrails import resolve_assembly_stale_resume

            resume_stage = resolve_assembly_stale_resume(ctx)
        elif error_class == "seed_order_prereq":
            playbook_id = "seed_order_prereq"
            resume_stage = playbook_seed_order_prereq(ctx, exc) or stage_id
            artifacts = [resume_stage] if resume_stage else []
            recovered = bool(resume_stage)
        elif error_class == "redundant_framing_transitions":
            playbook_id = "redundant_framing_transitions"
            artifacts = playbook_redundant_framing_transitions(ctx)
            recovered = bool(artifacts)
            resume_stage = "transitions"
        elif error_class == "finalize_input_missing":
            playbook_id = "finalize_input_missing"
            resume_stage = playbook_finalize_input_missing(ctx, exc) or stage_id
            artifacts = [resume_stage] if resume_stage else []
            recovered = bool(resume_stage)
        elif error_class == "opening_slot_conflict":
            playbook_id = "opening_slot_conflict"
            artifacts = playbook_opening_slot_conflict(ctx)
            recovered = bool(artifacts)
            resume_stage = "edl"
        elif error_class == "post_master_quality_missing":
            playbook_id = "post_master_quality_missing"
            artifacts = playbook_post_master_quality_missing(ctx)
            recovered = bool(artifacts)
            resume_stage = "master_finalize"
        elif error_class == "high_gap_unframed":
            playbook_id = "high_gap_unframed"
            artifacts = playbook_high_gap_unframed(ctx)
            recovered = bool(artifacts)
            from interview_mux.stage_completion import high_gap_heal_resume_stage

            resume_stage = high_gap_heal_resume_stage(ctx)
        elif error_class == "opening_orientation_inaudible":
            playbook_id = "opening_orientation_inaudible"
            from interview_mux.stage_completion import edl_heal_resume_stage

            resume_stage = edl_heal_resume_stage(ctx)
            # R6: when the named producer is upstream of edl, do not run the
            # rebuild/omit playbook — it can waive orientation and burn the
            # single structural attempt on a consumer no-op.
            if resume_stage != "edl":
                artifacts = []
                recovered = False
            else:
                artifacts = playbook_opening_orientation_inaudible(ctx)
                recovered = bool(artifacts)
        elif error_class == "vo_audibility_drift":
            playbook_id = "vo_audibility_drift"
            from interview_mux.stage_completion import edl_heal_resume_stage

            resume_stage = edl_heal_resume_stage(ctx)
            if resume_stage != "edl":
                artifacts = []
                recovered = False
            else:
                artifacts = playbook_vo_audibility_drift(ctx)
                recovered = bool(artifacts)
        elif error_class == "never_touch_zeroed_keep":
            playbook_id = "never_touch_zeroed_keep"
            from interview_mux.stage_completion import edl_heal_resume_stage

            resume_stage = edl_heal_resume_stage(ctx)
            if resume_stage != "edl":
                artifacts = []
                recovered = False
            else:
                artifacts = playbook_never_touch_zeroed_keep(ctx)
                recovered = bool(artifacts)
        elif error_class == "pending_write_barrier":
            playbook_id = "pending_write_barrier"
            artifacts = playbook_pending_write_barrier(ctx)
            recovered = bool(artifacts)
            resume_stage = "junction_snip_qa"
        elif error_class == "musicgen_theme_failed":
            playbook_id = "musicgen_theme_failed"
            artifacts = playbook_musicgen_theme_failed(ctx)
            recovered = True
            resume_stage = "music_palette_compose"
        elif error_class == "incomplete_cut_unresolved":
            playbook_id = "incomplete_cut_unresolved"
            artifacts = playbook_incomplete_cut_unresolved(ctx)
            recovered = True
            resume_stage = "junction_snip_qa"
        elif error_class == "vo_seated_coverage":
            playbook_id = "vo_seated_coverage"
            from interview_mux.execution_contract import run_edl_vo_coverage_ladder
            from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

            ladder = run_edl_vo_coverage_ladder(ctx, consumer_stage=stage_id)
            artifacts = list(ladder.artifacts)
            recovered = ladder.recovered
            # Absolute pin: VO coverage class always resumes vo_synthesize unless
            # coverage is already satisfied (already_ok → stay on consumer).
            still_missing = compact_vo_coverage_stale_or_missing(ctx)
            if ladder.detail == "already_ok" and not still_missing:
                resume_stage = stage_id
            else:
                resume_stage = "vo_synthesize"
                try:
                    from interview_mux.delivery_guardrails import may_rewind_to_vo_synthesize

                    if may_rewind_to_vo_synthesize(ctx) or still_missing:
                        _unmark_stages(ctx, "vo_synthesize", force=True)
                except Exception:
                    _unmark_stages(ctx, "vo_synthesize", force=True)
                if still_missing and not recovered:
                    # Pin producer even when ladder escalates so we don't identical-fail
                    # on the consumer (edl_narrative / mix).
                    recovered = True
                    detail = ladder.detail or "pin_vo_synthesize"
        elif error_class == "vo_contract_repair":
            playbook_id = "vo_contract_repair"
            artifacts = playbook_vo_contract_repair(ctx)
            from interview_mux.vo_contract import validate_vo_contract

            recovered = not validate_vo_contract(ctx)
            resume_stage = "vo_line_adjudicate" if recovered else stage_id
        elif error_class == "upstream_stale_rerun":
            playbook_id = "upstream_stale_rerun"
            artifacts = playbook_upstream_stale_rerun(ctx, consumer_stage=stage_id)
            recovered = bool(artifacts)
            resume_stage = stage_id
            if artifacts:
                try:
                    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

                    order = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
                    ranked = [a for a in artifacts if a in order]
                    resume_stage = (
                        min(ranked, key=lambda s: order.index(s))
                        if ranked
                        else artifacts[0]
                    )
                except Exception:
                    resume_stage = artifacts[0]
        elif error_class == "air_script_omit_sync":
            playbook_id = "air_script_omit_sync"
            artifacts = playbook_air_script_omit_sync(ctx)
            recovered = bool(artifacts)
            resume_stage = "vo_line_adjudicate"
        elif error_class == "pmq_incomplete_ship_walk":
            playbook_id = "listen_delight_remutate"
            artifacts = playbook_listen_delight_remutate(ctx)
            recovered = bool(artifacts)
            resume_stage = "air_script_seams"
            try:
                if ctx.artifact_exists("mastering/listen_delight_remutate.json"):
                    plan = ctx.read_json("mastering/listen_delight_remutate.json")
                    if isinstance(plan, dict) and plan.get("from_stage"):
                        resume_stage = str(plan.get("from_stage") or "air_script_seams")
            except Exception:
                pass
            # B5: refuse air_script_seams pin under hard freeze + assembly.
            try:
                from interview_mux.seat_authority import may_rewind_to_air_script_seams

                if resume_stage == "air_script_seams" and not may_rewind_to_air_script_seams(ctx):
                    resume_stage = "transitions"
            except Exception:
                pass
        else:
            recovered = False
            detail = "unhandled_class"
    except Exception as play_exc:
        recovered = False
        detail = str(play_exc)[:240]

    result = _result(
        status="recovered" if recovered else "escalate",
        playbook_id=playbook_id,
        signature=sig,
        resume_stage=resume_stage,
        artifacts=artifacts,
        detail=detail,
    )
    _append_action(
        ctx,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signature": sig,
            "playbook_id": result.playbook_id,
            "status": result.status,
            "artifacts": result.artifacts_written,
            "detail": result.detail,
            **({"vo_seats_hash": vo_hash} if vo_hash else {}),
        },
    )
    if result.status != "recovered":
        if has_classified_playbook(error_class):
            from interview_mux.identical_failures import failure_signature_by_class, is_halted

            halt_sig = failure_signature_by_class(
                failed_stage=stage_id,
                error_class=error_class,
            )
            halted = is_halted(ctx, halt_sig)
        else:
            row = record_identical_failure(
                ctx,
                failed_stage=stage_id,
                producer=error_class,
                reason=str(exc)[:400],
                resume_attempted=result.resume_stage,
            )
            halted = bool(row.get("halt"))
        if halted:
            result.status = "escalate"
            result.playbook_id = "identical_failure_halt"
            result.detail = (result.detail + " identical_failures_halted").strip()
    elif recovered and playbook_id in _OMIT_PLAYBOOKS:
        append_remediation_log(ctx, action=playbook_id, detail=error_class or detail)
    return result
