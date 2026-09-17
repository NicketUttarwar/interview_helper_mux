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
    "episode_cover_generate": ["publish/cover.jpg"],
    "podcast_publish": ["publish/package_ready.json"],
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
        try:
            from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

            if gap_fill_was_skipped(ctx):
                return None
        except Exception:
            pass
        return (
            "understanding/gap_report.json is a skip stub while framing is enabled"
        )
    return None


BATCH_FILL_BY = "missing_framing_batch_coverage"
REPAIR_FILL_BY = "repair_gap_evaluations"
MISSING_FRAMING_FILL_TAGS = frozenset({BATCH_FILL_BY, REPAIR_FILL_BY})
_BATCH_FILL_BY = BATCH_FILL_BY


def _missing_framing_batch_fill_incompleteness(ctx: RunContext) -> str | None:
    """HG-3 2B: default ok_with_light_bridge coverage fills are not LLM-scored — refuse done."""
    rel = "understanding/gap_evaluations.json"
    if not ctx.artifact_exists(rel):
        return None
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    from interview_mux.stages.gaps import _gap_eval_is_unscored_fill

    filled = [
        str(row.get("segment_id") or "")
        for row in (doc.get("evaluations") or [])
        if isinstance(row, dict)
        and _gap_eval_is_unscored_fill(row)
        and str((row.get("_meta") or {}).get("producer") or "") != "gap_fill_skip"
    ]
    filled = [sid for sid in filled if sid]
    if not filled:
        return None
    return (
        "missing_framing batch_fill — resume missing_framing: "
        f"LLM must score {len(filled)} segment(s) (examples {filled[:6]})"
    )


def _edl_narrative_audit_heard_wav_incompleteness(ctx: RunContext) -> str | None:
    """HE-1: 5C audit is incomplete unless vo_synthesize is seed-complete and heard."""
    from interview_mux.delivery_guardrails import seed_stage_complete

    if not seed_stage_complete(ctx, "vo_synthesize"):
        return (
            "heard_wav_flow — resume vo_synthesize: "
            "vo_synthesize is not seed-complete"
        )
    try:
        from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

        stale = compact_vo_coverage_stale_or_missing(ctx)
    except Exception:
        stale = []
    if stale:
        return (
            "VO coverage not rendered — resume vo_synthesize: "
            + ", ".join(stale[:4])
        )
    return None


def assembly_preview_unsourced_glue_ids(edl: dict[str, Any] | None) -> list[str]:
    """Heard VO/transition clips on the EDL with no source_path (skip-then-stamp hole)."""
    ids: list[str] = []
    for i, clip in enumerate((edl or {}).get("clips") or []):
        if not isinstance(clip, dict):
            continue
        ctype = str(clip.get("type") or "")
        if ctype not in {"vo_pickup", "transition"}:
            continue
        if str(clip.get("source_path") or "").strip():
            continue
        text = str(clip.get("text") or "").strip()
        dur = 0
        try:
            dur = int(clip.get("duration_ms") or 0)
        except (TypeError, ValueError):
            dur = 0
        # Empty-text zero-duration is not heard glue (native/empty seat).
        if ctype == "transition" and not text and dur <= 0:
            continue
        label = str(clip.get("line_id") or "").strip()
        if not label and ctype == "transition":
            after = str(clip.get("after_segment_id") or "")
            before = str(clip.get("before_segment_id") or "")
            label = f"{after}->{before}".strip("->")
        ids.append(label or f"{ctype}:{i}")
    return ids


def _assembly_preview_heard_wav_incompleteness(
    ctx: RunContext, edl: dict[str, Any] | None = None
) -> str | None:
    """HE-3: preview is incomplete unless heard VO/glue is sourced and bind is sanitary."""
    doc = edl
    if doc is None and ctx.artifact_exists("master/edl.json"):
        try:
            raw = ctx.read_json("master/edl.json")
            doc = raw if isinstance(raw, dict) else None
        except Exception:
            doc = None
    unsourced = assembly_preview_unsourced_glue_ids(doc if isinstance(doc, dict) else None)
    if unsourced:
        return (
            "heard_wav_flow — resume vo_synthesize: "
            "current transition pairs missing WAV: "
            + ", ".join(unsourced[:4])
        )
    try:
        from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

        stale = compact_vo_coverage_stale_or_missing(ctx)
    except Exception:
        stale = []
    if stale:
        return (
            "heard_wav_flow — resume vo_synthesize: VO coverage not rendered: "
            + ", ".join(stale[:4])
        )
    return None


def assembly_preview_heard_wav_refuse(
    ctx: RunContext, edl: dict[str, Any] | None = None
) -> str | None:
    """Writer-facing HE-3 refuse reason (same prose as incompleteness)."""
    return _assembly_preview_heard_wav_incompleteness(ctx, edl)


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


DOSSIER_READING_STAGES: frozenset[str] = frozenset(
    {
        "mastering_shape_agenda",
        "mastering_shape_candidates",
        "mastering_plan_synthesize",
        "mastering_plan_confirm",
    }
)


def _research_dossier_stale_incompleteness(ctx: RunContext) -> str | None:
    """A-01 latch: a rollup whose record the run has outgrown has not finished its job.

    Consumers are refused "resume mastering_research_rollup"; unless the rollup
    itself reads incomplete while its dossier is stale, nothing ever re-probes and
    the refusal holds for the rest of the phase. One re-run clears it.
    """
    try:
        from interview_mux.mastering_research import research_dossier_shape_core_stale

        if not research_dossier_shape_core_stale(ctx):
            return None
    except Exception:
        return None
    return (
        "research dossier stale — resume mastering_research_rollup: "
        "shape-core evidence landed after the rollup ran"
    )


def _research_thin_late_refuse(ctx: RunContext, stage_id: str) -> str | None:
    """A-01: Shape/gap consumers always late for shape-core thin (flags OFF OK).

    Rollup stays advisory until Shape about-to-bind. Do not refuse on global
    majority thin (W4–W8 expected thin at Pass1).

    The dossier records a probe taken when the rollup ran, so a completed rollup
    can pin consumers to evidence the run has since acquired. Stages that read
    the dossier stay refused on that record and the rollup re-runs to refresh it;
    stages that only need the evidence itself are judged on the live probe.
    """
    try:
        from interview_mux.mastering_research import research_shape_core_thin
    except Exception:
        return None
    if stage_id == "mastering_research_rollup":
        if _shape_about_to_bind(ctx) and research_shape_core_thin(ctx):
            return (
                "research dossier shape-core thin — resume mastering_research_rollup: "
                "late refuse — Shape about to bind"
            )
        return _research_dossier_stale_incompleteness(ctx)
    if stage_id not in RESEARCH_CONSUMER_STAGES:
        return None
    if stage_id in {"missing_framing", "gap_framing_compose", "optimal_questions"}:
        try:
            from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

            if gap_fill_was_skipped(ctx):
                return None
        except Exception:
            pass
    if not research_shape_core_thin(ctx):
        return None
    if stage_id not in DOSSIER_READING_STAGES and _research_dossier_stale_incompleteness(ctx):
        # Thin is the rollup's record, not the run: the evidence these stages
        # need is already on disk. Dossier readers keep waiting for the refresh.
        return None
    return (
        "research shape-core thin — resume mastering_research_rollup: "
        "not ready for Shape/gap consumers"
    )


