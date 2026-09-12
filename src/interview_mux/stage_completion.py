"""Whether pipeline stages are truly complete on disk (UI + runner parity)."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_completeness import artifact_status_for_stage
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.run_context import RunContext
from interview_mux.v2.config import DELIVERY_ORDER

# Non-primary outputs that must exist before a stage is marked done.
STAGE_SECONDARY_ARTIFACT_PATHS: dict[str, list[str]] = {
    "optimal_questions": ["understanding/interviewer_script.txt"],
    "junction_snip_qa": ["master/seam_autopsy.json"],
}


class StageArtifactsIncompleteError(ValueError):
    """Raised when a stage must not be marked done or advanced past."""

    def __init__(self, stage_id: str, reason: str) -> None:
        self.stage_id = stage_id
        self.reason = reason
        super().__init__(f"Stage {stage_id} artifacts incomplete — {reason}")


def stage_required_artifact_paths(stage_id: str) -> list[str]:
    """Producer artifact path(s) that must be complete before a stage is truly done."""
    paths: list[str] = []
    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_id)
    if rel:
        paths.append(rel)
    paths.extend(STAGE_SECONDARY_ARTIFACT_PATHS.get(stage_id, []))
    return paths


def _gap_report_skip_stub_while_framing(ctx: RunContext) -> str | None:
    """Skip-producer gap_report is not complete once G-Framing is Yes."""
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return None
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled

        if not gap_framing_enabled(ctx):
            return None
        doc = ctx.read_json("understanding/gap_report.json")
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    producer = str((doc.get("_meta") or {}).get("producer") or "")
    if producer == "gap_fill_skip":
        return (
            "understanding/gap_report.json is a skip stub while framing is enabled"
        )
    return None


def _research_is_thin(ctx: RunContext) -> bool:
    """True when research dossier is mostly skipped_or_thin / incomplete (telemetry).

    Do **not** use this as the Shape refuse predicate — see research_shape_core_thin.
    """
    try:
        from interview_mux.mastering_research import load_dossier

        dossier = load_dossier(ctx)
    except Exception:
        dossier = None
    if not isinstance(dossier, dict):
        if not ctx.artifact_exists("mastering/research/rollup.json"):
            return False  # early — no dossier yet (advisory path)
        return True
    thin = list(dossier.get("thin_fields") or [])
    complete = list(dossier.get("complete_fields") or [])
    total = len(thin) + len(complete)
    if total == 0:
        fields = dossier.get("fields") if isinstance(dossier.get("fields"), dict) else {}
        if not fields:
            return True
        thin_n = sum(
            1
            for v in fields.values()
            if isinstance(v, dict) and str(v.get("status") or "") != "complete"
        )
        return thin_n >= max(1, len(fields) // 2)
    return len(thin) >= max(1, (total + 1) // 2)


RESEARCH_CONSUMER_STAGES: frozenset[str] = frozenset(
    {
        "mastering_shape_agenda",
        "mastering_shape_candidates",
        "mastering_plan_synthesize",
        "mastering_plan_confirm",
        "missing_framing",
        "gap_framing_compose",
    }
)


def _shape_about_to_bind(ctx: RunContext) -> bool:
    """True when Shape/gap bind artifacts or stage_done markers already exist (rollup late)."""
    if ctx.artifact_exists("mastering/shape/agenda.json"):
        return True
    if ctx.artifact_exists("mastering/shape/candidates.json"):
        return True
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        return True
    for sid in (
        "mastering_shape_agenda",
        "mastering_shape_candidates",
        "mastering_plan_synthesize",
        "mastering_plan_confirm",
    ):
        if ctx.is_done(sid):
            return True
    return False


def _research_thin_late_refuse(ctx: RunContext, stage_id: str) -> str | None:
    """A-01: Shape/gap consumers always late for shape-core thin (flags OFF OK).

    Rollup stays advisory until Shape about-to-bind. Do not refuse on global
    majority thin (W4–W8 expected thin at Pass1).
    """
    try:
        from interview_mux.mastering_research import research_shape_core_thin
    except Exception:
        return None
    if stage_id == "mastering_research_rollup":
        if _shape_about_to_bind(ctx) and research_shape_core_thin(ctx):
            return "research dossier shape-core thin (late refuse — Shape about to bind)"
        return None
    if stage_id not in RESEARCH_CONSUMER_STAGES:
        return None
    if research_shape_core_thin(ctx):
        return "research shape-core thin — not ready for Shape/gap consumers"
    return None


def stage_artifact_incompleteness(
    ctx: RunContext,
    stage_id: str,
    *,
    lifecycle: dict[str, Any] | None = None,
) -> str | None:
    """Human-readable reason when required artifacts are not complete, else None."""
    if stage_id == "mmaudio_sfx":
        # Empty/phantom QA rows read as partial even when theme WAVs exist.
        try:
            from interview_mux.mmaudio_asset_qa import heal_mmaudio_qa_wav_parity

            heal_mmaudio_qa_wav_parity(ctx)
        except Exception:
            pass
    if stage_id == "mix":
        try:
            from interview_mux.air_order import mix_wav_fresh_versus_edl

            if ctx.artifact_exists("master/assembly.wav") and not mix_wav_fresh_versus_edl(
                ctx
            ):
                return "master/assembly.wav is stale versus live EDL"
        except Exception:
            pass
    for path in stage_required_artifact_paths(stage_id):
        phase = (lifecycle or {}).get(path)
        if phase in ("n_a", "skipped"):
            continue
        if not ctx.artifact_exists(path):
            return f"{path} is pending"
        # F-04: prefer hollow-seats signal over generic "partial" for air stages.
        if stage_id in {"air_script_seams", "air_script_compose"} and path.endswith(
            "mastering_plan.json"
        ):
            hollow = _air_script_hollow_seats_incompleteness(ctx)
            if hollow:
                return hollow
        # Exists ≠ usable (stale, fingerprint, pending-only seating).
        try:
            from interview_mux.thrash_hardening import artifact_usable

            ok, usable_reason = artifact_usable(ctx, path, consumer=stage_id)
            if not ok:
                return f"{path} unusable ({usable_reason})"
        except Exception:
            pass
        # Stale stamps mean the producer must re-run / restamp — do not treat as
        # complete for seed-front (else conductor skips to the next consumer).
        try:
            raw = ctx.read_json(path)
            meta = (raw.get("_meta") or {}) if isinstance(raw, dict) else {}
            if meta.get("stale"):
                reason = str(meta.get("stale_reason") or "upstream fix")
                return f"{path} is marked stale ({reason})"
        except Exception:
            pass
        st = artifact_status_for_stage(path, ctx, stage_id)
        if st != "complete":
            return f"{path} is {st}"
    if stage_id == "vo_synthesize":
        try:
            from interview_mux.thrash_hardening import vo_done_with_deferred_pairs_ok

            ok, why = vo_done_with_deferred_pairs_ok(ctx)
            if not ok:
                return why
        except Exception:
            pass
    if stage_id in {"missing_framing", "gap_framing_compose", "optimal_questions"}:
        stub = _gap_report_skip_stub_while_framing(ctx)
        if stub:
            return stub
    # A-01: research thin — early advisory; late/expected consumers refuse seed_complete.
    thin_reason = _research_thin_late_refuse(ctx, stage_id)
    if thin_reason:
        return thin_reason
    try:
        from interview_mux.gap_fill_eligibility import synthetic_vo_incompleteness

        vo_reason = synthetic_vo_incompleteness(ctx, stage_id)
    except Exception:
        vo_reason = None
    if vo_reason:
        return vo_reason
    if stage_id == "nugget_layup_compose":
        try:
            from interview_mux.artifact_sanitize.registry import selection_sanitary_errors

            sel_errs = selection_sanitary_errors(ctx)
        except Exception:
            sel_errs = []
        if sel_errs:
            return (
                "selection_unsanitary — resume selection_order_sanitize: "
                + "; ".join(sel_errs[:3])
            )
        try:
            from interview_mux.nugget_layup import layup_freshness_errors

            fresh_errs = layup_freshness_errors(ctx)
        except Exception:
            fresh_errs = []
        if fresh_errs:
            return fresh_errs[0]
        try:
            from interview_mux.artifact_sanitize.registry import layup_sanitary_errors

            lay_errs = layup_sanitary_errors(ctx)
        except Exception:
            lay_errs = []
        if lay_errs:
            return "layup_unsanitary — resume nugget_layup_compose: " + "; ".join(
                lay_errs[:3]
            )
    if stage_id == "gap_report_sanitize":
        try:
            from interview_mux.artifact_sanitize.registry import gap_sanitary_errors

            gap_errs = gap_sanitary_errors(ctx)
        except Exception:
            gap_errs = []
        if gap_errs:
            return "gap still unsanitary: " + "; ".join(gap_errs[:3])
    if stage_id == "air_contract_sanitize":
        try:
            from interview_mux.artifact_sanitize.registry import air_contract_sanitary_errors

            air_errs = air_contract_sanitary_errors(ctx)
        except Exception:
            air_errs = []
        if air_errs:
            return "air_contract still unsanitary: " + "; ".join(air_errs[:3])
    if stage_id == "selection_order_sanitize":
        if not ctx.artifact_exists("master/selection.json"):
            return "master/selection.json is pending"
        try:
            from interview_mux.artifact_sanitize.registry import selection_sanitary_errors

            sel_errs = selection_sanitary_errors(ctx)
        except Exception:
            sel_errs = []
        if sel_errs:
            return "selection still unsanitary: " + "; ".join(sel_errs[:3])
    if stage_id == "sound_design_plan":
        try:
            from interview_mux.artifact_sanitize.registry import (
                selection_sanitary_errors,
                sdp_sanitary_errors,
                layup_sanitary_errors,
            )

            sel_errs = selection_sanitary_errors(ctx)
            if sel_errs:
                return (
                    "selection_unsanitary — resume selection_order_sanitize: "
                    + "; ".join(sel_errs[:3])
                )
            lay_errs = layup_sanitary_errors(ctx)
            if lay_errs:
                return (
                    "layup_unsanitary — resume nugget_layup_compose: "
                    + "; ".join(lay_errs[:3])
                )
            sdp_errs = sdp_sanitary_errors(ctx)
            if sdp_errs and any("missing" not in e for e in sdp_errs):
                # missing is ok before first write; stale/unsanitary is not
                stale = [e for e in sdp_errs if "stale" in e or "needs_sanitize" in e]
                if stale:
                    return "sdp_unsanitary — resume sound_design_plan: " + "; ".join(
                        stale[:3]
                    )
        except Exception:
            pass
        if not ctx.artifact_exists("master/transitions.json"):
            return "master/transitions.json is pending"
        try:
            from interview_mux.homunculus.agenda import delivery_sdp_present

            if not delivery_sdp_present(ctx):
                return "sound_design_plan has not written the delivery SDP"
            # F-03: unpaid invent obligation + empty palettes/cues → incomplete
            try:
                from interview_mux.soundscape_policy import invent_obligation_status

                status = invent_obligation_status(ctx)
                if status.get("unpaid"):
                    return "sound_design_plan invent obligation unpaid (empty palettes+cues)"
            except Exception:
                pass
        except Exception:
            return "sound_design_plan delivery SDP not confirmed"
    if stage_id == "vo_synthesize":
        try:
            from interview_mux.artifact_sanitize.registry import (
                gap_sanitary_errors,
                air_contract_sanitary_errors,
            )

            for label, fn in (
                ("gap", gap_sanitary_errors),
                ("air_contract", air_contract_sanitary_errors),
            ):
                try:
                    errs = fn(ctx)
                except Exception:
                    errs = []
                if errs:
                    resume = (
                        "gap_report_sanitize"
                        if label == "gap"
                        else "air_contract_sanitize"
                    )
                    return f"{label}_unsanitary — resume {resume}: " + "; ".join(
                        errs[:3]
                    )
        except Exception:
            pass
        if not ctx.artifact_exists("master/transitions.json"):
            return "master/transitions.json is pending"
        try:
            from interview_mux.transition_vo import vo_synthesize_pair_incompleteness

            pair_reason = vo_synthesize_pair_incompleteness(ctx)
        except Exception:
            pair_reason = None
        if pair_reason:
            return pair_reason
        try:
            from interview_mux.gates import check_g1_vo

            missing_g1 = check_g1_vo(ctx)
            if missing_g1:
                return f"G1 VO pickups missing: {', '.join(missing_g1[:4])}"
        except Exception:
            pass
        try:
            from interview_mux.vo_contract import seated_vo_missing_ids

            missing_seated = seated_vo_missing_ids(ctx)
            if missing_seated:
                return (
                    "seated synthesize VO missing WAV: "
                    + ", ".join(missing_seated[:4])
                )
        except Exception:
            pass
        try:
            from interview_mux.artifact_sanitize.registry import vo_sanitary_errors

            vo_errs = vo_sanitary_errors(ctx)
            if vo_errs:
                return "vo_unsanitary — resume vo_synthesize: " + "; ".join(vo_errs[:3])
        except Exception:
            pass
        try:
            from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

            stale = compact_vo_coverage_stale_or_missing(ctx)
            if stale:
                return (
                    "seated synthesize VO script/WAV stale: "
                    + ", ".join(stale[:4])
                )
        except Exception:
            pass
    if stage_id in {
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
    }:
        if not ctx.artifact_exists("master/assembly.wav") and not ctx.artifact_exists(
            "master/assembly_preview.wav"
        ):
            return "assembly audio missing — theme/SFX wait for assembly_preview"
    if stage_id == "mmaudio_sfx":
        try:
            from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

            missing_wavs = missing_sdp_asset_wavs(ctx)
        except Exception:
            missing_wavs = []
        if missing_wavs:
            return (
                "SDP theme WAVs missing: "
                + ", ".join(str(a) for a in missing_wavs[:4])
            )
    if stage_id == "edl":
        try:
            from interview_mux.artifact_sanitize.registry import vo_sanitary_errors

            vo_errs = vo_sanitary_errors(ctx)
            if vo_errs:
                return "vo_unsanitary — resume vo_synthesize: " + "; ".join(vo_errs[:3])
        except Exception:
            pass
        try:
            from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

            stale = compact_vo_coverage_stale_or_missing(ctx)
            if stale:
                return (
                    "seated synthesize VO script/WAV stale: "
                    + ", ".join(stale[:4])
                )
        except Exception:
            pass
        try:
            from interview_mux.transition_vo import seated_vo_paths_missing

            missing = seated_vo_paths_missing(ctx)
        except Exception:
            missing = []
        if missing:
            return f"seated VO missing: {', '.join(missing[:4])}"
    return None


def _air_script_hollow_seats_incompleteness(ctx: RunContext) -> str | None:
    """When air is on and live gap VO needs seats, empty seated_line_ids is hollow."""
    try:
        from interview_mux.air_script import air_script_enabled, gap_line_air_eligible
        from interview_mux.mastering_plan_loader import load_plan_raw
    except Exception:
        return None
    if not air_script_enabled():
        return None
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return None
    try:
        gap = ctx.read_json("understanding/gap_report.json")
    except Exception:
        return None
    if not isinstance(gap, dict):
        return None
    live_ids = [
        str(row.get("line_id") or "").strip()
        for row in (gap.get("interviewer_lines") or [])
        if isinstance(row, dict) and gap_line_air_eligible(row) and row.get("line_id")
    ]
    if not live_ids:
        return None
    plan = None
    try:
        plan = load_plan_raw(ctx)
    except Exception:
        plan = None
    if not isinstance(plan, dict):
        return "air_script hollow seats — live VO lines need seats but plan missing"
    script = plan.get("air_script") if isinstance(plan.get("air_script"), dict) else {}
    seats = script.get("vo_seats") if isinstance(script.get("vo_seats"), dict) else {}
    seated = [str(x) for x in (seats.get("seated_line_ids") or []) if x]
    if seated:
        return None
    return (
        "air_script hollow seats — live VO lines need seats but seated_line_ids empty"
    )


def vo_synthesize_should_defer_done(ctx: RunContext, stage_id: str) -> str | None:
    """If set, do not mark vo_synthesize done and do not abort the delivery batch.

    Mix last-chance is the remaining net. GUI/reconcile still see incompleteness.
    """
    if stage_id != "vo_synthesize":
        return None
    return stage_artifact_incompleteness(ctx, stage_id)


def reconcile_stage_done_marker(ctx: RunContext, stage_id: str) -> bool:
    """
    Clear .stage_done when artifacts are not acceptable.
    Returns True when the stage remains marked done after reconcile.
    """
    if not ctx.is_done(stage_id):
        return False
    reason = stage_artifact_incompleteness(ctx, stage_id)
    if not reason:
        return True
    marker = ctx.final_path(".stage_done", stage_id)
    if marker.is_file():
        marker.unlink(missing_ok=True)
        ctx.log(
            f"Cleared stale .stage_done/{stage_id}: {reason}",
            level="warning",
            stage=stage_id,
            detail={"reason": reason},
        )
    return False


# Error-token → earliest producer (durable Wave 1+). heal_navigate / identical×3
# consult this table only — no ad-hoc stage guesses past an incomplete producer.
PRODUCER_PIN_TABLE: dict[str, str] = {
    "missing_wav": "vo_synthesize",
    "edl_script_hash_stale": "edl",
    "music_incomplete": "mmaudio_sfx",
    "mmaudio_incomplete": "mmaudio_sfx",
    "sdp_theme_wavs_missing": "mmaudio_sfx",
    "seam_autopsy": "junction_snip_qa",
    "g1_vo_open": "vo_synthesize",  # synth path; record path via resolve_g1_vo_open_resume
    "g1_vo_incomplete": "vo_synthesize",
    "incomplete_cut_unresolved": "junction_snip_qa",
    "voice_reference_pending": "topic_coverage_audit",
    "seed_order": "edl",
    "assembly_seating_stale": "mix",
    "air_script_incomplete": "air_script_compose",
    "air_script_seams": "air_script_seams",
    "edl_narrative_fail": "edl_narrative_audit",
    "pmq_structural": "master_finalize",
    "hollow_done": "edl",
    "skip_then_consume": "edl",
    "chapter_close_hitch": "chapter_close_hitch",
    "nugget_corpus_mine": "nugget_corpus_mine",
    "information_package_plan": "information_package_plan",
    "ingest_missing": "ingest",
    "g0_pending": "transcript_review_build",
    "preclean_pending": "audio_preclean",
    "cover_missing": "episode_cover_generate",
    "encode_missing": "podcast_encode_mp3",
    "publish_advisories": "podcast_publish",
    # Sanitize / incompleteness tokens (Lock 5 / O3)
    "selection_unsanitary": "selection_order_sanitize",
    "gap_unsanitary": "gap_report_sanitize",
    "air_contract_unsanitary": "air_contract_sanitize",
    "layup_unsanitary": "nugget_layup_compose",
    "fragment_depth": "selection_order_sanitize",
    "sdp_unsanitary": "sound_design_plan",
    "vo_unsanitary": "vo_synthesize",
}
# Every delivery stage pins itself for "artifact missing" tokens.
for _sid in DELIVERY_ORDER:
    PRODUCER_PIN_TABLE.setdefault(str(_sid), str(_sid))
    PRODUCER_PIN_TABLE.setdefault(f"{_sid}_missing", str(_sid))
    PRODUCER_PIN_TABLE.setdefault(f"artifact_missing:{_sid}", str(_sid))


def incompleteness_resume_stage(reason: str, *, stage_id: str = "") -> str:
    """Map incompleteness prose / tokens to heal-registry resume stage."""
    text = str(reason or "").lower()
    sid = str(stage_id or "").strip()
    try:
        from interview_mux.heal_routing import resume_stage_for_error_class

        if "g1" in text or "pickup" in text:
            return resume_stage_for_error_class("g1_vo_incomplete", default="vo_synthesize")
        if "sdp" in text or "theme wav" in text or "mmaudio" in text:
            return resume_stage_for_error_class("mmaudio_incomplete", default="mmaudio_sfx")
        if "on_a_roll" in text or "incomplete_cut" in text:
            return resume_stage_for_error_class(
                "incomplete_cut_unresolved", default="junction_snip_qa"
            )
    except Exception:
        pass
    for token, pin in PRODUCER_PIN_TABLE.items():
        if token and token in text:
            return str(pin)
    return sid or "edl"


def _resume_stage_allowlist() -> set[str]:
    from interview_mux.v2.config import ANALYSIS_ORDER

    ids = {str(s) for s in DELIVERY_ORDER} | {str(s) for s in ANALYSIS_ORDER}
    ids.update(
        {
            "selection_order_sanitize",
            "gap_report_sanitize",
            "air_contract_sanitize",
        }
    )
    return ids


def parse_resume_stage_from_reason(reason: str) -> str | None:
    """Allowlisted fallback parse of ``— resume <stage>:`` in incompleteness prose."""
    import re

    text = str(reason or "")
    m = re.search(r"—\s*resume\s+([a-z0-9_]+)\s*:", text, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"-\s*resume\s+([a-z0-9_]+)\s*:", text, flags=re.IGNORECASE)
    if not m:
        return None
    sid = str(m.group(1) or "").strip()
    if sid in _resume_stage_allowlist():
        return sid
    return None


def incompleteness_resume_stage(ctx: RunContext, consumer_stage: str) -> str | None:
    """Structured resume for a consumer's incompleteness (same branch, not regex)."""
    sid = str(consumer_stage or "").strip()
    if not sid:
        return None
    # Mirror the sanitary/resume branches in stage_artifact_incompleteness.
    if sid == "nugget_layup_compose":
        try:
            from interview_mux.artifact_sanitize.registry import selection_sanitary_errors

            if selection_sanitary_errors(ctx):
                return "selection_order_sanitize"
        except Exception:
            pass
        try:
            from interview_mux.artifact_sanitize.registry import layup_sanitary_errors

            if layup_sanitary_errors(ctx):
                return "nugget_layup_compose"
        except Exception:
            pass
    if sid == "sound_design_plan":
        try:
            from interview_mux.artifact_sanitize.registry import (
                selection_sanitary_errors,
                layup_sanitary_errors,
                sdp_sanitary_errors,
            )

            if selection_sanitary_errors(ctx):
                return "selection_order_sanitize"
            if layup_sanitary_errors(ctx):
                return "nugget_layup_compose"
            sdp_errs = sdp_sanitary_errors(ctx)
            if sdp_errs and any("stale" in e or "needs_sanitize" in e for e in sdp_errs):
                return "sound_design_plan"
        except Exception:
            pass
    reason = stage_artifact_incompleteness(ctx, sid)
    if reason:
        parsed = parse_resume_stage_from_reason(reason)
        if parsed:
            return parsed
        reason_l = str(reason).lower()
        # invalidated_by:<producer> must not yank resume back to a completed
        # producer (exec_10066: vo_synthesize.json stale → layup thrash while
        # G1 still needs WAVs). Clear stale and regenerate the consumer.
        if "invalidated_by:" in reason_l or "stale_meta:invalidated_by:" in reason_l:
            inv = ""
            for marker in ("stale_meta:invalidated_by:", "invalidated_by:"):
                if marker in reason_l:
                    inv = reason_l.split(marker, 1)[1].split()[0].strip("):,]\"'")
                    break
            if inv and inv in _resume_stage_allowlist():
                # Producer already marked done → regenerate consumer; do not
                # re-enter a completed invalidator (G1/VO thrash).
                if ctx.is_done(inv):
                    try:
                        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

                        rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
                        if rel and ctx.artifact_exists(rel):
                            doc = ctx.read_json(rel)
                            if isinstance(doc, dict):
                                meta = dict(doc.get("_meta") or {})
                                if meta.get("stale"):
                                    meta.pop("stale", None)
                                    meta.pop("stale_reason", None)
                                    doc["_meta"] = meta
                                    ctx.write_json(rel, doc, skip_handoff=True)
                    except Exception:
                        pass
                    return sid
        for tok, pin in PRODUCER_PIN_TABLE.items():
            if tok and tok in reason_l and pin in _resume_stage_allowlist():
                return pin
    return None


