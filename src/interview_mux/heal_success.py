"""Heal Success Constitution (Heal Clinic heal_validate_stage_fail B+).

HC-HEAL-SUCCESS — plug into Done Constitution + Admit; not a fourth brand.

``finalize_heal_success`` is the sole gate for ``status=recovered`` across
pipeline / homunculus / driver. Refuse false recovered (identical ledger proceeds).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interview_mux.run_context import RunContext

# Only listed playbooks may attempt recovered — and only through finalize_heal_success.
RECOVER_PLAYBOOK_ALLOW: frozenset[str] = frozenset(
    {
        "cuts_empty_snap_demote",
        "stamp_valueless_skips",
        "orientation_retarget_open",
        "stamp_air_script_omits",
        "seam_mint_reorder",
        "ensure_mmaudio_qa",
        "generate_sdp_theme_wavs",
        "place_episode_close_cue",
        "ensure_g1_pickups",
        "adopt_layup_to_selection",
        "hitch_listen_restage",
        "listen_delight_remutate",
        "fingerprint_restamp_or_rerun",
        "speaker_roles_dominant_fallback",
        "skip_never_touch_cta_layups",
        "materialize_nle_split_children",
        "merge_overlapping_source_ranges",
        "host_cta_omit",
        "selection_edl_order_drift",
        "assembly_not_rendered_from_current_edl",
        "seed_order_prereq",
        "redundant_framing_transitions",
        "finalize_input_missing",
        "opening_slot_conflict",
        "post_master_quality_missing",
        "high_gap_unframed",
        "opening_orientation_inaudible",
        "vo_audibility_drift",
        "never_touch_zeroed_keep",
        "pending_write_barrier",
        "musicgen_theme_failed",
        "incomplete_cut_unresolved",
        "vo_seated_coverage",
        "vo_contract_repair",
        "upstream_stale_rerun",
        "air_script_omit_sync",
        # error_class-as-playbook defaults that recover via bool(artifacts)
        "empty_snap",
        "never_touch_cta",
        "layup_coverage",
        "framing_vo_unseated",
        "orientation_target_mismatch",
        "naked_seam",
        "mmaudio_qa_missing",
        "sdp_theme_wavs_missing",
        "episode_close_outro",
        "missing_g1_pickup",
        "layup_stale",
        "hitch_listen_restage",
        "listen_delight_floors",
        "fingerprint_mismatch",
        "speaker_roles",
        "pending_writes",
        "musicgen_failed",
        "incomplete_cut",
        "vo_coverage",
        "vo_contract",
        "upstream_stale",
        "air_script_omit",
        "seed_order",
        "g1_vo_open",
    }
)

# Default empty — recover always needs seed or resume-producer path.
RECOVER_ALLOW_WITHOUT_SEED: frozenset[str] = frozenset()

# Soft pre-flush may log but must not unlock mark_done (empty = halt soft).
SOFT_PRE_FLUSH_ALLOW: frozenset[str] = frozenset()

# Playbooks allowed to re-run the failed stage without producer resume.
SAME_STAGE_RETRY_ALLOW: frozenset[str] = frozenset(
    {
        "speaker_roles_dominant_fallback",
        "fingerprint_restamp_or_rerun",
        "stamp_valueless_skips",
        "stamp_air_script_omits",
        "vo_audibility_drift",
        "opening_orientation_inaudible",
        "never_touch_zeroed_keep",
        "listen_delight_remutate",
        # Host CTA omit intentionally re-enters layup with pruned selection
        # (exec_13177 / HR-2).
        "host_cta_omit",
    }
)


@dataclass(frozen=True)
class HealSuccessResult:
    ok: bool
    resume_stage: str
    reason: str
    recovered: bool

    @property
    def status(self) -> str:
        return "recovered" if self.recovered else "escalate"


def _artifact_signals_still_broken(artifacts: list[str] | None) -> bool:
    for raw in artifacts or []:
        s = str(raw or "").strip().lower()
        if not s:
            continue
        if s.startswith("missing:") or s.startswith("pending:"):
            return True
        if "incomplete" in s or "failed" in s or "unresolved" in s:
            return True
    return False


def heal_fail_predicate_clear(
    ctx: RunContext,
    error_class: str,
    *,
    artifacts: list[str] | None = None,
    detail: str = "",
) -> bool:
    """SSOT: is the fail predicate gone? (no free-prose playbook booleans)."""
    cls = str(error_class or "").strip()
    arts = list(artifacts or [])
    if _artifact_signals_still_broken(arts):
        return False

    if cls in {"sdp_theme_wavs_missing", "generate_sdp_theme_wavs"}:
        try:
            from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

            return not bool(missing_sdp_asset_wavs(ctx))
        except Exception:
            return False

    if cls in {"pending_write_barrier", "pending_writes"}:
        try:
            from interview_mux.write_staging import stages_with_pending_writes

            return not bool(stages_with_pending_writes(ctx))
        except Exception:
            # Empty artifact list means playbook saw no pending.
            return not bool(arts)

    if cls in {"musicgen_theme_failed", "musicgen_failed"}:
        # Resume to palette is work ahead — clear only if playbook wrote real paths.
        return bool(arts) and not _artifact_signals_still_broken(arts)

    if cls in {"incomplete_cut_unresolved", "incomplete_cut"}:
        return bool(arts) and not _artifact_signals_still_broken(arts)

    # Default: non-empty honest artifacts, or explicit empty-ok classes.
    if arts:
        return True
    # No artifacts → not clear (refuse unconditional recovered).
    _ = detail
    return False


def may_mark_after_flush(
    ctx: RunContext,
    stage_id: str,
    *,
    resilience_action: str,
    acceptance_ok: bool | None,
) -> tuple[bool, str]:
    """V3: mark_done only when post-flush does not signal acceptance failure.

    Fail-open for incomplete ``vo_synthesize`` is handled by raising after flush
    (S5 honest pin) via ``vo_synthesize_should_defer_done``. Do not also
    gate on ``seed_stage_complete`` here — that requires ``is_done`` and
    chicken-eggs first-time mark into ``flush_refuse:vo_fail_open_not_success``.
    """
    action = str(resilience_action or "").strip().lower()
    if action in {"halt", "escalate"} and acceptance_ok is False:
        return False, f"flush_refuse:{action}"
    if action == "retry" and acceptance_ok is False:
        return False, "flush_refuse:retry_acceptance_fail"
    sid = str(stage_id or "").strip()
    if not sid:
        return False, "empty_stage"
    try:
        from interview_mux.homunculus.agenda import stage_outputs_present
        from interview_mux.stage_completion import stage_artifact_incompleteness

        if stage_artifact_incompleteness(ctx, sid) is not None:
            return False, "flush_refuse:incompleteness"
        if not stage_outputs_present(ctx, sid):
            return False, "flush_refuse:outputs_missing"
    except Exception as exc:
        return False, f"flush_refuse:{type(exc).__name__}"
    return True, "ok"


def may_soft_pre_flush_pass(stage_id: str, *, soft_reason: str) -> bool:
    """V4: soft pre-flush never unlocks done unless stage explicitly allowlisted."""
    sid = str(stage_id or "").strip()
    if sid in SOFT_PRE_FLUSH_ALLOW:
        return True
    _ = soft_reason
    return False


def finalize_heal_success(
    ctx: RunContext,
    *,
    failed_stage: str,
    resume_stage: str = "",
    playbook_id: str = "",
    error_class: str = "",
    artifacts: list[str] | None = None,
    predicate_clear: bool | None = None,
    detail: str = "",
) -> HealSuccessResult:
    """Sole recovered gate — pipeline / runtime / driver must call this."""
    failed = str(failed_stage or "").strip()
    pid = str(playbook_id or "").strip()
    cls = str(error_class or pid).strip()
    resume_raw = str(resume_stage or failed).strip() or failed

    if not pid or pid not in RECOVER_PLAYBOOK_ALLOW:
        return HealSuccessResult(
            False, failed, f"heal_refuse:playbook_not_allowlisted:{pid}", False
        )

    clear = predicate_clear
    if clear is None:
        clear = heal_fail_predicate_clear(
            ctx, cls, artifacts=artifacts, detail=detail
        )
    if not clear:
        return HealSuccessResult(
            False, failed, "heal_refuse:predicate_not_clear", False
        )

    try:
        from interview_mux.heal_pin_authority import admit_resume

        resume = admit_resume(
            ctx,
            resume_raw,
            current=failed,
            error=cls,
            intent="heal_success",
        )
    except Exception:
        resume = resume_raw

    same_stage = (not resume) or resume == failed
    if same_stage:
        if pid not in SAME_STAGE_RETRY_ALLOW and pid not in RECOVER_ALLOW_WITHOUT_SEED:
            try:
                from interview_mux.delivery_guardrails import seed_stage_complete

                if not seed_stage_complete(ctx, failed):
                    return HealSuccessResult(
                        False,
                        failed,
                        "heal_refuse:same_stage_not_seed_complete",
                        False,
                    )
            except Exception:
                return HealSuccessResult(
                    False, failed, "heal_refuse:same_stage_seed_check_error", False
                )
        resume = failed or resume

    return HealSuccessResult(True, resume, "ok", True)


def soft_cross_validate_is_not_success() -> bool:
    """V11: soft cross-validate never counts as heal/recover success."""
    return True