def _mix_unseated_incompleteness(ctx: RunContext) -> str | None:
    """HX-2: mix is complete only when mix_outputs_seated (not mtime-only)."""
    try:
        from interview_mux.air_order import mix_outputs_seated

        if mix_outputs_seated(ctx):
            return None
    except Exception:
        pass
    return "mix unseated — resume mix: mix_outputs_seated"


def _junction_commitment_incompleteness(ctx: RunContext) -> str | None:
    """End-D: junction is hollow without commitment matching live assembly."""
    if not ctx.artifact_exists("master/junction_snip_qa.json"):
        return None
    if not ctx.artifact_exists("master/seam_autopsy.json"):
        return (
            "junction commitment missing — resume junction_snip_qa: "
            "seam_autopsy.json"
        )
    try:
        from interview_mux.homunculus.agenda import _junction_commitment_matches_assembly

        if _junction_commitment_matches_assembly(ctx):
            return None
    except Exception:
        return (
            "junction commitment unreadable — resume junction_snip_qa: "
            "commitment check failed"
        )
    return (
        "junction commitment mismatch — resume junction_snip_qa: "
        "refuse hollow seed-complete"
    )


def _episode_cover_incompleteness(ctx: RunContext) -> str | None:
    """HPUB-2: cover generate is hollow without publish/cover.jpg."""
    if ctx.artifact_exists("publish/cover.jpg"):
        return None
    return "cover_missing — resume episode_cover_generate: publish/cover.jpg missing"


def _podcast_publish_package_ready_incompleteness(ctx: RunContext) -> str | None:
    """HPUB-2: publish seed requires package_ready with ready:true, not chapters.json."""
    if not ctx.artifact_exists("publish/package_ready.json"):
        return (
            "package_ready — resume podcast_publish: "
            "publish/package_ready.json missing"
        )
    try:
        doc = ctx.read_json("publish/package_ready.json")
    except Exception:
        return (
            "package_ready — resume podcast_publish: "
            "publish/package_ready.json unreadable"
        )
    if not isinstance(doc, dict) or doc.get("ready") is not True:
        return (
            "package_ready — resume podcast_publish: "
            "publish/package_ready.json ready is not true"
        )
    return None


def _master_transcript_incompleteness(ctx: RunContext) -> str | None:
    """HPUB-3: seed-complete only with spoken cues and a VTT that has cue bodies."""
    from interview_mux.asset_transcripts import master_transcript_ship_incompleteness

    return master_transcript_ship_incompleteness(ctx)


def _source_acoustic_profile_incompleteness(ctx: RunContext) -> str | None:
    """HU-1: SAP is complete only when the JSON exists and passes schema."""
    rel = "understanding/source_acoustic_profile.json"
    if not ctx.artifact_exists(rel):
        return f"{rel} is pending — resume source_acoustic_profile:"
    try:
        from interview_mux.prompt_validation import validate_source_acoustic_profile

        doc = ctx.read_json(rel)
    except Exception as exc:
        return f"{rel} unreadable — resume source_acoustic_profile: {exc}"
    if not isinstance(doc, dict) or not doc:
        return f"{rel} schema-hollow — resume source_acoustic_profile:"
    errs = validate_source_acoustic_profile(doc)
    if errs:
        return f"{rel} schema-hollow — resume source_acoustic_profile: {errs[0]}"
    return None


def _sonic_context_incompleteness(ctx: RunContext) -> str | None:
    """HM-4: sonic_context_build is complete only when the JSON exists and passes schema.

    Empty tag_registry with sparse_mode is schema-valid (honest sparse briefing).
    Missing / {} / missing required keys stay incomplete. Do not invent a skip stub.
    """
    rel = "understanding/sonic_context.json"
    if not ctx.artifact_exists(rel):
        return f"{rel} is pending — resume sonic_context_build:"
    try:
        from interview_mux.write_staging import uncommitted_pending_reason

        shadow = uncommitted_pending_reason(ctx, rel)
        if shadow:
            return shadow
    except Exception:
        pass
    try:
        from interview_mux.prompt_validation import validate_sonic_context

        doc = ctx.read_json(rel)
    except Exception as exc:
        return f"{rel} unreadable — resume sonic_context_build: {exc}"
    if not isinstance(doc, dict):
        return f"{rel} schema-hollow — resume sonic_context_build:"
    body = {k: v for k, v in doc.items() if k != "_meta"}
    if not body:
        return f"{rel} schema-hollow — resume sonic_context_build:"
    errs = validate_sonic_context(doc)
    if errs:
        return f"{rel} schema-hollow — resume sonic_context_build: {errs[0]}"
    return None


_GAP_TAIL_STAGES: dict[str, str] = {
    "delivery_brief_build": "understanding/delivery_brief.json",
    "soundscape_policy_build": "understanding/soundscape_policy.json",
    "episode_structure_compose": "understanding/episode_structure.json",
}


def _gap_tail_validator(stage_id: str):
    from interview_mux.prompt_validation import (
        validate_delivery_brief,
        validate_episode_structure,
        validate_soundscape_policy,
    )

    return {
        "delivery_brief_build": validate_delivery_brief,
        "soundscape_policy_build": validate_soundscape_policy,
        "episode_structure_compose": validate_episode_structure,
    }.get(stage_id)


def _gap_tail_incompleteness(ctx: RunContext, stage_id: str) -> str | None:
    """HG-2: brief / soundscape / structure done only when the primary JSON passes schema.

    Disabled skip stubs are schema-valid (required keys; zero budgets allowed).
    Missing / {} / missing required keys stay incomplete.
    """
    rel = _GAP_TAIL_STAGES.get(stage_id)
    validator = _gap_tail_validator(stage_id)
    if not rel or validator is None:
        return None
    if not ctx.artifact_exists(rel):
        return f"{rel} is pending — resume {stage_id}:"
    try:
        from interview_mux.write_staging import uncommitted_pending_reason

        shadow = uncommitted_pending_reason(ctx, rel)
        if shadow:
            return shadow
    except Exception:
        pass
    try:
        doc = ctx.read_json(rel)
    except Exception as exc:
        return f"{rel} unreadable — resume {stage_id}: {exc}"
    if not isinstance(doc, dict):
        return f"{rel} schema-hollow — resume {stage_id}:"
    body = {k: v for k, v in doc.items() if k != "_meta"}
    if not body:
        return f"{rel} schema-hollow — resume {stage_id}:"
    errs = validator(doc)
    if errs:
        return f"{rel} schema-hollow — resume {stage_id}: {errs[0]}"
    return None