def producer_pin_for_token(token: str, *, default: str = "edl") -> str:
    key = str(token or "").strip().lower()
    if key in PRODUCER_PIN_TABLE:
        return PRODUCER_PIN_TABLE[key]
    for needle, pin in PRODUCER_PIN_TABLE.items():
        if needle and needle in key:
            return pin
    return default


def heal_or_refuse_mark(ctx: RunContext, stage: str, *, force: bool = False) -> dict[str, Any]:
    """Sole mark/unmark authority for delivery completeness (heal ≠ waive).

    - incompleteness None + usable → mark_done (force only via assert_may_force_done)
    - incompleteness set + done → unmark that stage only
    - incompleteness set + not done → refuse mark
    - intentional allow-stub (G1 optional VO skip with force) → mark despite hollow
    """
    sid = str(stage or "").strip()
    out: dict[str, Any] = {"stage": sid, "marked": False, "unmarked": False, "refused": False}
    if not sid:
        out["refused"] = True
        out["reason"] = "empty_stage"
        return out
    reason = stage_artifact_incompleteness(ctx, sid)
    allow_stub = False
    if reason and force and sid in {"vo_synthesize", "vo_line_adjudicate"}:
        # Documented allow-stub: operator skipped optional G1 VO pickup.
        try:
            from interview_mux.gates import g1_vo_was_skipped_optional

            allow_stub = bool(g1_vo_was_skipped_optional(ctx))
        except Exception:
            allow_stub = False
    if reason is None or allow_stub:
        # Depth 7: refuse mark when primary artifact fails usability (unless allow_stub).
        if reason is None:
            try:
                from interview_mux.thrash_hardening import artifact_usable
                from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

                rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
                if rel and ctx.artifact_exists(rel):
                    ok, ureason = artifact_usable(ctx, rel, consumer=sid)
                    if not ok:
                        out["refused"] = True
                        out["reason"] = f"artifact_unusable:{ureason or rel}"
                        return out
            except Exception:
                pass
        if force and not allow_stub:
            try:
                from interview_mux.thrash_hardening import assert_may_force_done

                assert_may_force_done(ctx, sid)
            except RuntimeError as exc:
                out["refused"] = True
                out["reason"] = str(exc)
                return out
        if not ctx.is_done(sid):
            # Avoid re-entering heal_or_refuse via mark_done force guard.
            prev = getattr(ctx, "_mark_done_raw", False)
            ctx._mark_done_raw = True
            try:
                ctx.mark_done(sid, force=bool(force))
            finally:
                ctx._mark_done_raw = prev
            out["marked"] = True
            if allow_stub:
                out["allow_stub"] = True
                out["reason"] = reason
        return out
    if ctx.is_done(sid):
        reconcile_stage_done_marker(ctx, sid)
        out["unmarked"] = not ctx.is_done(sid)
        out["reason"] = reason
        return out
    out["refused"] = True
    out["reason"] = reason
    return out


