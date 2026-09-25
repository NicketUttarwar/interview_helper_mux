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


def _primary_artifact_thin_incompleteness(
    ctx: RunContext, stage_id: str, path: str
) -> str | None:
    """XC-HOLLOW-01: empty / byte-thin / empty-dict primary is not landable."""
    try:
        final = ctx.final_path(*str(path).split("/"))
        if not final.is_file():
            return None
        size = int(final.stat().st_size)
        if size <= 0:
            return f"{path} is empty (0 bytes) — resume {stage_id}"
        if size < 3 and str(path).endswith(".json"):
            return f"{path} is schema-thin — resume {stage_id}"
    except Exception:
        pass
    if not str(path).endswith(".json"):
        return None
    try:
        doc = ctx.read_json(path)
    except Exception:
        return f"{path} unreadable — resume {stage_id}"
    if doc is None:
        return f"{path} is null — resume {stage_id}"
    if isinstance(doc, dict) and not doc:
        return f"{path} is empty object — resume {stage_id}"
    if isinstance(doc, list) and not doc:
        # Empty list primaries are sometimes intentional (e.g. no gaps); leave to
        # specialized incompleteness. Only refuse empty dict / null / zero bytes.
        return None
    return None


def _gap_report_skip_stub_while_framing(ctx: RunContext) -> str | None:
    """Skip-producer / empty-seed gap_report is not complete once G-Framing is Yes.

    GRS-B2: sanitize must not hollow-complete on an empty stub when framing Yes.
    Intentional framing-skip (gap_fill_was_skipped) still allows empty skip stubs.
    Missing gap_report is not incompleteness for upstream stages (compose writes it).
    """
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
    meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
    producer = str(meta.get("producer") or "")
    lines = [
        row
        for row in (doc.get("interviewer_lines") or [])
        if isinstance(row, dict)
    ]
    gaps = [row for row in (doc.get("gaps") or []) if isinstance(row, dict)]
    empty_body = not lines and not gaps
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
    # GRS-B2: sanitize-seeded empty stub (missing-file path) while framing Yes.
    if empty_body and (
        producer in {"gap_report_sanitize_empty_seed", "gap_report_sanitize"}
        or meta.get("empty_stub") is True
    ):
        return (
            "understanding/gap_report.json is an empty stub while framing is enabled — "
            "resume nugget_layup_compose"
        )
    # GFC Q6B: framing Yes + compose zero lines allowed (helper always None).
    try:
        from interview_mux.openai_primary_honesty import gap_compose_zero_lines_while_framing

        compose_hollow = gap_compose_zero_lines_while_framing(doc, framing_enabled=True)
        if compose_hollow:
            return compose_hollow
    except Exception:
        pass
    return None


def _gap_report_missing_while_framing(
    ctx: RunContext, stage_id: str
) -> str | None:
    """S4: sanitize must not hollow-complete when gap_report is absent under framing Yes."""
    if stage_id != "gap_report_sanitize":
        return None
    if ctx.artifact_exists("understanding/gap_report.json"):
        return None
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled

        if not gap_framing_enabled(ctx):
            return None
    except Exception:
        return None
    return (
        "understanding/gap_report.json missing while framing enabled — "
        "resume nugget_layup_compose"
    )


def _high_gap_unframed_incompleteness(
    ctx: RunContext, stage_id: str
) -> str | None:
    """Refuse hollow compose/sanitize done while a high gap lacks an interviewer line.

    Seeds that spoken-copy-omit after write left `.stage_done` on compose while
    lint stayed dirty (exec_13157 seg_051) and driver heal thrash-locked layup.

    S5: ``nugget_layup_compose`` only blocks when the plan claimed air for a
    high-gap target that is still missing on gap_report; otherwise framing owns.
    """
    if stage_id not in {
        "gap_framing_compose",
        "optimal_questions",
        "gap_report_sanitize",
        "nugget_layup_compose",
    }:
        return None
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return None
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return None
    if stage_id == "nugget_layup_compose":
        try:
            from interview_mux.nugget_layup import layup_claimed_air_missing_high_gap

            claimed = layup_claimed_air_missing_high_gap(ctx)
        except Exception:
            claimed = []
        if not claimed:
            return None
        return (
            "high_gap_unframed — resume nugget_layup_compose: "
            "layup claimed air but gap missing line for "
            + ",".join(claimed[:4])
        )
    try:
        from interview_mux.deterministic_lint import _lint_optimal_questions
        from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

        if gap_fill_was_skipped(ctx):
            return None
        report = ctx.read_json("understanding/gap_report.json")
        if not isinstance(report, dict):
            return None
        errs = _lint_optimal_questions(report, ctx)
    except Exception:
        return None
    dirty = [e for e in errs if "has no interviewer line" in str(e)]
    if not dirty:
        return None
    resume_stage = high_gap_heal_resume_stage(ctx)
    return (
        f"high_gap_unframed — resume {resume_stage}: "
        + "; ".join(str(e) for e in dirty[:2])
    )


def _nugget_corpus_empty_incompleteness(ctx: RunContext) -> str | None:
    """NCM-B2: enabled mine with zero nuggets must not hollow-complete."""
    try:
        from interview_mux.nugget_layup import CORPUS_REL, nugget_layup_enabled
    except Exception:
        return None
    if not nugget_layup_enabled():
        return None
    if not ctx.artifact_exists(CORPUS_REL):
        return f"{CORPUS_REL} is pending"
    try:
        doc = ctx.read_json(CORPUS_REL)
    except Exception:
        return f"{CORPUS_REL} unreadable"
    if not isinstance(doc, dict):
        return f"{CORPUS_REL} unreadable"
    nuggets = [n for n in (doc.get("nuggets") or []) if isinstance(n, dict)]
    if nuggets:
        return None
    return (
        "nugget_corpus_empty — resume nugget_corpus_mine: "
        "enabled mine produced zero nuggets"
    )


def _information_package_corpus_incompleteness(ctx: RunContext) -> str | None:
    """IPP-B2: require_corpus + empty corpus must not warn-and-done."""
    try:
        from interview_mux.information_packages import (
            CORPUS_REL,
            _corpus_nuggets,
            information_packages_cfg,
        )
    except Exception:
        return None
    cfg = information_packages_cfg()
    if not cfg.get("enable", True):
        return None
    if not cfg.get("require_corpus", True):
        return None
    if _corpus_nuggets(ctx):
        return None
    return (
        "information_package_corpus_missing — resume nugget_corpus_mine: "
        f"{CORPUS_REL} empty while require_corpus"
    )


BATCH_FILL_BY = "missing_framing_batch_coverage"
REPAIR_FILL_BY = "repair_gap_evaluations"
MISSING_FRAMING_FILL_TAGS = frozenset({BATCH_FILL_BY, REPAIR_FILL_BY})
_BATCH_FILL_BY = BATCH_FILL_BY


def _missing_framing_batch_fill_incompleteness(ctx: RunContext) -> str | None:
    """HG-3 2B: unscored batch_fill rows refuse done.

    Default ``ok_with_light_bridge`` coverage fills are not LLM-scored. Persist is allowed;
    heal must not mark ``missing_framing`` complete until a leftover re-volley scores them
    or the in-invoke coverage CAP seals leftovers.

    Last-wins per ``segment_id`` (same as ``_split_keep_and_leftover``): a superseded
    fabricate/fill row must not strand done when a later keep-eligible row exists
    (exec_13198: duplicate repair fills + scored rows → attempt_memo thrash).
    """
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

    by_id: dict[str, dict] = {}
    for row in doc.get("evaluations") or []:
        if isinstance(row, dict) and row.get("segment_id"):
            by_id[str(row["segment_id"])] = row
    filled = [
        sid
        for sid, row in by_id.items()
        if _gap_eval_is_unscored_fill(row)
        and str((row.get("_meta") or {}).get("producer") or "") != "gap_fill_skip"
    ]
    if not filled:
        return None
    return (
        "missing_framing batch_fill — resume missing_framing: "
        f"LLM must score {len(filled)} segment(s) (examples {filled[:6]})"
    )