def _source_topology_incompleteness(ctx: RunContext) -> str | None:
    """HU-4: classify is complete only when topology and flow_adaptation both exist.

    Speaker-sample WAVs stay skip-only (not a done requirement).
    """
    topo = "understanding/source_topology.json"
    adapt = "understanding/flow_adaptation.json"
    if not ctx.artifact_exists(topo):
        return f"{topo} is pending — resume source_topology_build:"
    if not ctx.artifact_exists(adapt):
        return f"{adapt} is pending — resume source_topology_build:"
    return None


def _honest_vernacular_resplit_report(doc: dict[str, Any] | None) -> bool:
    """HS-5 1A: skip stub, rows list, or sanitize error — not `{}`."""
    if not isinstance(doc, dict):
        return False
    body = {k: v for k, v in doc.items() if k != "_meta"}
    if not body:
        return False
    skipped = body.get("skipped")
    if isinstance(skipped, str) and skipped.strip():
        return True
    if "rows" in body and isinstance(body.get("rows"), list):
        return True
    err = body.get("error")
    return isinstance(err, str) and bool(err.strip())


def _vernacular_restamped_manifest(ctx: RunContext) -> bool:
    """HS-5 1A: this producer restamped segments/manifest.json."""
    rel = "segments/manifest.json"
    if not ctx.artifact_exists(rel):
        return False
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
    return str(meta.get("producer_stage") or "") == "vernacular_segment_sanitize"


def _vernacular_segment_sanitize_incompleteness(ctx: RunContext) -> str | None:
    """HS-5: done only after an honest resplit_report or a vernacular restamp of manifest."""
    rel = "vernacular/resplit_report.json"
    try:
        from interview_mux.write_staging import uncommitted_pending_reason

        shadow = uncommitted_pending_reason(ctx, rel)
        if shadow:
            return shadow
    except Exception:
        pass
    if ctx.artifact_exists(rel):
        try:
            doc = ctx.read_json(rel)
        except Exception as exc:
            if _vernacular_restamped_manifest(ctx):
                return None
            return f"{rel} unreadable — resume vernacular_segment_sanitize: {exc}"
        if _honest_vernacular_resplit_report(doc if isinstance(doc, dict) else None):
            return None
    if _vernacular_restamped_manifest(ctx):
        return None
    if ctx.artifact_exists(rel):
        return f"{rel} schema-hollow — resume vernacular_segment_sanitize:"
    return f"{rel} is pending — resume vernacular_segment_sanitize:"


_MASTERING_SCHEMA_STAGES: dict[str, str] = {
    "mastering_research_routing": "mastering/research/routing.json",
    "mastering_research_waves": "mastering/research/waves.json",
    "mastering_research_rollup": "mastering/research/rollup.json",
    "mastering_shape_agenda": "mastering/shape/agenda.json",
    "mastering_shape_candidates": "mastering/shape/candidates.json",
}


def _mastering_schema_validator(stage_id: str):
    from interview_mux.prompt_validation import (
        validate_mastering_research_rollup,
        validate_mastering_research_routing,
        validate_mastering_research_waves,
        validate_mastering_shape_agenda,
        validate_mastering_shape_candidates,
    )

    return {
        "mastering_research_routing": validate_mastering_research_routing,
        "mastering_research_waves": validate_mastering_research_waves,
        "mastering_research_rollup": validate_mastering_research_rollup,
        "mastering_shape_agenda": validate_mastering_shape_agenda,
        "mastering_shape_candidates": validate_mastering_shape_candidates,
    }.get(stage_id)


def _mastering_plan_confirm_incompleteness(ctx: RunContext) -> str | None:
    """HM-1 leftover: a provisional synthesize plan must not hollow-complete confirm."""
    rel = "mastering/mastering_plan.json"
    if not ctx.artifact_exists(rel):
        return f"{rel} is pending — resume mastering_plan_confirm:"
    try:
        doc = ctx.read_json(rel)
    except Exception as exc:
        return f"{rel} unreadable — resume mastering_plan_confirm: {exc}"
    if not isinstance(doc, dict):
        return f"{rel} confirm-hollow — resume mastering_plan_confirm:"
    pass_name = str(doc.get("pass") or "").strip().lower()
    confirmed = doc.get("confirmed_mode")
    if pass_name == "confirmed" or (isinstance(confirmed, str) and confirmed.strip()):
        return None
    return (
        f"{rel} confirm-hollow — resume mastering_plan_confirm: "
        "pass is not confirmed (synthesize JSON is not enough)"
    )


def _mastering_schema_hollow_incompleteness(ctx: RunContext, stage_id: str) -> str | None:
    """HM-1: research/shape done only when the primary JSON passes the published schema."""
    rel = _MASTERING_SCHEMA_STAGES.get(stage_id)
    validator = _mastering_schema_validator(stage_id)
    if not rel or validator is None:
        return None
    if not ctx.artifact_exists(rel):
        return f"{rel} is pending — resume {stage_id}:"
    try:
        from interview_mux.write_staging import uncommitted_pending_reason

        shadow = uncommitted_pending_reason(ctx, rel)
        if shadow:
            return shadow
    except Exception:
        pass
    try:
        doc = ctx.read_json(rel)
    except Exception as exc:
        return f"{rel} unreadable — resume {stage_id}: {exc}"
    if not isinstance(doc, dict):
        return f"{rel} schema-hollow — resume {stage_id}:"
    body = {k: v for k, v in doc.items() if k != "_meta"}
    if not body:
        return f"{rel} schema-hollow — resume {stage_id}:"
    errs = validator(doc)
    if errs:
        return f"{rel} schema-hollow — resume {stage_id}: {errs[0]}"
    return None