def seed_stage_complete(ctx: RunContext, stage: str) -> bool:
    """G1: is_done ∧ outputs present ∧ no artifact incompleteness."""
    from interview_mux.delivery_guardrails import seed_stage_complete as _complete

    return _complete(ctx, stage)


def assert_stage_artifacts_complete(ctx: RunContext, stage_id: str) -> None:
    reason = stage_artifact_incompleteness(ctx, stage_id)
    if reason:
        raise StageArtifactsIncompleteError(stage_id, reason)


def _staged_resilience_partial_acceptable(
    rel: str,
    doc: dict[str, Any],
    stage_id: str,
    ctx: RunContext | None = None,
) -> bool:
    """Allow partial-persist rescue saves when the stage producer content is semantically complete.

    Critical LLM stages never approve resilience-partial staging — Fail closed; re-run instead.
    """
    from interview_mux.artifact_completeness import compute_gaps
    from interview_mux.llm_flow_hardening import ALL_CRITICAL_LLM_STAGES
    from interview_mux.llm_output_resilience import artifact_resilience_partial

    if ctx and _staged_zero_pickup_acceptable(ctx, stage_id, rel, doc):
        return True
    if stage_id in ALL_CRITICAL_LLM_STAGES:
        return False
    if not artifact_resilience_partial(doc):
        return False
    producer = STAGE_ARTIFACT_DISK_PATHS.get(stage_id)
    if not producer or rel != producer:
        return False
    return not compute_gaps(rel, doc, stage_key=stage_id)