def _missing_framing_sealed_ratio_incompleteness(ctx: RunContext) -> str | None:
    """S7: one coverage-thin gate before CAP; hard_max STOP after CAP only.

    Safest collapse of soft sealed_ratio + sealed_vs_risk into a single
    ``coverage_thin`` resume predicate while coverage budget remains. After
    ``_coverage_rescue_exhausted``, only ``sealed_ratio_hard`` remains (operator
    STOP) — residual sealed_vs_risk alone must not thrash past CAP.
    """
    rel = "understanding/gap_evaluations.json"
    if not ctx.artifact_exists(rel):
        return None
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled

        if not gap_framing_enabled(ctx):
            return None
    except Exception:
        return None
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    if str((doc.get("_meta") or {}).get("producer") or "") == "gap_fill_skip":
        return None
    from interview_mux.stages.gaps import (
        _coverage_rescue_exhausted,
        _coverage_stats_from_doc,
        _gap_segment_ids,
        _sealed_ratio_hard_max,
        _sealed_vs_risk_ids,
    )

    required = _gap_segment_ids(ctx)
    if not required:
        return None
    stats = _coverage_stats_from_doc(doc, required)
    ratio = float(stats.get("sealed_ratio") or 0.0)
    max_ratio = float(stats.get("sealed_ratio_max") or 0.15)
    hard_max = float(stats.get("sealed_ratio_hard_max") or _sealed_ratio_hard_max())
    exhausted = _coverage_rescue_exhausted(doc)
    risk_sealed = _sealed_vs_risk_ids(ctx, doc)
    sealed_n = int(stats.get("sealed_count") or 0)
    examples = list(stats.get("sealed_ids") or [])[:6]
    if exhausted:
        if ratio > hard_max + 1e-9:
            return (
                "missing_framing sealed_ratio_hard — operator STOP: "
                f"after coverage CAP still sealed {sealed_n}/{stats.get('required_count')} "
                f"({ratio:.0%} > hard max {hard_max:.0%}); inspect "
                "understanding/stage_runs/missing_framing/coverage_report.json "
                f"(examples {examples})"
            )
        return None
    soft_ratio = ratio > max_ratio + 1e-9
    if not soft_ratio and not risk_sealed:
        return None
    detail_bits = [
        f"sealed {sealed_n}/{stats.get('required_count')} ({ratio:.0%} vs max {max_ratio:.0%})"
    ]
    if risk_sealed:
        detail_bits.append(
            f"sealed_vs_risk {len(risk_sealed)} (examples {risk_sealed[:6]})"
        )
    return (
        "missing_framing coverage_thin — resume missing_framing: "
        + "; ".join(detail_bits)
        + "; spend coverage pass on sealed/risk ids"
    )