def _transcript_review_build_incompleteness(ctx: RunContext) -> str | None:
    """HP-2: G0 build is complete only with a schema-valid review_queue (chunks may be empty)."""
    rel = "transcript/review_queue.json"
    if not ctx.artifact_exists(rel):
        return f"{rel} is pending — resume transcript_review_build:"
    try:
        from interview_mux.prompt_validation import validate_transcript_review_queue

        doc = ctx.read_json(rel)
    except Exception as exc:
        return f"{rel} unreadable — resume transcript_review_build: {exc}"
    if not isinstance(doc, dict) or "chunks" not in doc:
        return f"{rel} schema-hollow — resume transcript_review_build:"
    errs = validate_transcript_review_queue(doc)
    if errs:
        return f"{rel} schema-hollow — resume transcript_review_build: {errs[0]}"
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
        unseated = _mix_unseated_incompleteness(ctx)
        if unseated:
            return unseated
    if stage_id == "junction_snip_qa":
        junc = _junction_commitment_incompleteness(ctx)
        if junc:
            return junc
        # End-D: when commitment matches live assembly and primaries exist,
        # that is the seed-complete seal (do not schema-partial autopsy).
        if ctx.artifact_exists("master/junction_snip_qa.json") and ctx.artifact_exists(
            "master/seam_autopsy.json"
        ):
            return None
    if stage_id == "master_finalize":
        from interview_mux.delivery_invariants import committed_master_integrity_ok

        if not committed_master_integrity_ok(ctx):
            return (
                "master_finalize hollow — resume master_finalize: "
                "committed master.wav missing/truncated/pending"
            )
    if stage_id == "chapter_close_hitch":
        hitch = _hitch_layup_adopt_incompleteness(ctx)
        if hitch:
            return hitch
    if stage_id in {"air_script_compose", "nugget_layup_compose"}:
        try:
            from interview_mux.air_order_boundary import selection_commit_refused_reason

            refused = selection_commit_refused_reason(ctx, stage_id)
            if refused:
                return refused
        except Exception:
            pass
    if stage_id in {
        "refinement_agenda",
        "gap_framing_recompose",
        "selection_framing_apply",
    }:
        pass2 = _pass2_hollow_incompleteness(ctx, stage_id)
        if pass2:
            return pass2
        dirty = _pass2_gap_unsanitary_incompleteness(ctx, stage_id)
        if dirty:
            return dirty
    if stage_id == "assembly_preview":
        heard = _assembly_preview_heard_wav_incompleteness(ctx)
        if heard:
            return heard
    if stage_id == "episode_cover_generate":
        cover = _episode_cover_incompleteness(ctx)
        if cover:
            return cover
        return None
    if stage_id == "podcast_publish":
        pkg = _podcast_publish_package_ready_incompleteness(ctx)
        if pkg:
            return pkg
        return None
    if stage_id == "master_transcript_build":
        return _master_transcript_incompleteness(ctx)
    if stage_id == "source_acoustic_profile":
        return _source_acoustic_profile_incompleteness(ctx)
    if stage_id == "sonic_context_build":
        return _sonic_context_incompleteness(ctx)
    if stage_id in _GAP_TAIL_STAGES:
        return _gap_tail_incompleteness(ctx, stage_id)
    if stage_id == "source_topology_build":
        return _source_topology_incompleteness(ctx)
    if stage_id == "transcript_review_build":
        return _transcript_review_build_incompleteness(ctx)
    if stage_id == "vernacular_segment_sanitize":
        return _vernacular_segment_sanitize_incompleteness(ctx)
    if stage_id == "mastering_plan_confirm":
        confirm = _mastering_plan_confirm_incompleteness(ctx)
        if confirm:
            return confirm
    if stage_id in _MASTERING_SCHEMA_STAGES:
        hollow = _mastering_schema_hollow_incompleteness(ctx, stage_id)
        if hollow or stage_id != "mastering_research_rollup":
            return hollow
        # Schema-clean is not enough for the rollup: a dossier that no longer
        # describes the run leaves its consumers with nothing to wait for.
        return _research_dossier_stale_incompleteness(ctx)
    for path in stage_required_artifact_paths(stage_id):
        phase = (lifecycle or {}).get(path)
        if phase in ("n_a", "skipped"):
            continue
        if not ctx.artifact_exists(path):
            if (
                stage_id == "gap_framing_recompose"
                and path.endswith("gap_framing_recompose.json")
                and ctx.artifact_exists("understanding/refinement_skip_copy.json")
            ):
                continue
            try:
                from interview_mux.write_staging import uncommitted_pending_reason

                shadow = uncommitted_pending_reason(ctx, path)
                if shadow:
                    return shadow
            except Exception:
                pass
            return f"{path} is pending"
        try:
            from interview_mux.write_staging import uncommitted_pending_reason

            shadow = uncommitted_pending_reason(ctx, path)
            if shadow:
                return shadow
        except Exception:
            pass
        # F-04 hollow seats are Pass B (seams) only. HR-3: Pass A is complete
        # without seats once a real air_script write exists.
        if stage_id == "air_script_compose" and path.endswith("mastering_plan.json"):
            pass_a = _air_script_compose_pass_a_incompleteness(ctx)
            if pass_a:
                return pass_a
        if stage_id == "air_script_seams" and path.endswith("mastering_plan.json"):
            hollow = _air_script_hollow_seats_incompleteness(ctx)
            if hollow:
                return hollow
            drift = _air_script_seams_contract_drift(ctx)
            if drift:
                return drift
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
    if stage_id == "sound_design_vo_finalize":
        fin = _sound_design_vo_finalize_incompleteness(ctx)
        if fin:
            return fin
    if stage_id in {"missing_framing", "gap_framing_compose", "optimal_questions"}:
        stub = _gap_report_skip_stub_while_framing(ctx)
        if stub:
            return stub
    # A-01: research thin — early advisory; late/expected consumers refuse seed_complete.
    thin_reason = _research_thin_late_refuse(ctx, stage_id)
    if thin_reason:
        return thin_reason
    if stage_id == "missing_framing":
        filled = _missing_framing_batch_fill_incompleteness(ctx)
        if filled:
            return filled
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
            return "gap still unsanitary — resume gap_report_sanitize: " + "; ".join(
                gap_errs[:3]
            )
    if stage_id == "air_contract_sanitize":
        try:
            from interview_mux.artifact_sanitize.registry import air_contract_sanitary_errors

            air_errs = air_contract_sanitary_errors(ctx)
        except Exception:
            air_errs = []
        if air_errs:
            return (
                "air_contract_unsanitary — resume air_contract_sanitize: "
                + "; ".join(air_errs[:3])
            )
    if stage_id == "selection_order_sanitize":
        if not ctx.artifact_exists("master/selection.json"):
            return "master/selection.json is pending"
        try:
            from interview_mux.artifact_sanitize.registry import selection_sanitary_errors

            sel_errs = selection_sanitary_errors(ctx)
        except Exception:
            sel_errs = []
        if sel_errs:
            return "selection still unsanitary — resume selection_order_sanitize: " + "; ".join(
                sel_errs[:3]
            )
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
                    if label == "gap":
                        try:
                            pin = pass2_gap_heal_resume_stage(
                                ctx, error="gap_unsanitary", stage="vo_synthesize"
                            )
                            if pin:
                                resume = pin
                        except Exception:
                            pass
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
        hollow_vo = _vo_seed_hollow_seats_incompleteness(ctx)
        if hollow_vo:
            return hollow_vo
    if stage_id == "edl_narrative_audit":
        # Fail verdict first — hollow stage_done must not mask a blocking audit
        # (exec_11630: stale fail deferred EDL while assembly walked).
        if ctx.artifact_exists("master/edl_narrative_audit.json"):
            try:
                audit = ctx.read_json("master/edl_narrative_audit.json")
            except Exception:
                audit = None
            if isinstance(audit, dict) and str(audit.get("verdict") or "").strip().lower() == "fail":
                return "edl_narrative_audit verdict=fail — remutate/re-audit before edl"
        heard = _edl_narrative_audit_heard_wav_incompleteness(ctx)
        if heard:
            return heard
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
        # Required orientation without audible WAV must not seed-complete EDL.
        try:
            from interview_mux.gap_vo_gates import gap_framing_enabled
            from interview_mux.opening_orientation import (
                orientation_omitted,
                validate_opening_orientation,
            )

            if (
                gap_framing_enabled(ctx)
                and ctx.artifact_exists("understanding/gap_report.json")
                and ctx.artifact_exists("master/edl.json")
            ):
                gap = ctx.read_json("understanding/gap_report.json")
                edl_doc = ctx.read_json("master/edl.json")
                if (
                    isinstance(gap, dict)
                    and isinstance(edl_doc, dict)
                    and not orientation_omitted(gap)
                ):
                    opening_errors = validate_opening_orientation(
                        gap_report=gap, edl=edl_doc
                    )
                    inaudible = [
                        e
                        for e in opening_errors
                        if "opening_orientation_audible_count" in e
                        or "opening_orientation_count" in e
                    ]
                    if inaudible:
                        return (
                            "opening_orientation_inaudible — resume vo_synthesize: "
                            + "; ".join(inaudible[:2])
                        )
        except Exception:
            pass
    return None