def _staged_zero_pickup_acceptable(
    ctx: RunContext,
    stage_id: str,
    rel: str,
    doc: dict[str, Any],
) -> bool:
    """Empty interviewer_lines are valid when gap-fill was skipped or no segment needs pickup."""
    if stage_id != "optimal_questions" or rel != "understanding/gap_report.json":
        return False
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

    if gap_fill_was_skipped(ctx):
        return True
    lines = doc.get("interviewer_lines")
    if not isinstance(lines, list) or lines:
        return False
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return False
    try:
        eval_doc = ctx.read_json("understanding/gap_evaluations.json")
    except Exception:
        return False
    evals = eval_doc.get("evaluations") or []
    if not isinstance(evals, list) or not evals:
        return False
    for row in evals:
        if not isinstance(row, dict):
            continue
        if row.get("self_explanatory"):
            continue
        severity = str(row.get("severity") or "").lower()
        if severity in {"high", "critical"}:
            return False
        gap_type = str(row.get("gap_type") or "")
        if gap_type and gap_type != "ok_with_light_bridge":
            return False
    return True


def staged_artifacts_acceptable(ctx: RunContext, stage_id: str) -> tuple[bool, str]:
    """True when pending staged JSON artifacts are safe to flush and mark done."""
    from interview_mux.artifact_completeness import compute_staged_write_gaps
    from interview_mux.llm_flow_hardening import ALL_CRITICAL_LLM_STAGES
    from interview_mux.llm_output_resilience import artifact_resilience_partial
    from interview_mux.prompt_validation import validate_artifact_write
    from interview_mux.write_staging import list_stage_staging_paths, read_pending_json

    for rel in list_stage_staging_paths(ctx, stage_id):
        if not rel.endswith(".json"):
            continue
        try:
            doc = read_pending_json(ctx, stage_id, rel)
        except Exception as exc:
            return False, f"{rel}: cannot read staged file ({exc})"
        if not isinstance(doc, dict):
            return False, f"{rel}: staged content is not a JSON object"
        if artifact_resilience_partial(doc) and not _staged_resilience_partial_acceptable(
            rel, doc, stage_id, ctx
        ):
            return False, (
                f"{rel} is a partial rescue save — re-run the stage instead of approving."
            )
        te = (doc.get("_meta") or {}).get("truncation_escalation") or {}
        flags = te.get("final_flags") or []
        if flags and stage_id in ALL_CRITICAL_LLM_STAGES:
            return False, (
                f"{rel} has truncation flags ({', '.join(list(flags)[:2])}) — "
                "re-run instead of approving."
            )
        errors = validate_artifact_write(rel, doc)
        if errors:
            return False, f"{rel}: {'; '.join(errors[:3])}"
        if compute_staged_write_gaps(rel, doc, stage_id=stage_id):
            return False, f"{rel} would remain incomplete after save"
    return True, ""