def _missing_framing_stale_ids_incompleteness(ctx: RunContext) -> str | None:
    """Refuse done when gap_evaluations reference segment ids absent from manifest."""
    rel = "understanding/gap_evaluations.json"
    if not ctx.artifact_exists(rel) or not ctx.artifact_exists("segments/manifest.json"):
        return None
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled

        if not gap_framing_enabled(ctx):
            return None
    except Exception:
        return None
    try:
        doc = ctx.read_json(rel)
        man = ctx.read_json("segments/manifest.json")
    except Exception:
        return None
    if not isinstance(doc, dict) or not isinstance(man, dict):
        return None
    if str((doc.get("_meta") or {}).get("producer") or "") == "gap_fill_skip":
        return None
    manifest_ids = {
        str(s.get("segment_id"))
        for s in (man.get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }
    if not manifest_ids:
        return None
    orphans = [
        str(row.get("segment_id") or "")
        for row in (doc.get("evaluations") or [])
        if isinstance(row, dict)
        and str(row.get("segment_id") or "")
        and str(row.get("segment_id") or "") not in manifest_ids
    ]
    orphans = [s for s in orphans if s]
    if not orphans:
        return None
    return (
        "missing_framing stale_segment_ids — resume missing_framing: "
        f"{len(orphans)} evaluation id(s) not in manifest (examples {orphans[:6]})"
    )


def _missing_framing_high_without_mission_incompleteness(ctx: RunContext) -> str | None:
    """Refuse missing_framing done when high/critical rows lack mission text.

    Prevents compose fill spam from hollow high-gap evals (Phase 4A).
    """
    rel = "understanding/gap_evaluations.json"
    if not ctx.artifact_exists(rel):
        return None
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled

        if not gap_framing_enabled(ctx):
            return None
    except Exception:
        return None
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    if str((doc.get("_meta") or {}).get("producer") or "") == "gap_fill_skip":
        return None
    thin: list[str] = []
    for row in doc.get("evaluations") or []:
        if not isinstance(row, dict):
            continue
        sev = str(row.get("severity") or "").strip().lower()
        if sev not in {"high", "critical"}:
            continue
        sid = str(row.get("segment_id") or "").strip()
        if not sid:
            continue
        mission = str(
            row.get("listener_confusion")
            or row.get("mission")
            or row.get("why_it_matters")
            or ""
        ).strip()
        if len(mission) < 8:
            thin.append(sid)
    if not thin:
        return None
    return (
        "missing_framing high_without_mission — resume missing_framing: "
        f"{len(thin)} high/critical eval(s) lack mission text (examples {thin[:6]})"
    )


def _gap_evals_warrant_hosted_vo(ctx: RunContext) -> bool:
    """True when gap_evaluations imply compose should ship synthetic host VO.

    Avoids identical×3 compose thrash when sealed/ok-low evals honestly need
    zero lines under G-Framing Yes (Q6B / mass CAP seal).
    """
    rel = "understanding/gap_evaluations.json"
    if not ctx.artifact_exists(rel):
        # No evals yet — keep the floor strict so empty compose after a real
        # framing Yes path still surfaces.
        return True
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return True
    if not isinstance(doc, dict):
        return True
    if str((doc.get("_meta") or {}).get("producer") or "") == "gap_fill_skip":
        return False
    warrant = 0
    for row in doc.get("evaluations") or []:
        if not isinstance(row, dict):
            continue
        gtype = str(row.get("gap_type") or "").strip().lower()
        if not gtype or gtype in {"ok_with_light_bridge", "null", "none", "ok"}:
            continue
        sev = str(row.get("severity") or "").strip().lower()
        # R4: any missing_* gap type warrants hosted VO regardless of severity.
        if gtype.startswith("missing_"):
            warrant += 1
            continue
        if sev in {"medium", "high", "critical"}:
            warrant += 1
        elif sev == "low" and (
            "gap" in gtype or "bridge" in gtype or "setup" in gtype or "context" in gtype
        ):
            warrant += 1
    if warrant > 0:
        return True
    try:
        from interview_mux.stages.gaps import (
            _coverage_stats_from_doc,
            _gap_segment_ids,
        )

        stats = _coverage_stats_from_doc(doc, _gap_segment_ids(ctx))
        sealed = float(stats.get("sealed_ratio") or 0.0)
        # High seal fraction usually means under-scored VO need — keep floor.
        # Lowered from 0.25 so mass CAP-seal under Q6B still warrants hosted VO.
        if sealed > 0.15:
            return True
        # Any coverage_exhausted_accept seal row → warrant (compose must not
        # soft-green empty under framing Yes after CAP exhaustion).
        for row in doc.get("evaluations") or []:
            if not isinstance(row, dict):
                continue
            if bool(row.get("coverage_exhausted_accept")):
                return True
            seal = str(
                row.get("coverage_seal")
                or row.get("seal_reason")
                or row.get("severity_demotion_reason")
                or ""
            ).lower()
            if "coverage_exhausted" in seal:
                return True
    except Exception:
        pass
    return False


def _gap_framing_compose_hosted_floor_incompleteness(ctx: RunContext) -> str | None:
    """When G-Framing Yes + evals warrant VO, refuse compose if lines < hosted floor.

    Cluster C: HOLLOW_ZERO never aspirational-continues; PARTIAL may.

    S9 (safest): when layup authority stamp is live **with** a plan on disk,
    floor incompleteness belongs to ``nugget_layup_compose`` — compose no-ops
    under that stamp and must not thrash on hosted_vo_floor. Orphan stamp
    (no plan) still evaluates floor here after clear-and-run.
    """
    try:
        from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
        from interview_mux.gap_vo_gates import gap_framing_enabled
        from interview_mux.hosted_vo_authority import (
            floor_snapshot,
            may_aspirational_proceed,
            reconcile_escalations,
        )

        if gap_fill_was_skipped(ctx) or not gap_framing_enabled(ctx):
            return None
    except Exception:
        return None
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return None
    try:
        doc = ctx.read_json("understanding/gap_report.json")
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    if str((doc.get("_meta") or {}).get("producer") or "") == "gap_fill_skip":
        return None
    # S9: peel floor to layup when authority + plan are live.
    if bool(doc.get("nugget_layup_authority")):
        try:
            from interview_mux.nugget_layup import PLAN_REL, nugget_layup_enabled

            if nugget_layup_enabled() and ctx.artifact_exists(PLAN_REL):
                return None
        except Exception:
            pass
    try:
        snap = floor_snapshot(ctx, stage_id="gap_framing_compose", persist=True)
    except Exception:
        return None
    if snap.identity.status in {"MET", "UNWARRANTED", "WAIVED"}:
        reconcile_escalations(ctx, snap)
        return None
    need = snap.need
    active = snap.have
    if snap.identity.status == "PARTIAL" and may_aspirational_proceed(
        ctx, stage_id="gap_framing_compose"
    ):
        try:
            from interview_mux.floor_progress import proceed_on_floor_miss

            proceed_on_floor_miss(
                ctx,
                gate_id="hosted_vo_floor",
                have=active,
                need=need,
                pool_exhausted=True,
                extra={
                    "source": "gap_framing_compose_incompleteness",
                    "cause": snap.identity.cause,
                },
            )
            reconcile_escalations(ctx, snap)
            return None
        except Exception:
            pass
    if snap.identity.status == "HOLLOW_ZERO":
        # Still allow empty when evals do not warrant (Q6B).
        if not _gap_evals_warrant_hosted_vo(ctx):
            try:
                ctx.log(
                    "gap_framing_compose Q6B: HOLLOW_ZERO but evals do not warrant "
                    f"hosted VO — allowing empty (have={active} need={need})",
                    level="info",
                    stage="gap_framing_compose",
                    action_id="gap_framing_compose.q6b_empty_allowed",
                    detail={"active": active, "need": need},
                )
            except Exception:
                pass
            return None
        resume = snap.resume_producer or high_gap_heal_resume_stage(ctx)
        if resume == "nugget_layup_compose":
            return (
                "hosted_vo_floor_unmet — resume nugget_layup_compose: "
                f"G-Framing Yes requires ≥{need} synthetic host line(s), gap_report has {active}"
            )
        return (
            "gap_framing_compose hosted_vo_floor — resume gap_framing_compose: "
            f"G-Framing Yes requires ≥{need} synthetic host line(s), gap_report has {active}"
        )
    if not _gap_evals_warrant_hosted_vo(ctx):
        try:
            ctx.log(
                "gap_framing_compose Q6B: framing Yes with active lines below floor "
                f"({active}<{need}) but evals do not warrant hosted VO — allowing empty",
                level="info",
                stage="gap_framing_compose",
                action_id="gap_framing_compose.q6b_empty_allowed",
                detail={"active": active, "need": need},
            )
        except Exception:
            pass
        return None
    resume = snap.resume_producer or high_gap_heal_resume_stage(ctx)
    if resume == "nugget_layup_compose":
        return (
            "hosted_vo_floor_unmet — resume nugget_layup_compose: "
            f"G-Framing Yes requires ≥{need} synthetic host line(s), gap_report has {active}"
        )
    return (
        "gap_framing_compose hosted_vo_floor — resume gap_framing_compose: "
        f"G-Framing Yes requires ≥{need} synthetic host line(s), gap_report has {active}"
    )


def _missing_framing_vo_ladder_incompleteness(ctx: RunContext) -> str | None:
    """Distinct UX: voice-ref / pickup / consent / delivery vs gap_evaluations gaps."""
    try:
        from interview_mux.gap_vo_gates import (
            check_clone_consent_pending,
            check_gap_delivery_pending,
            check_gap_framing_decision_pending,
            check_voice_reference_pending,
            gap_framing_enabled,
        )
        from interview_mux.source_topology import check_pickup_speaker_pending
    except Exception:
        return None
    if check_gap_framing_decision_pending(ctx):
        return (
            "vo_path_not_ready — resume missing_framing: "
            "G-Framing decision still open (not a gap_evaluations / CAP-seal issue)"
        )
    if not gap_framing_enabled(ctx):
        return None
    if check_pickup_speaker_pending(ctx):
        return (
            "vo_path_not_ready — resume missing_framing: "
            "gap pickup speaker still unconfirmed "
            "(voice-ref ladder — not gap_evaluations incompleteness)"
        )
    if check_voice_reference_pending(ctx):
        return (
            "vo_path_not_ready — resume missing_framing: "
            "interviewer voice reference still pending approval "
            "(voice-ref ladder — not gap_evaluations incompleteness)"
        )
    if check_clone_consent_pending(ctx):
        return (
            "vo_path_not_ready — resume missing_framing: "
            "voice-clone consent still open "
            "(voice-ref ladder — not gap_evaluations incompleteness)"
        )
    if check_gap_delivery_pending(ctx):
        return (
            "vo_path_not_ready — resume missing_framing: "
            "gap VO delivery choice still open "
            "(voice-ref ladder — not gap_evaluations incompleteness)"
        )
    return None


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

    Never soft-done thin when Shape is about to bind (MRRoll-B1) — incompleteness
    must pin consumers (and late rollup) until probes refresh.

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
    """HX-2: mix is complete only when seated and remaster land is paid.

    Land Honesty: any remaster_in_flight or speech_first_remaster_owed blocks
    complete so orphan promote cannot restamp ``.stage_done/mix`` without
    ``clear_remaster`` (forensics exec_13183 + siblings).
    """
    try:
        from interview_mux.done_authority import unpaid_land_reason

        unpaid = unpaid_land_reason(ctx, "mix")
        if unpaid:
            return unpaid
    except Exception:
        pass
    try:
        from interview_mux.air_order import mix_outputs_seated

        if mix_outputs_seated(ctx):
            return None
    except Exception:
        pass
    return "mix unseated — resume mix: mix_outputs_seated"


def _junction_commitment_incompleteness(ctx: RunContext) -> str | None:
    """End-D: junction is hollow without commitment matching live assembly.

    S6(B): junction-owned remaster is paid for ``unpaid_land_reason``, but
    mid-flight still blocks seed-complete / orphan promote until ``clear_remaster``.
    """
    try:
        from interview_mux.mix_junction_seat import remaster_in_flight, remaster_owner

        if remaster_in_flight(ctx):
            owner_l = str(remaster_owner(ctx) or "").strip().lower()
            if owner_l in {"junction", "junction_snip_qa"}:
                return (
                    "junction remaster in flight — resume junction_snip_qa: "
                    "remaster_owner=junction (paid land; seat after clear_remaster)"
                )
    except Exception:
        pass
    try:
        from interview_mux.done_authority import unpaid_land_reason

        unpaid = unpaid_land_reason(ctx, "junction_snip_qa")
        if unpaid:
            return unpaid
    except Exception:
        pass
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


def _episode_cover_prompt_craft_incompleteness(ctx: RunContext) -> str | None:
    """ECPC-B1: cover_prompt.json with empty prompt must not hollow-complete.

    Fail-open harvest (F7) stays done when the assembled prompt is non-empty.
    Empty prompt after craft/harvest is incomplete — honest reject, not seed-done.
    """
    rel = "publish/cover_prompt.json"
    if not ctx.artifact_exists(rel):
        return f"{rel} is pending"
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return f"{rel} is pending"
    if not isinstance(doc, dict):
        return f"{rel} is pending"
    prompt = str(doc.get("prompt") or "").strip()
    if prompt:
        return None
    return (
        "cover_prompt empty — resume episode_cover_prompt_craft: "
        "publish/cover_prompt.json prompt is empty"
    )


def _episode_cover_incompleteness(ctx: RunContext) -> str | None:
    """HPUB-2: cover generate is hollow without publish/cover.jpg."""
    if ctx.artifact_exists("publish/cover.jpg"):
        return None
    return "cover_missing — resume episode_cover_generate: publish/cover.jpg missing"


def _podcast_encode_mp3_incompleteness(ctx: RunContext) -> str | None:
    """PEM-B1: missing/empty publish/audio.mp3 must not hollow-complete.

    Binary status already treats ≤1024-byte mp3 as partial; pin token
    ``encode_missing`` keeps resume routing aligned with producer_pin map.
    """
    rel = "publish/audio.mp3"
    st = artifact_status_for_stage(rel, ctx, "podcast_encode_mp3")
    if st == "complete":
        return None
    if st == "pending":
        return f"encode_missing — resume podcast_encode_mp3: {rel} missing"
    return f"encode_missing — resume podcast_encode_mp3: {rel} empty or incomplete"


def _podcast_publish_package_ready_incompleteness(ctx: RunContext) -> str | None:
    """HPUB-2: publish seed requires package_ready ready:true, or honest skip.

    Clinic B1: ``ready:false`` + ``skipped:true`` is seed-complete (operator
    Skip). Bare ``ready:false`` / chapters-only / missing package_ready stay
    hollow.
    """
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
    if not isinstance(doc, dict):
        return (
            "package_ready — resume podcast_publish: "
            "publish/package_ready.json unreadable"
        )
    if doc.get("ready") is True:
        return None
    if doc.get("skipped") is True:
        return None
    return (
        "package_ready — resume podcast_publish: "
        "publish/package_ready.json ready is not true"
    )


def _master_transcript_incompleteness(ctx: RunContext) -> str | None:
    """HPUB-3: seed-complete only with spoken cues and a VTT that has cue bodies."""
    from interview_mux.asset_transcripts import master_transcript_ship_incompleteness

    return master_transcript_ship_incompleteness(ctx)


def _pre_ranking_fuse_incompleteness(ctx: RunContext) -> str | None:
    """G4 + H6-B: pre_ranking done only with its own rounds SSOT; missing_manifest incomplete."""
    from interview_mux.segment_fuse import FUSE_ROUNDS_PRE_RANKING_PATH

    rel = FUSE_ROUNDS_PRE_RANKING_PATH
    if not ctx.artifact_exists(rel):
        return f"{rel} is pending — resume connector_fuse_pass_pre_ranking:"
    try:
        doc = ctx.read_json(rel)
    except Exception as exc:
        return f"{rel} unreadable — resume connector_fuse_pass_pre_ranking: {exc}"
    if not isinstance(doc, dict):
        return f"{rel} schema-hollow — resume connector_fuse_pass_pre_ranking:"
    if str(doc.get("pass_id") or "") != "pre_ranking":
        return (
            f"{rel} pass_id != pre_ranking — resume connector_fuse_pass_pre_ranking:"
        )
    skip = str(doc.get("skip_reason") or "")
    if skip == "missing_manifest":
        return (
            "connector_fuse_pass_pre_ranking incomplete — missing segments/manifest.json "
            "(resume segment_classification / hitch producers)"
        )
    # enabled=false skip is intentional complete (H6-B).
    return None


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
    # SSP-B1: invent_gate blocked under fail_closed must not count as done.
    if stage_id == "soundscape_policy_build":
        try:
            from interview_mux.soundscape_policy import fail_closed as _sc_fail_closed

            if _sc_fail_closed() and str(doc.get("invent_gate") or "") == "blocked":
                return (
                    f"{rel} invent_gate=blocked — resume soundscape_policy_build "
                    "(unpaid invent / sound_design_plan)"
                )
        except Exception:
            pass
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
    if stage_id == "audio_preclean":
        # HP-3 / prepare_outputs_present: operator skip is a finished outcome.
        if ctx.artifact_exists("preclean/skip.json"):
            return None
        if ctx.artifact_exists("preclean/isolated.wav"):
            return None
        return (
            "audio_preclean incomplete — resume audio_preclean: "
            "preclean/isolated.wav or preclean/skip.json"
        )
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
        # Remaster unpaid already returned above via unpaid_land_reason.
        if ctx.artifact_exists("master/junction_snip_qa.json") and ctx.artifact_exists(
            "master/seam_autopsy.json"
        ):
            return None
    # Land Honesty: unpaid obligation for any stage (layup stamp-alone, remutate,
    # shared-path) before specialized / generic path loops.
    try:
        from interview_mux.done_authority import unpaid_land_reason

        unpaid = unpaid_land_reason(ctx, stage_id)
        if unpaid and stage_id not in {"mix", "junction_snip_qa"}:
            # mix/junction already handled above with seating detail
            return unpaid
    except Exception:
        pass
    if stage_id == "master_finalize":
        from interview_mux.done_authority import finalize_incompleteness

        return finalize_incompleteness(ctx)
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
    if stage_id == "episode_cover_prompt_craft":
        empty_prompt = _episode_cover_prompt_craft_incompleteness(ctx)
        if empty_prompt:
            return empty_prompt
        return None
    if stage_id == "episode_cover_generate":
        cover = _episode_cover_incompleteness(ctx)
        if cover:
            return cover
        return None
    if stage_id == "podcast_encode_mp3":
        enc = _podcast_encode_mp3_incompleteness(ctx)
        if enc:
            return enc
        return None
    if stage_id == "podcast_publish":
        pkg = _podcast_publish_package_ready_incompleteness(ctx)
        if pkg:
            return pkg
        return None
    if stage_id == "master_transcript_build":
        return _master_transcript_incompleteness(ctx)
    if stage_id == "connector_fuse_pass_pre_ranking":
        return _pre_ranking_fuse_incompleteness(ctx)
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
    if stage_id == "mastering_research_routing":
        # CSP-05 / MRR: llm_failed stub must not heal-done.
        try:
            from interview_mux.openai_primary_honesty import (
                research_routing_llm_failed_incompleteness,
            )

            rel = _MASTERING_SCHEMA_STAGES.get(stage_id)
            if rel and ctx.artifact_exists(rel):
                rdoc = ctx.read_json(rel)
                llm_failed = research_routing_llm_failed_incompleteness(
                    rdoc if isinstance(rdoc, dict) else None
                )
                if llm_failed:
                    return llm_failed
        except Exception:
            pass
    if stage_id == "mastering_shape_agenda":
        # CSP-05 / MSA: rubric/agenda LLM fail notes must not heal-done.
        try:
            from interview_mux.openai_primary_honesty import (
                shape_agenda_rubric_llm_failed_incompleteness,
            )

            agenda = (
                ctx.read_json("mastering/shape/agenda.json")
                if ctx.artifact_exists("mastering/shape/agenda.json")
                else None
            )
            rubric = (
                ctx.read_json("mastering/shape/eval_rubric.json")
                if ctx.artifact_exists("mastering/shape/eval_rubric.json")
                else None
            )
            msa_fail = shape_agenda_rubric_llm_failed_incompleteness(
                agenda if isinstance(agenda, dict) else None,
                rubric if isinstance(rubric, dict) else None,
            )
            if msa_fail:
                return msa_fail
        except Exception:
            pass
    if stage_id == "topic_coverage_audit":
        # CSP-05 / TCA: soft-fail LLM hollow audit must not heal-done.
        try:
            from interview_mux.openai_primary_honesty import coverage_audit_hollow_incompleteness

            if ctx.artifact_exists("master/coverage_audit.json"):
                cdoc = ctx.read_json("master/coverage_audit.json")
                hollow_cov = coverage_audit_hollow_incompleteness(
                    cdoc if isinstance(cdoc, dict) else None
                )
                if hollow_cov:
                    return hollow_cov
        except Exception:
            pass
    if stage_id in _MASTERING_SCHEMA_STAGES:
        hollow = _mastering_schema_hollow_incompleteness(ctx, stage_id)
        if hollow or stage_id != "mastering_research_rollup":
            return hollow
        # Schema-clean is not enough for the rollup: a dossier that no longer
        # describes the run leaves its consumers with nothing to wait for.
        return _research_dossier_stale_incompleteness(ctx)
    # Voice-ref ladder must beat "gap_evaluations.json is pending" so operators
    # don't chase CAP/eval incompleteness while pickup/voice-ref/consent is open.
    if stage_id == "missing_framing":
        vo_ladder = _missing_framing_vo_ladder_incompleteness(ctx)
        if vo_ladder:
            return vo_ladder
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
            # S4: framing Yes + missing gap_report → pin layup (not generic pending).
            if (
                stage_id == "gap_report_sanitize"
                and path.endswith("gap_report.json")
            ):
                framing_miss = _gap_report_missing_while_framing(ctx, stage_id)
                if framing_miss:
                    return framing_miss
            try:
                from interview_mux.write_staging import uncommitted_pending_reason

                shadow = uncommitted_pending_reason(ctx, path)
                if shadow:
                    return shadow
            except Exception:
                pass
            return f"{path} is pending"
        # XC-HOLLOW-01 / Land Honesty: empty or schema-thin primary is not land.
        try:
            thin = _primary_artifact_thin_incompleteness(ctx, stage_id, path)
            if thin:
                return thin
        except Exception:
            pass
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
    if stage_id in {
        "missing_framing",
        "gap_framing_compose",
        "optimal_questions",
        "gap_report_sanitize",
        "nugget_layup_compose",
    }:
        missing = _gap_report_missing_while_framing(ctx, stage_id)
        if missing:
            return missing
        stub = _gap_report_skip_stub_while_framing(ctx)
        if stub:
            return stub
        high_gap = _high_gap_unframed_incompleteness(ctx, stage_id)
        if high_gap:
            return high_gap
    # A-01: research thin — early advisory; late/expected consumers refuse seed_complete.
    thin_reason = _research_thin_late_refuse(ctx, stage_id)
    if thin_reason:
        return thin_reason
    if stage_id == "nugget_corpus_mine":
        empty_corpus = _nugget_corpus_empty_incompleteness(ctx)
        if empty_corpus:
            return empty_corpus
    if stage_id == "information_package_plan":
        ip_corpus = _information_package_corpus_incompleteness(ctx)
        if ip_corpus:
            return ip_corpus
    if stage_id == "missing_framing":
        filled = _missing_framing_batch_fill_incompleteness(ctx)
        if filled:
            return filled
        sealed = _missing_framing_sealed_ratio_incompleteness(ctx)
        if sealed:
            return sealed
        stale = _missing_framing_stale_ids_incompleteness(ctx)
        if stale:
            return stale
        thin_high = _missing_framing_high_without_mission_incompleteness(ctx)
        if thin_high:
            return thin_high
    if stage_id in {"gap_framing_compose", "optimal_questions"}:
        floor = _gap_framing_compose_hosted_floor_incompleteness(ctx)
        if floor:
            return floor
    try:
        from interview_mux.gap_fill_eligibility import synthetic_vo_incompleteness

        vo_reason = synthetic_vo_incompleteness(ctx, stage_id)
    except Exception:
        vo_reason = None
    if vo_reason:
        return vo_reason
    if stage_id == "nugget_layup_compose":
        # Once EDL is committed, layup compose is frozen history — do not report
        # shard/freshness/sanitary incompleteness that rewinds mix under seal
        # (exec_13159 thrash).
        try:
            from interview_mux.artifact_ownership import current_epoch

            epoch = str(current_epoch(ctx) or "")
            if epoch in {"edl_sealed", "mix_seated", "junction_committed"} or (
                ctx.is_done("edl") and ctx.artifact_exists("master/edl.json")
            ):
                return None
        except Exception:
            pass
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
        # NLC-B1: mid-shard intermediate plan must not hollow-complete.
        try:
            from interview_mux.nugget_layup import PLAN_REL

            if ctx.artifact_exists(PLAN_REL):
                plan_doc = ctx.read_json(PLAN_REL)
                meta = (
                    plan_doc.get("_meta")
                    if isinstance(plan_doc, dict) and isinstance(plan_doc.get("_meta"), dict)
                    else {}
                )
                if meta.get("compose_shards_pending"):
                    idx = meta.get("compose_shard_index")
                    total = meta.get("compose_shard_total")
                    # Final-shard stamp (index==total) with layups present is a
                    # persist/flush race after batched complete — not mid-compose.
                    # Blocking here ×3-thrashes under hard freeze (exec_13177).
                    layups = plan_doc.get("layups") if isinstance(plan_doc, dict) else None
                    final_shard_done = (
                        idx is not None
                        and total is not None
                        and int(idx) >= int(total)
                        and isinstance(layups, list)
                        and len(layups) > 0
                    )
                    if not final_shard_done:
                        tail = ""
                        if idx is not None and total is not None:
                            tail = f" (shard {idx}/{total})"
                        return (
                            "layup_compose_shards_pending — resume nugget_layup_compose:"
                            + tail
                        )
                if meta.get("compose_qc_pending"):
                    errs = meta.get("compose_qc_errors") or []
                    tail = ""
                    if isinstance(errs, list) and errs:
                        tail = " " + "; ".join(str(e) for e in errs[:3])
                    return (
                        "layup_compose_qc_pending — resume nugget_layup_compose:"
                        + tail
                    )
                if meta.get("hosted_vo_floor_unsatisfiable"):
                    try:
                        from interview_mux.hosted_vo_authority import (
                            floor_snapshot,
                            may_aspirational_proceed,
                            reconcile_escalations,
                        )

                        snap = floor_snapshot(
                            ctx, stage_id="nugget_layup_compose", persist=True
                        )
                        detail = meta.get("hosted_vo_floor_unsatisfiable_detail") or {}
                        active = int(detail.get("active") or snap.have or 0)
                        need_n = int(detail.get("need") or snap.need or 0)
                        if snap.identity.status == "HOLLOW_ZERO" or active < 1:
                            return (
                                "hosted_vo_floor_unsatisfiable — needs_operator "
                                "(do not recompose): "
                                f"need={need_n} active={active} "
                                f"eligible={detail.get('eligible_nugget_count')}"
                            )
                        if may_aspirational_proceed(
                            ctx, stage_id="nugget_layup_compose"
                        ):
                            from interview_mux.floor_progress import proceed_on_floor_miss

                            proceed_on_floor_miss(
                                ctx,
                                gate_id="hosted_vo_floor",
                                have=active,
                                need=need_n,
                                pool_exhausted=True,
                                extra={
                                    "source": "stage_completion_unsatisfiable_cleared",
                                    "eligible": detail.get("eligible_nugget_count"),
                                    "cause": snap.identity.cause,
                                },
                            )
                            reconcile_escalations(ctx, snap)
                            return None
                    except Exception:
                        pass
                    detail = meta.get("hosted_vo_floor_unsatisfiable_detail") or {}
                    return (
                        "hosted_vo_floor_unsatisfiable — needs_operator (do not recompose): "
                        f"need={detail.get('need')} active={detail.get('active')} "
                        f"eligible={detail.get('eligible_nugget_count')}"
                    )
        except Exception:
            pass
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
        # S3: compose-thin gap coverage floor — pin layup (not gap_report_sanitize).
        try:
            from interview_mux.artifact_sanitize.gap_report import (
                gap_layup_coverage_errors,
            )

            cov_errs = gap_layup_coverage_errors(ctx)
        except Exception:
            cov_errs = []
        if cov_errs:
            return (
                "layup_coverage_below_floor — resume nugget_layup_compose: "
                + "; ".join(cov_errs[:3])
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
            blob = "; ".join(sel_errs[:3])
            pin = producer_pin_for_token(blob, default="selection_order_sanitize", ctx=ctx)
            if pin == "full_master_ranking":
                return (
                    "selection still unsanitary — resume full_master_ranking: " + blob
                )
            return (
                "selection still unsanitary — resume selection_order_sanitize: " + blob
            )
    if stage_id == "sound_design_plan":
        try:
            from interview_mux.homunculus.agenda import delivery_sdp_present

            mix_seat_paid = False
            try:
                from interview_mux.artifact_ownership import current_epoch

                mix_seat_paid = delivery_sdp_present(ctx) and str(
                    current_epoch(ctx) or ""
                ) in {"mix_seated", "junction_committed"}
            except Exception:
                mix_seat_paid = False
            if not mix_seat_paid and ctx.artifact_exists("master/assembly.wav"):
                try:
                    mix_seat_paid = delivery_sdp_present(ctx)
                except Exception:
                    mix_seat_paid = False
        except Exception:
            mix_seat_paid = False
        try:
            from interview_mux.artifact_sanitize.registry import (
                selection_sanitary_errors,
                sdp_sanitary_errors,
                layup_sanitary_errors,
            )

            # Mix-seat + paid delivery SDP: mark-done only — do not thrash on
            # upstream sanitize noise (S5 peel; invent already refused).
            if not mix_seat_paid:
                sel_errs = selection_sanitary_errors(ctx)
                if sel_errs:
                    return (
                        "selection_unsanitary — resume selection_order_sanitize: "
                        + "; ".join(sel_errs[:3])
                    )
                # After EDL, layup QC noise must not block SDP seed (exec_13159 mix rewind).
                edl_sealed = False
                try:
                    from interview_mux.artifact_ownership import current_epoch

                    edl_sealed = str(current_epoch(ctx) or "") in {
                        "edl_sealed",
                        "mix_seated",
                        "junction_committed",
                    } or (
                        ctx.is_done("edl") and ctx.artifact_exists("master/edl.json")
                    )
                except Exception:
                    edl_sealed = False
                if not edl_sealed:
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
        # S4: pairs / G1 / seated / vo sanitary / stale — one helper.
        try:
            from interview_mux.vo_contract import vo_synthesize_render_incompleteness

            render_reason = vo_synthesize_render_incompleteness(ctx)
        except Exception:
            render_reason = None
        if render_reason:
            return render_reason
        hollow_vo = _vo_seed_hollow_seats_incompleteness(ctx)
        if hollow_vo:
            return hollow_vo
    if stage_id == "edl_narrative_audit":
        # Only live blockers count; stale fail prose contradicted by current disk
        # must not make a complete audit hollow.
        try:
            from interview_mux.edl_narrative_remutate import (
                effective_narrative_blocking_issues,
            )

            if effective_narrative_blocking_issues(ctx):
                return (
                    "edl_narrative_audit has effective blocking issues "
                    "— remutate/re-audit before edl"
                )
        except Exception:
            pass
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
    if stage_id == "music_palette_compose":
        # MPC-B1: cue_count=0 with theme assets is hollow — not seed-complete.
        hollow_cues = _music_palette_hollow_cues_incompleteness(ctx)
        if hollow_cues:
            return hollow_cues
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
            from interview_mux.gates import check_g1_vo

            g1 = check_g1_vo(ctx)
            if g1:
                return "g1_open — refuse edl complete: " + ", ".join(str(x) for x in g1[:4])
        except Exception:
            pass
        try:
            from interview_mux.delivery_guardrails import seed_stage_complete

            if not seed_stage_complete(ctx, "vo_synthesize"):
                return "vo_synthesize incomplete — refuse edl complete"
            if not seed_stage_complete(ctx, "sound_design_vo_finalize"):
                # Soft: finalize may be marker-lag after seated WAVs; only block
                # when incompleteness is open (not mere missing done mark).
                fin_inc = stage_artifact_incompleteness(
                    ctx, "sound_design_vo_finalize"
                )
                if fin_inc:
                    return f"sound_design_vo_finalize incomplete — {fin_inc}"
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
        # SFA-B2: refused APPLY sidecars (missing/invalid selection, gap_unsanitary)
        # never seed-complete — even after mark_done_raw / force heal.
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


def _music_palette_hollow_cues_incompleteness(ctx: RunContext) -> str | None:
    """MPC-B1: cue_count=0 with SDP theme assets must not hollow-complete.

    Zero assets → zero cues is honest sparse. Compose primary missing stays on
    the generic pending path.
    """
    compose_rel = "sound_design/music_palette_compose.json"
    if not ctx.artifact_exists(compose_rel):
        return None
    asset_n = 0
    sdp_cue_n = 0
    if ctx.artifact_exists("understanding/sound_design_plan.json"):
        try:
            sdp = ctx.read_json("understanding/sound_design_plan.json")
        except Exception:
            sdp = None
        if isinstance(sdp, dict):
            asset_n = sum(
                1
                for a in (sdp.get("assets") or [])
                if isinstance(a, dict) and a.get("asset_id")
            )
            flow = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
            podcast = flow.get("podcast") if isinstance(flow.get("podcast"), dict) else {}
            sdp_cue_n = sum(
                1 for c in (podcast.get("cues") or []) if isinstance(c, dict)
            )
    if asset_n < 1:
        return None
    try:
        compose = ctx.read_json(compose_rel)
    except Exception:
        return None
    if not isinstance(compose, dict):
        return None
    try:
        if compose.get("cue_count") is not None:
            cue_count = int(compose.get("cue_count"))
        elif isinstance(compose.get("cues"), list):
            cue_count = len(compose.get("cues") or [])
        else:
            cue_count = sdp_cue_n
    except (TypeError, ValueError):
        cue_count = sdp_cue_n
    if cue_count >= 1:
        return None
    return (
        "music_palette_compose hollow cues — resume music_palette_compose: "
        "cue_count=0 with theme assets present"
    )


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
    "gap_delivery_pending": "missing_framing",
    "clone_consent_pending": "missing_framing",
    "pickup_speaker_pending": "missing_framing",
    "voice_reference_unusable": "missing_framing",
    "vo_path_not_ready": "missing_framing",
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
    "hosted_vo_hollow": "nugget_layup_compose",
    "hosted_vo_wav_coverage": "vo_synthesize",
    "hosted_vo_floor_unsatisfiable": "",  # escalate once — do not re-pin LLM compose
    "gap_framing_compose hosted_vo_floor": "gap_framing_compose",
    "hosted_vo_books_agree": "nugget_layup_compose",
    "missing_framing sealed_ratio_hard": "missing_framing",
    "missing_framing sealed_ratio": "missing_framing",
    "missing_framing sealed_vs_risk": "missing_framing",
    "missing_framing coverage_thin": "missing_framing",
    "missing_framing stale_segment_ids": "missing_framing",
    "missing_framing needs.rerun_stage": "missing_framing",
    "missing_framing empty shard": "missing_framing",
    "missing_hard_input_mastering_plan": "mastering_plan_synthesize",
    "hosted_framing_floor_unmet": "nugget_layup_compose",
    "transitions_missing": "transitions",
    "missing_transitions": "transitions",
    "g1_incomplete": "vo_synthesize",
    # vo_g1 before bare premature_complete — substring match must not steal G1 → transitions
    "vo_g1": "vo_synthesize",
    # Bare token only; producer_pin_for_token parses premature_complete:stage:<sid> / :vo_g1
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
    "layup_compose_qc_pending": "nugget_layup_compose",
    "layup_compose_shards_pending": "nugget_layup_compose",
    "layup_coverage_below_floor": "nugget_layup_compose",
    "fragment_depth": "selection_order_sanitize",
    "same_family_over_budget": "selection_order_sanitize",
    "selection_needs_sanitize": "selection_order_sanitize",
    "segment_starts_unavailable": "selection_order_sanitize",
    "chapters_emptied": "selection_order_sanitize",
    "chapters_emptied_by_sanitize": "selection_order_sanitize",
    "overlap_collapse_incomplete": "selection_order_sanitize",
    # Lattice / integrity — sanitize cannot restore without amplifying → ranking
    "hard_keep_missing_from_order": "full_master_ranking",
    "hard_keep_exceeds_fragment_depth": "full_master_ranking",
    "hard_keep_same_family_over_budget": "full_master_ranking",
    "hard_keep_span_collision": "full_master_ranking",
    "air_order_integrity_critical": "full_master_ranking",
    "never_exclude_primary_impact": "full_master_ranking",
    "framing:primary impact": "full_master_ranking",
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
    """Structured resume for a consumer's incompleteness (same branch, not regex).

    PIN_PREMATURE B6: **sole** live API — ``(ctx, consumer_stage)``. There is no
    shadowed prose-only overload; thrash/heal must call this signature only.
    """
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

            sel_errs = selection_sanitary_errors(ctx)
            if sel_errs:
                blob = "; ".join(sel_errs)
                ranked = producer_pin_for_token(blob, default="", ctx=ctx)
                if ranked == "full_master_ranking":
                    return "full_master_ranking"
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
    ladder_tokens = (
        "voice_reference_pending",
        "voice reference gate",
        "approve interviewer voice",
        "gap_delivery_pending",
        "gap delivery gate",
        "clone_consent_pending",
        "voice clone gate",
        "pickup_speaker_pending",
        "gap pickup speaker gate",
        "voice_reference_unusable",
        "vo_path_not_ready",
    )
    if any(tok in blob for tok in ladder_tokens):
        return "missing_framing"
    sid = str(stage or "").strip()
    if ctx is not None and sid == "topic_coverage_audit":
        try:
            from interview_mux.gap_vo_gates import check_voice_reference_pending

            if check_voice_reference_pending(ctx):
                # Refuse remap onto an already-complete framing pin (spine-freeze thrash).
                if ctx.is_done("missing_framing") and (
                    stage_artifact_incompleteness(ctx, "missing_framing") is None
                ):
                    return None
                # Real TCA producer incompleteness wins over voice-ref pickup race.
                tca_inc = stage_artifact_incompleteness(ctx, "topic_coverage_audit")
                if tca_inc and "coverage_audit" in str(tca_inc).lower():
                    return None
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
            # Probe failed — fail-closed: assume freeze so we never invent W1.
            freeze = True
    if writer:
        return writer
    if freeze:
        return "selection_framing_apply"
    return None


def high_gap_heal_resume_stage(ctx: RunContext | None = None) -> str:
    """S5: pin framing unless layup claimed air for a still-missing high-gap line.

    Plan-on-disk alone is not ownership — that used to thrash layup for upstream
    framing debt. Orphan ``nugget_layup_authority`` without a plan still pins compose.
    """
    if ctx is None:
        return "gap_framing_compose"
    try:
        from interview_mux.nugget_layup import (
            PLAN_REL,
            layup_claimed_air_missing_high_gap,
            nugget_layup_enabled,
        )

        if not nugget_layup_enabled():
            return "gap_framing_compose"
        if ctx.artifact_exists(PLAN_REL):
            try:
                if layup_claimed_air_missing_high_gap(ctx):
                    return "nugget_layup_compose"
            except Exception:
                # Prefer framing when the claim probe fails — avoid layup thrash.
                return "gap_framing_compose"
            return "gap_framing_compose"
    except Exception as exc:
        try:
            from interview_mux.nugget_layup import PLAN_REL as _PLAN_REL

            if ctx.artifact_exists(_PLAN_REL):
                # Plan exists but helpers failed — still prefer framing (S5).
                return "gap_framing_compose"
        except Exception:
            pass
        raise RuntimeError(
            f"high_gap_heal_resume_stage: layup/authority probe failed; "
            f"refusing gap_framing_compose default ({exc})"
        ) from exc
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


# Named premature_complete:<class> suffixes that must not fall through to bare
# "premature_complete" → transitions (exec_13165 substring steal).
_PREMATURE_NAMED_CLASSES: frozenset[str] = frozenset(
    {
        "vo_g1",
        "g1_vo",
        "g1_incomplete",
        "music_epoch",
        "mix_seat",
        "finalize_inputs",
        "phase_a_edl",
        "delivery_blocked",
        "incomplete_after_conductor",
        "mastering_shape_llm_hollow",
    }
)


def _bare_premature_complete_pin(ctx: RunContext | None) -> str:
    """S5: pin bare premature_complete to transitions only when transitions hollow.

    When ``master/transitions.json`` is already complete, walk earliest incomplete
    Flow-1 spine / delivery seat so delivery stalls do not sticky-count on
    transitions (exec_13165 thrash).
    """
    if ctx is not None:
        try:
            from interview_mux.artifact_completeness import artifact_status

            if artifact_status("master/transitions.json", ctx) == "complete":
                try:
                    from interview_mux.progression_spine import (
                        first_incomplete_flow1_spine_stage,
                    )

                    early = first_incomplete_flow1_spine_stage(ctx)
                    if early and early != "transitions":
                        return early
                except Exception:
                    pass
                try:
                    from interview_mux.mix_junction_seat import next_delivery_seat

                    seat = str(next_delivery_seat(ctx) or "").strip()
                    if seat and seat != "transitions":
                        return seat
                except Exception:
                    pass
                return "edl"
        except Exception:
            pass
    return "transitions"


def premature_class_pin(
    fail_key: str, ctx: RunContext | None = None
) -> str | None:
    """Parse ``premature_complete:<class>`` → producer pin via canonical resume.

    Returns None when the token is not a premature_complete key (caller falls
    through). Bare ``premature_complete`` alone → transitions when hollow;
    otherwise earliest incomplete Flow-1 / delivery seat (S5). Named classes
    never substring-steal to transitions.
    """
    key = str(fail_key or "").strip().lower()
    if "premature_complete" not in key:
        return None
    import re as _re_pc

    stage_m = _re_pc.search(r"premature_complete:stage:([a-z0-9_]+)", key)
    if stage_m:
        return stage_m.group(1)
    if "vo_g1" in key or "g1_vo" in key or "g1_incomplete" in key:
        if ctx is not None:
            try:
                from interview_mux.delivery_invariants import resolve_g1_vo_open_resume

                return resolve_g1_vo_open_resume(ctx)
            except Exception:
                pass
            try:
                from interview_mux.thrash_hardening import (
                    FAIL_CLASS_VO_G1,
                    canonical_resume_pin,
                )

                return canonical_resume_pin(ctx, FAIL_CLASS_VO_G1)
            except Exception:
                pass
        return "vo_synthesize"
    # Named class after premature_complete: (music_epoch, mix_seat, …)
    cls_m = _re_pc.search(r"premature_complete:([a-z0-9_]+)", key)
    cls = cls_m.group(1) if cls_m else ""
    if cls == "stage":
        # stage: without sid already handled; treat as bare.
        cls = ""
    if cls in _PREMATURE_NAMED_CLASSES:
        # Static / analysis pins before canonical (which may fall through to edl).
        static = {
            "music_epoch": "mmaudio_sfx",
            "mix_seat": "mix",
            "finalize_inputs": "edl",
            "phase_a_edl": "edl",
            "delivery_blocked": "edl",
            "incomplete_after_conductor": "edl",
            "mastering_shape_llm_hollow": "mastering_research_rollup",
        }
        if cls == "mastering_shape_llm_hollow":
            return static[cls]
        if ctx is not None and cls:
            try:
                from interview_mux.thrash_hardening import canonical_resume_pin

                pin = str(canonical_resume_pin(ctx, cls, hint="") or "").strip()
                if pin:
                    return pin
            except Exception:
                pass
        if cls in static:
            return static[cls]
        if cls in PRODUCER_PIN_TABLE:
            return PRODUCER_PIN_TABLE[cls]
        return "transitions"
    if cls:
        # B3-1: unknown premature_complete:<class> is not a fake stage id.
        return "transitions"
    if key == "premature_complete" or key.endswith(":premature_complete"):
        return _bare_premature_complete_pin(ctx)
    # Key contains premature_complete but no named class — still transitions
    # only when no other named class substring is present.
    for named in _PREMATURE_NAMED_CLASSES:
        if named in key:
            break
    else:
        if "premature_complete:stage:" not in key:
            return _bare_premature_complete_pin(ctx)
    return None


def producer_pin_for_token(
    token: str, *, default: str = "", ctx: RunContext | None = None
) -> str:
    """Map an error / incompleteness token to the earliest heal producer.

    PIN_PREMATURE family SSOT:
    - **B1** Compound: score ``mix_unseated``-family vs ``premature_complete:*``;
      longest needle wins; length ties prefer non-``mix`` (VO structured over seating).
    - **B2** Table walk: exact / delimited tokens and spaced phrases only — never
      bare stage-id substring (``\"mix\" in \"remix …\"``).
    - **B3** Unknown ``premature_complete:<class>`` → ``transitions``, never the
      class string as a fake stage id.
    """
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
    scored: list[tuple[int, str]] = []
    if "mix unseated" in key or "mix_unseated" in key or "mix_outputs_seated" in key:
        needle = (
            "mix_outputs_seated"
            if "mix_outputs_seated" in key
            else ("mix_unseated" if "mix_unseated" in key else "mix unseated")
        )
        scored.append((len(needle), "mix"))
    pc_pin = premature_class_pin(token, ctx)
    if pc_pin is not None:
        import re as _re_sc

        m = _re_sc.search(r"premature_complete(?::[a-z0-9_]+)*", key)
        nlen = len(m.group(0)) if m else len("premature_complete")
        scored.append((nlen, pc_pin))
    if scored:
        # B1: longest needle wins; ties prefer non-mix so structured premature
        # classes beat mix_unseated / mix_outputs_seated at equal length.
        scored.sort(key=lambda t: (t[0], t[1] != "mix"), reverse=True)
        return scored[0][1]
    if "music_incomplete" in key:
        if ctx is not None:
            try:
                from interview_mux.mix_junction_seat import next_delivery_seat

                pin = str(next_delivery_seat(ctx) or "").strip()
                if pin:
                    return pin
            except Exception:
                pass
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
    # SOS harden: lattice / integrity tokens pin ranking (not sanitize self-loop).
    if (
        "hard_keep_missing_from_order" in key
        or "hard_keep_exceeds_fragment_depth" in key
        or "hard_keep_same_family_over_budget" in key
        or "hard_keep_span_collision" in key
        or "air_order_integrity_critical" in key
        or "never_exclude_primary_impact" in key
        or "framing:primary impact" in key
        or "primary impact segment" in key
    ):
        return "full_master_ranking"
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
    # B2-2: exact tokens / structured phrases only — never bare stage-id substring
    # (``"mix" in "remix bed failed"``). Whole-key and delimited tokens win by length.
    import re as _re_pin

    scored_exact: list[tuple[int, str]] = []
    tokens = _re_pin.findall(r"[a-z0-9_]+(?::[a-z0-9_]+)*", key)
    seen_tok: set[str] = set()
    for tok in tokens:
        if tok in seen_tok:
            continue
        seen_tok.add(tok)
        if tok in PRODUCER_PIN_TABLE:
            pin = PRODUCER_PIN_TABLE[tok]
            if pin:
                scored_exact.append((len(tok), pin))
    for needle, pin in PRODUCER_PIN_TABLE.items():
        if not needle or not pin:
            continue
        # Multi-word / spaced phrases (e.g. "vo_finalize refused") — whole phrase only.
        if " " in needle and needle in key:
            scored_exact.append((len(needle), pin))
    if scored_exact:
        scored_exact.sort(key=lambda t: t[0], reverse=True)
        return scored_exact[0][1]
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
            # Skip when already stamped done: HC-3 pending_only must unmark,
            # not promote orphan leftover staging into a hollow commit.
            if (
                should_flush
                and not ctx.is_done(sid)
                and active_stage() in {sid, None, ""}
            ):
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
            # Hollow-pass R2: raw stamp only via Done Authority session + outputs.
            try:
                from interview_mux.done_authority import raw_stamp_session
                from interview_mux.homunculus.agenda import stage_outputs_present

                if not stage_outputs_present(ctx, sid) and not allow_stub:
                    out["refused"] = True
                    out["reason"] = f"hollow_refuse_raw:{sid}:outputs_missing"
                    return out
                with raw_stamp_session(ctx, "heal_or_refuse_mark"):
                    ctx.mark_done(sid, force=bool(force))
            except Exception as exc:
                out["refused"] = True
                out["reason"] = f"raw_stamp_refused:{type(exc).__name__}:{exc}"[:240]
                return out
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
    """HF-4 / HR-4: heal is mark authority — never mute ``mark_done`` on refuse.

    Heal Success V10: success ≡ seed-complete (not bare ``is_done``).
    """
    out = heal_or_refuse_mark(ctx, stage, force=force)
    try:
        from interview_mux.delivery_guardrails import seed_stage_complete

        ok = bool(out.get("marked")) or seed_stage_complete(ctx, stage)
    except Exception:
        ok = bool(out.get("marked") or (hasattr(ctx, "is_done") and ctx.is_done(stage)))
    if out.get("refused") or not ok:
        # Prefer real flush/commit barrier failure over HC-3 pending_only mask
        # (exec_13177: missing rationale halted flush, then pending_only thrash).
        flush_err = str(out.get("flush_error") or "").strip()
        reason = str(out.get("reason") or "").strip()
        if flush_err and (
            not reason
            or "pending_only" in reason
            or reason.startswith("understanding/")
        ):
            reason = f"flush_failed:{flush_err}"
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