def _air_script_compose_pass_a_incompleteness(ctx: RunContext) -> str | None:
    """HR-3: Pass A is markable without VO seats — seats are Pass B.

    Complete when ``air_script`` was written (``pass`` in {pass_a, pass_b} or
    nonempty beats). Empty seats + live gap lines must not refuse compose.
    """
    try:
        from interview_mux.air_script import air_script_enabled
        from interview_mux.mastering_plan_loader import load_plan_raw
    except Exception:
        return None
    if not air_script_enabled():
        return None
    plan = None
    try:
        plan = load_plan_raw(ctx)
    except Exception:
        plan = None
    if not isinstance(plan, dict):
        return "air_script_incomplete — Pass A air_script not written (plan missing)"
    script = plan.get("air_script") if isinstance(plan.get("air_script"), dict) else None
    if script is None:
        return "air_script_incomplete — Pass A air_script not written"
    beats = script.get("beats")
    if not isinstance(beats, list):
        return "air_script_incomplete — Pass A air_script not written (beats missing)"
    pass_name = str(script.get("pass") or "").strip()
    if pass_name in {"pass_a", "pass_b"}:
        return None
    if beats:
        return None
    return "air_script_incomplete — Pass A air_script not written (empty beats, no pass)"


def _air_script_hollow_seats_incompleteness(ctx: RunContext) -> str | None:
    """When air is on and live gap VO needs seats, empty seated_line_ids is hollow.

    Seams / Pass B only. Pass A uses ``_air_script_compose_pass_a_incompleteness``.
    """
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


def _air_script_seams_contract_drift(ctx: RunContext) -> str | None:
    """HF-2: remaining VO contract drift after Pass B is not a complete seams seed."""
    try:
        from interview_mux.air_script import SEAMS_CONTRACT_DRIFT_REL

        if ctx.artifact_exists(SEAMS_CONTRACT_DRIFT_REL):
            doc = ctx.read_json(SEAMS_CONTRACT_DRIFT_REL)
            if isinstance(doc, dict) and doc.get("active"):
                leftover = [str(x) for x in (doc.get("remaining") or []) if x]
                return "VO contract drift after air_script_seams: " + (
                    leftover[0] if leftover else "active"
                )
    except Exception:
        pass
    try:
        from interview_mux.vo_contract import seams_contract_remaining

        leftover = seams_contract_remaining(ctx)
        if leftover:
            return "VO contract drift after air_script_seams: " + leftover[0]
    except Exception:
        pass
    return None


def _vo_seed_hollow_seats_incompleteness(ctx: RunContext) -> str | None:
    """HV-4: live air-eligible synthesize lines + empty seats is not a complete VO seed.

    G1 optional skip waives record pickups, not this seated floor. Air-script
    seams keep ``_air_script_hollow_seats_incompleteness`` (F-04). Pass A
    compose is HR-3 (markable without seats).
    """
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
        if isinstance(row, dict)
        and gap_line_air_eligible(row)
        and str(row.get("delivery") or "").lower() == "synthesize"
        and row.get("line_id")
    ]
    if not live_ids:
        return None
    plan = None
    try:
        plan = load_plan_raw(ctx)
    except Exception:
        plan = None
    if not isinstance(plan, dict):
        return "vo seed hollow seats — live synthesize lines need seats but plan missing"
    script = plan.get("air_script") if isinstance(plan.get("air_script"), dict) else {}
    seats = script.get("vo_seats") if isinstance(script.get("vo_seats"), dict) else {}
    seated = [str(x) for x in (seats.get("seated_line_ids") or []) if x]
    if seated:
        return None
    return (
        "vo seed hollow seats — live synthesize lines need seats but seated_line_ids empty"
    )


def _hitch_layup_adopt_incompleteness(ctx: RunContext) -> str | None:
    """HR-1 3A: hitch is not complete while post-remap adopt_layup failed."""
    if not ctx.artifact_exists("mastering/chapter_close_hitch.json"):
        return None
    try:
        latch = ctx.read_json("mastering/chapter_close_hitch.json")
    except Exception:
        return None
    if not isinstance(latch, dict):
        return None
    adopt = latch.get("layup_adopt") if isinstance(latch.get("layup_adopt"), dict) else {}
    try:
        from interview_mux.chapter_close_hitch import hitch_layup_adopt_failed
    except Exception:
        return None
    if not hitch_layup_adopt_failed(adopt):
        return None
    err = str(adopt.get("error") or "adopt_failed")
    return f"hitch_layup_adopt_failed — resume nugget_layup_compose: {err}"


def _pass2_hollow_incompleteness(ctx: RunContext, stage_id: str) -> str | None:
    """HF-1: Pass-2 done requires a producer sidecar (or recompose skip-copy)."""
    if stage_id == "refinement_agenda":
        rel = "understanding/refinement_agenda.json"
        if not ctx.artifact_exists(rel):
            return f"{rel} is pending"
        return None
    if stage_id == "gap_framing_recompose":
        rel = "understanding/gap_framing_recompose.json"
        skip = "understanding/refinement_skip_copy.json"
        if ctx.artifact_exists(rel):
            try:
                doc = ctx.read_json(rel)
            except Exception:
                return f"{rel} is pending"
            if isinstance(doc, dict) and doc.get("refused"):
                reason = str(doc.get("reason") or "refused")
                if reason == "gap_unsanitary":
                    errs = [str(e) for e in (doc.get("errors") or []) if e]
                    tail = "; ".join(errs[:3]) if errs else "gap_needs_sanitize"
                    return f"gap_unsanitary — resume gap_framing_recompose: {tail}"
                return "gap_framing_recompose refused — " + reason
            return None
        if ctx.artifact_exists(skip):
            return None
        return f"{rel} is pending"
    if stage_id == "selection_framing_apply":
        rel = "understanding/selection_framing_apply.json"
        if not ctx.artifact_exists(rel):
            return f"{rel} is pending"
        try:
            doc = ctx.read_json(rel)
        except Exception:
            return f"{rel} is pending"
        if isinstance(doc, dict) and doc.get("refused"):
            reason = str(doc.get("reason") or "refused")
            if reason == "gap_unsanitary":
                errs = [str(e) for e in (doc.get("errors") or []) if e]
                tail = "; ".join(errs[:3]) if errs else "gap_needs_sanitize"
                return f"gap_unsanitary — resume selection_framing_apply: {tail}"
            return "selection_framing_apply refused — " + reason
        return None
    return None


def _pass2_sidecar_skipped(ctx: RunContext, stage_id: str) -> bool:
    rel = {
        "gap_framing_recompose": "understanding/gap_framing_recompose.json",
        "selection_framing_apply": "understanding/selection_framing_apply.json",
    }.get(str(stage_id or "").strip())
    if not rel or not ctx.artifact_exists(rel):
        return False
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return False
    return isinstance(doc, dict) and doc.get("skipped") is True


def _pass2_gap_unsanitary_incompleteness(ctx: RunContext, stage_id: str) -> str | None:
    """HF-5: Pass-2 writers must not seed-complete while gap is W1-unsanitary."""
    sid = str(stage_id or "").strip()
    if sid not in {"gap_framing_recompose", "selection_framing_apply"}:
        return None
    if _pass2_sidecar_skipped(ctx, sid):
        return None
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return None
    try:
        from interview_mux.artifact_sanitize.registry import gap_sanitary_errors

        errs = [
            str(e)
            for e in (gap_sanitary_errors(ctx) or [])
            if e and "missing" not in str(e).lower()
        ]
    except Exception:
        errs = []
    if not errs:
        return None
    return f"gap_unsanitary — resume {sid}: " + "; ".join(errs[:3])


def _sound_design_vo_finalize_incompleteness(ctx: RunContext) -> str | None:
    """HV-6: refuse/error sidecars are not a complete finalize seed."""
    rel = "mastering/sound_design_vo_finalize.json"
    if not ctx.artifact_exists(rel):
        return f"{rel} is pending"
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return f"{rel} is pending"
    if not isinstance(doc, dict):
        return f"{rel} is pending"
    if doc.get("refused"):
        reason = str(doc.get("reason") or "refused")
        if reason == "no_sound_design_plan":
            return (
                "vo_finalize refused — no sound_design_plan — resume sound_design_plan:"
            )
        return f"vo_finalize refused — {reason}"
    errs = [str(x) for x in (doc.get("errors") or []) if x]
    if errs:
        return "vo_finalize SDP invalid — " + errs[0]
    return None


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
    "seam_autopsy_blocking": "junction_snip_qa",
    "g1_vo_open": "vo_synthesize",  # synth path; record path via resolve_g1_vo_open_resume
    "g1_vo_incomplete": "vo_synthesize",
    "incomplete_cut_unresolved": "junction_snip_qa",
    "voice_reference_pending": "missing_framing",
    "assembly_seating_stale": "mix",
    "mix_unseated": "mix",
    "mix_outputs_seated": "mix",
    "air_script_incomplete": "air_script_compose",
    "air_script_seams": "air_script_seams",
    "edl_narrative_fail": "edl_narrative_audit",
    "pmq_structural": "master_finalize",
    # End-E: bare seed_order token is NOT mapped — parse named producer in
    # producer_pin_for_token (never default sealed edl/mix/master_finalize).
    # hollow_done / skip_then_consume: pin empty unless EDL is the incomplete producer.
    "hollow_done": "",
    "skip_then_consume": "",
    "hosted_vo_floor_unmet": "nugget_layup_compose",
    "hosted_framing_floor_unmet": "nugget_layup_compose",
    "transitions_missing": "transitions",
    "missing_transitions": "transitions",
    "g1_incomplete": "vo_synthesize",
    "premature_complete": "transitions",
    "chapter_close_hitch": "chapter_close_hitch",
    "nugget_corpus_mine": "nugget_corpus_mine",
    "information_package_plan": "information_package_plan",
    "ingest_missing": "ingest",
    "g0_pending": "transcript_review",
    "preclean_pending": "audio_preclean",
    "cover_missing": "episode_cover_generate",
    "package_ready": "podcast_publish",
    "cue_count_zero": "master_transcript_build",
    "header_only_vtt": "master_transcript_build",
    "encode_missing": "podcast_encode_mp3",
    "publish_advisories": "podcast_publish",
    # End-C: glue / framing quality — never pin sealed EDL consumer
    "bridge_incomplete": "transitions",
    "bridge_completeness": "transitions",
    "missing_forward_cue": "gap_framing_compose",
    "framing_before_impact": "gap_framing_compose",
    "framing_quality": "gap_framing_compose",
    # Sanitize / incompleteness tokens (Lock 5 / O3)
    "selection_unsanitary": "selection_order_sanitize",
    "gap_unsanitary": "gap_report_sanitize",
    "air_contract_unsanitary": "air_contract_sanitize",
    "layup_unsanitary": "nugget_layup_compose",
    "fragment_depth": "selection_order_sanitize",
    "sdp_unsanitary": "sound_design_plan",
    "vo_unsanitary": "vo_synthesize",
    "no_sound_design_plan": "sound_design_plan",
    "vo_finalize refused": "sound_design_vo_finalize",
    "vo_finalize SDP invalid": "sound_design_plan",
    "shape-core": "mastering_research_rollup",
    "research dossier": "mastering_research_rollup",
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
        from interview_mux.delivery_invariants import parse_seed_order_producer

        if "seed order" in text or "seed_order" in text:
            named = parse_seed_order_producer(reason)
            if named:
                return named
    except Exception:
        pass
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
        if "shape-core" in text or "research dossier" in text:
            return "mastering_research_rollup"
    except Exception:
        pass
    for token, pin in PRODUCER_PIN_TABLE.items():
        if token and token in text:
            return str(pin)
    return sid or ""


def _resume_stage_allowlist() -> set[str]:
    from interview_mux.v2.config import ANALYSIS_ORDER

    ids = {str(s) for s in DELIVERY_ORDER} | {str(s) for s in ANALYSIS_ORDER}
    ids.update(
        {
            "selection_order_sanitize",
            "gap_report_sanitize",
            "air_contract_sanitize",
            "transcript_review",
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
    if sid == "edl_narrative_audit":
        heard = _edl_narrative_audit_heard_wav_incompleteness(ctx)
        if heard:
            return "vo_synthesize"
    if sid == "assembly_preview":
        heard = _assembly_preview_heard_wav_incompleteness(ctx)
        if heard:
            return "vo_synthesize"
    if sid == "air_script_compose":
        try:
            from interview_mux.air_order_boundary import selection_commit_refused_reason

            if selection_commit_refused_reason(ctx, sid):
                return "air_script_compose"
        except Exception:
            pass
    if sid == "nugget_layup_compose":
        try:
            from interview_mux.air_order_boundary import selection_commit_refused_reason

            if selection_commit_refused_reason(ctx, sid):
                return "nugget_layup_compose"
        except Exception:
            pass
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
    if sid == "chapter_close_hitch":
        hitch = _hitch_layup_adopt_incompleteness(ctx)
        if hitch:
            return "nugget_layup_compose"
    if sid in {"gap_framing_recompose", "selection_framing_apply"}:
        dirty = _pass2_gap_unsanitary_incompleteness(ctx, sid)
        if dirty:
            return sid
        hollow = _pass2_hollow_incompleteness(ctx, sid)
        if hollow and "gap_unsanitary" in hollow:
            return sid
    if sid == "vo_synthesize":
        try:
            from interview_mux.artifact_sanitize.registry import gap_sanitary_errors

            if gap_sanitary_errors(ctx):
                pin = pass2_gap_heal_resume_stage(
                    ctx, error="gap_unsanitary", stage="vo_synthesize"
                )
                if pin:
                    return pin
        except Exception:
            pass
    if sid == "air_contract_sanitize":
        try:
            from interview_mux.artifact_sanitize.registry import air_contract_sanitary_errors

            if air_contract_sanitary_errors(ctx):
                return "air_contract_sanitize"
        except Exception:
            pass
    if sid == "selection_order_sanitize":
        try:
            from interview_mux.artifact_sanitize.registry import selection_sanitary_errors

            if selection_sanitary_errors(ctx):
                return "selection_order_sanitize"
        except Exception:
            pass
    if sid == "gap_report_sanitize":
        try:
            from interview_mux.artifact_sanitize.registry import gap_sanitary_errors

            if gap_sanitary_errors(ctx):
                return "gap_report_sanitize"
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
        mastering = mastering_heal_resume_stage(ctx, error=reason, stage=sid)
        if mastering:
            return mastering
        voice = voice_ref_heal_resume_stage(ctx, error=reason, stage=sid)
        if voice:
            return voice
    return None


def g0_heal_resume_stage(ctx: RunContext | None = None) -> str:
    """HP-4: queue exists → operator gate. Missing/hollow queue stays on build (HP-2)."""
    if ctx is not None:
        try:
            if _transcript_review_build_incompleteness(ctx):
                return "transcript_review_build"
        except Exception:
            if not ctx.artifact_exists("transcript/review_queue.json"):
                return "transcript_review_build"
    return "transcript_review"


def mastering_heal_resume_stage(
    ctx: RunContext | None = None,
    *,
    error: str = "",
    stage: str = "",
) -> str | None:
    """HM-2: shape-core thin → rollup; sonic/palettes self-pin unless the brief is named.

    Never returns ``edl`` / mix. Missing map stays None (caller keeps the consumer).
    """
    blob = f"{error} {stage}".strip().lower()
    sid = str(stage or "").strip()
    if (
        "shape-core" in blob
        or "research dossier" in blob
        or "research shape-core" in blob
    ):
        return "mastering_research_rollup"
    if ctx is not None and sid:
        try:
            thin = _research_thin_late_refuse(ctx, sid)
        except Exception:
            thin = None
        if thin:
            return "mastering_research_rollup"
    brief_named = "content_brief.json" in blob or "content_brief_reanchor" in blob
    sonic = sid == "sonic_context_build" or "sonic_context.json" in blob
    palettes = sid == "sound_design_palettes"
    if sonic or palettes:
        if brief_named:
            return "content_brief_reanchor"
        if palettes:
            return "sound_design_palettes"
        return "sonic_context_build"
    return None


def voice_ref_heal_resume_stage(
    ctx: RunContext | None = None,
    *,
    error: str = "",
    stage: str = "",
) -> str | None:
    """HG-4: open voice-ref pins missing_framing, never topic_coverage_audit / edl."""
    blob = f"{error} {stage}".strip().lower()
    if (
        "voice_reference_pending" in blob
        or "voice reference gate" in blob
        or "approve interviewer voice" in blob
    ):
        return "missing_framing"
    sid = str(stage or "").strip()
    if ctx is not None and sid == "topic_coverage_audit":
        try:
            from interview_mux.gap_vo_gates import check_voice_reference_pending

            if check_voice_reference_pending(ctx):
                return "missing_framing"
        except Exception:
            pass
    return None


def _pass2_non_skip_writer(ctx: RunContext | None) -> str | None:
    """Latest Pass-2 sidecar that actually ran (not a seat-freeze skip)."""
    if ctx is None:
        return None
    for sid, rel in (
        ("selection_framing_apply", "understanding/selection_framing_apply.json"),
        ("gap_framing_recompose", "understanding/gap_framing_recompose.json"),
    ):
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        if isinstance(doc, dict) and doc.get("skipped") is True:
            continue
        return sid
    return None


def pass2_gap_heal_resume_stage(
    ctx: RunContext | None = None,
    *,
    error: str = "",
    stage: str = "",
) -> str | None:
    """HF-5: Pass-2 re-dirtied gap pins the writer — never W1 while W3 freeze is stamped.

    None → callers keep ``gap_report_sanitize`` (W1 / HR-4).
    """
    sid = str(stage or "").strip()
    blob = f"{error} {stage}".strip().lower()
    if sid in {"gap_framing_recompose", "selection_framing_apply"}:
        return sid
    if "gap_framing_recompose" in blob and "selection_framing_apply" not in blob:
        return "gap_framing_recompose"
    if "selection_framing_apply" in blob:
        return "selection_framing_apply"
    writer = _pass2_non_skip_writer(ctx)
    freeze = False
    if ctx is not None:
        try:
            from interview_mux.seat_authority import soft_freeze_active

            freeze = bool(soft_freeze_active(ctx))
        except Exception:
            freeze = False
    if writer:
        return writer
    if freeze:
        return "selection_framing_apply"
    return None


def high_gap_heal_resume_stage(ctx: RunContext | None = None) -> str:
    """HG-5: layup owns (plan or authority) → nugget_layup_compose; else compose.

    ``gap_framing_compose`` no-ops under layup authority / a plan on disk.
    Analysis-era compose (no plan, no authority) is still the live writer.
    """
    if ctx is None:
        return "gap_framing_compose"
    try:
        from interview_mux.nugget_layup import (
            PLAN_REL,
            gap_report_has_layup_authority,
            nugget_layup_enabled,
        )

        if not nugget_layup_enabled():
            return "gap_framing_compose"
        if ctx.artifact_exists(PLAN_REL):
            return "nugget_layup_compose"
        gap = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else {}
        )
        if gap_report_has_layup_authority(gap if isinstance(gap, dict) else None):
            return "nugget_layup_compose"
    except Exception:
        pass
    return "gap_framing_compose"


def fuse_oscillation_heal_resume_stage(
    ctx: RunContext | None = None,
    *,
    error: str = "",
    stage: str = "",
) -> str:
    """HS-4: fuse oscillation pins the fuse writer, never ``edl``.

    Live pin: ``pre_ranking`` in the error / stage / residual ``pass_id`` →
    ``connector_fuse_pass_pre_ranking``; otherwise ``connector_fuse_pass``.
    """
    blob = f"{error} {stage}".strip().lower()
    sid = str(stage or "").strip()
    if "pre_ranking" in blob or sid == "connector_fuse_pass_pre_ranking":
        return "connector_fuse_pass_pre_ranking"
    if ctx is not None:
        try:
            from interview_mux.delivery_guardrails import DELIVERY_RESIDUALS_REL

            if ctx.artifact_exists(DELIVERY_RESIDUALS_REL):
                doc = ctx.read_json(DELIVERY_RESIDUALS_REL)
                rows = (doc or {}).get("residuals") if isinstance(doc, dict) else []
                for row in reversed(list(rows or [])):
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("kind") or "").lower() != "fuse_oscillation":
                        continue
                    state = str(row.get("state") or "open").lower()
                    if state not in {"", "open"}:
                        continue
                    detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
                    pass_id = str(
                        (detail or {}).get("pass_id") or row.get("stage") or ""
                    ).lower()
                    if "pre_ranking" in pass_id:
                        return "connector_fuse_pass_pre_ranking"
                    break
        except Exception:
            pass
    return "connector_fuse_pass"


def edl_vo_bind_unsanitary(ctx: RunContext) -> bool:
    """True when seated VO/bind is unsanitary or coverage is missing/stale."""
    try:
        from interview_mux.artifact_sanitize.registry import vo_sanitary_errors

        if vo_sanitary_errors(ctx):
            return True
    except Exception:
        pass
    try:
        from interview_mux.stage_input_checks import compact_vo_coverage_stale_or_missing

        if compact_vo_coverage_stale_or_missing(ctx):
            return True
    except Exception:
        pass
    return False


def edl_heal_resume_stage(ctx: RunContext | None = None) -> str:
    """HE-2: unsanitary VO/bind pins vo_synthesize; sanitary rebuild may resume edl."""
    if ctx is not None and edl_vo_bind_unsanitary(ctx):
        return "vo_synthesize"
    return "edl"


def producer_pin_for_token(
    token: str, *, default: str = "", ctx: RunContext | None = None
) -> str:
    key = str(token or "").strip().lower()
    # End-E: seed-order always parses the named producer — never sealed consumer default.
    if "seed order" in key or "seed_order" in key:
        try:
            from interview_mux.delivery_invariants import parse_seed_order_producer

            named = parse_seed_order_producer(token)
            if named:
                return named
        except Exception:
            pass
        # Bare seed_order token with no producer name — refuse sealed default.
        if default in {"edl", "mix", "master_finalize"}:
            return ""
        return default
    if "g0_pending" in key:
        return g0_heal_resume_stage(ctx)
    if "shape-core" in key or "research dossier" in key:
        return "mastering_research_rollup"
    if (
        "voice_reference_pending" in key
        or "voice reference gate" in key
        or "approve interviewer voice" in key
    ):
        return "missing_framing"
    if "high_gap_unframed" in key or (
        "high gap segment" in key and "no interviewer line" in key
    ):
        return high_gap_heal_resume_stage(ctx)
    if "fuse_oscillation" in key or "connector_fuse_oscillation" in key or (
        "oscillation_halt" in key and "fuse" in key and "junction" not in key
    ):
        return fuse_oscillation_heal_resume_stage(ctx, error=token)
    if "heard_wav_flow" in key:
        return "vo_synthesize"
    if "mix unseated" in key or "mix_unseated" in key or "mix_outputs_seated" in key:
        return "mix"
    if "music_incomplete" in key:
        if ctx is not None:
            try:
                from interview_mux.delivery_guardrails import _music_epoch_producer_pin

                pin = str(_music_epoch_producer_pin(ctx) or "").strip()
                if pin:
                    return pin
            except Exception:
                pass
        return "mmaudio_sfx"
    if "hitch_layup_adopt_failed" in key:
        return "nugget_layup_compose"
    if "selection_commit_refused" in key:
        parsed = parse_resume_stage_from_reason(token)
        if parsed in {"air_script_compose", "nugget_layup_compose"}:
            return parsed
        if "nugget_layup" in key:
            return "nugget_layup_compose"
        return "air_script_compose"
    if "gap_unsanitary" in key:
        pin = pass2_gap_heal_resume_stage(ctx, error=token, stage="")
        if pin:
            return pin
    if (
        "vo_audibility_drift" in key
        or "opening_orientation_inaudible" in key
        or "never_touch_zeroed_keep" in key
    ):
        return edl_heal_resume_stage(ctx)
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
    - intentional allow-stub (G1 optional skip waives *record*, not hollow seats)

    Under v2 auto-commit, in-stage ``heal_or_raise`` must flush this stage's
    pending writes before HC-3 ``pending_only`` incompleteness (exec_11630:
    ``audio_probe_build`` wrote ``run_golden_facts.json`` then raised before
    ``after_stage_write_check`` could commit).
    """
    sid = str(stage or "").strip()
    out: dict[str, Any] = {"stage": sid, "marked": False, "unmarked": False, "refused": False}
    if not sid:
        out["refused"] = True
        out["reason"] = "empty_stage"
        return out
    if not getattr(ctx, "_heal_flushing_stage", None):
        try:
            from interview_mux.v2.config import v2_auto_commit
            from interview_mux.write_staging import (
                _commit_stage_writes,
                active_stage,
                has_pending_writes,
                write_approval_enabled,
            )

            should_flush = (
                v2_auto_commit()
                and not write_approval_enabled()
                and has_pending_writes(ctx, sid)
            )
            # Flush owner pending even when active_stage already cleared
            # (write-then-raise before after_stage_write_check).
            if should_flush and active_stage() in {sid, None, ""}:
                ctx._heal_flushing_stage = sid
                try:
                    flushed = _commit_stage_writes(ctx, sid)
                    out["flushed"] = flushed
                    if ctx.is_done(sid):
                        out["marked"] = True
                        return out
                finally:
                    ctx._heal_flushing_stage = None
        except Exception as exc:  # noqa: BLE001
            out["flush_error"] = str(exc)[:240]
    reason = stage_artifact_incompleteness(ctx, sid)
    allow_stub = False
    if reason and force and sid in {"vo_synthesize", "vo_line_adjudicate"}:
        # Documented allow-stub: operator skipped optional G1 VO pickup.
        # HV-4: skip does not allow-stub while live synthesize lines have no seats.
        try:
            from interview_mux.gates import g1_vo_was_skipped_optional

            allow_stub = bool(g1_vo_was_skipped_optional(ctx))
            if allow_stub and _vo_seed_hollow_seats_incompleteness(ctx):
                allow_stub = False
            # HV-3 / 3A: G1 skip writes the adjudicate primary only when HV-4
            # hollow seats do not fire.
            if allow_stub and sid == "vo_line_adjudicate":
                from interview_mux.vo_line_adjudicate import persist_adjudication_skip_stub

                persist_adjudication_skip_stub(ctx, skip_reason="g1_skipped_optional")
                reason = stage_artifact_incompleteness(ctx, sid)
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


def heal_or_raise(ctx: RunContext, stage: str, *, force: bool = False) -> dict[str, Any]:
    """HF-4 / HR-4: heal is mark authority — never mute ``mark_done`` on refuse."""
    out = heal_or_refuse_mark(ctx, stage, force=force)
    if out.get("refused") or not (
        out.get("marked") or (hasattr(ctx, "is_done") and ctx.is_done(stage))
    ):
        reason = str(out.get("reason") or "").strip()
        if not reason:
            reason = stage_artifact_incompleteness(ctx, stage) or (
                f"{stage}_incomplete — resume {stage}: heal refused"
            )
        raise RuntimeError(reason)
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
