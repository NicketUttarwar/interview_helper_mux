"""Wave 8 — Residual cluster Done-when scorecard (A–G catalog).

SSOT for named proof pointers + cheap inline contract smokes. Heavy unit/vitest
execution stays in those suites; RSTM RC-DW cells assert coverage + optional
inline smokes only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_IDS: frozenset[str] = frozenset(
    [f"A-{i:02d}" for i in range(1, 6)]
    + [f"B-{i:02d}" for i in range(1, 8)]
    + [f"C-{i:02d}" for i in range(1, 6)]
    + [f"D-{i:02d}" for i in range(1, 9)]
    + [f"E-{i:02d}" for i in range(1, 6)]
    + [f"F-{i:02d}" for i in range(1, 8)]
    + [f"G-{i:02d}" for i in range(1, 4)]
)


def _pytest(nodeid: str) -> dict[str, str]:
    return {"kind": "pytest", "nodeid": nodeid}


def _vitest(path: str) -> dict[str, str]:
    return {"kind": "vitest", "path": path}


def _inline(name: str) -> dict[str, str]:
    return {"kind": "inline", "nodeid": name}


# ---------------------------------------------------------------------------
# Inline smokes (contract / source / tiny RunContext) — no heavy stage exec
# ---------------------------------------------------------------------------


def smoke_f02_vernacular_shadow_ledger(_ctx: Any = None) -> None:
    """F-02: auto-pack must ledger vernacular must_keep drops (shadow or wasted_work)."""
    src = (ROOT / "src/interview_mux/selection_auto_pack.py").read_text(encoding="utf-8")
    has_shadow = "vernacular_shadow_drop" in src
    has_wasted = "record_wasted_work" in src and "vernacular" in src.lower()
    has_policy = "shadow_must_keep_policy" in src
    assert (has_shadow or has_wasted) and has_policy, (
        "selection_auto_pack needs vernacular_shadow_drop ledger "
        "+ shadow_must_keep_policy (ledger|block)"
    )


def smoke_f03_invent_obligation(_ctx: Any = None) -> None:
    """F-03: invent obligation / invent-gate string present for deferred palettes."""
    policy = (ROOT / "src/interview_mux/soundscape_policy.py").read_text(encoding="utf-8")
    stages = (ROOT / "src/interview_mux/stages/sound_design_stages.py").read_text(
        encoding="utf-8"
    )
    completion = (ROOT / "src/interview_mux/stage_completion.py").read_text(encoding="utf-8")
    blob = policy + stages + completion
    assert "invent_obligation" in blob
    assert "invent_gate" in policy or "_apply_invent_obligation_gate" in policy, (
        "expected invent_gate contract in soundscape_policy for F-03"
    )


def smoke_b02_delivery_residual_ledger(_ctx: Any = None) -> None:
    """B-02: fuse oscillation → delivery residual ledger readable by ship."""
    fuse = (ROOT / "src/interview_mux/segment_fuse.py").read_text(encoding="utf-8")
    guard = (ROOT / "src/interview_mux/delivery_guardrails.py").read_text(encoding="utf-8")
    assert "record_delivery_residual" in fuse
    assert "fuse_oscillation" in fuse
    assert "def record_delivery_residual" in guard
    assert "def critical_residual_view" in guard
    assert "def has_critical_residuals" in guard
    # Residuals are advisory for ship since ISSUES 185: the ledger is still
    # recorded and readable, but no longer a ship_path_ready refusal.


def smoke_b03_junction_family_budget(_ctx: Any = None) -> None:
    """B-03: remaster↔hitch↔fuse share FAMILY_JUNCTION ceiling."""
    src = (ROOT / "src/interview_mux/heal_routing.py").read_text(encoding="utf-8")
    assert "FAMILY_JUNCTION" in src
    assert "junction_family" in src
    assert "FAMILY_JUNCTION," in src or "FAMILY_JUNCTION\n" in src
    assert "HALT_FAMILIES" in src and "FAMILY_JUNCTION" in src
    # FAMILY_JUNCTION must be a member of HALT_FAMILIES (not only a constant).
    halt_block = src[src.index("HALT_FAMILIES") : src.index("HALT_FAMILIES") + 500]
    assert "FAMILY_JUNCTION" in halt_block
    thrash = (ROOT / "src/interview_mux/thrash_hardening.py").read_text(encoding="utf-8")
    assert "junction_remaster_budget" in thrash
    assert "record_delivery_residual" in thrash


def smoke_f04_air_fail_open_auto(_ctx: Any = None) -> None:
    """F-04: air_script_cfg forces fail_open=False under auto (secondary smoke)."""
    src = (ROOT / "src/interview_mux/air_script.py").read_text(encoding="utf-8")
    assert "fail_open" in src
    assert 'out["fail_open"] = False' in src or 'fail_open"] = False' in src


def smoke_f05_mix_overlay_authority(_ctx: Any = None) -> None:
    """F-05: mix overlay stamps overlay_authority (secondary smoke)."""
    src = (ROOT / "src/interview_mux/sound_design.py").read_text(encoding="utf-8")
    assert "overlay_authority" in src
    assert "missing_assets" in src
    assert "sdp_placeholders" in src or "legacy_fallback" in src


def smoke_f06_refine_stage_retired(_ctx: Any = None) -> None:
    """F-06: ghost refine ids raise StageRetired and are non-dispatchable."""
    from interview_mux.pipeline import DELIVERY_ORDER
    from interview_mux.refinement_passes import RETIRED_REFINE_GHOSTS, refuse_retired_refine
    from interview_mux.web.stages import STAGE_BY_ID

    assert "sfx_prompt_refine" not in RETIRED_REFINE_GHOSTS
    assert "ranking_refine" in RETIRED_REFINE_GHOSTS
    for ghost in RETIRED_REFINE_GHOSTS:
        assert ghost not in DELIVERY_ORDER
        assert ghost not in STAGE_BY_ID
    try:
        refuse_retired_refine("ranking_refine")
        raise AssertionError("expected StageRetired")
    except RuntimeError as exc:
        assert "StageRetired" in str(exc)
    src = (ROOT / "src/interview_mux/refinement_passes.py").read_text(encoding="utf-8")
    assert "RETIRED_REFINE_GHOSTS" in src
    assert "refuse_retired_refine" in src
    pipe = (ROOT / "src/interview_mux/pipeline.py").read_text(encoding="utf-8")
    assert "run_ranking_refine(ctx)" not in pipe
    assert '"ranking_refine": lambda' not in pipe


def smoke_f07_pending_read_rules(_ctx: Any = None) -> None:
    """F-07: write_staging documents flush/commit discard + consumer read rules."""
    src = (ROOT / "src/interview_mux/write_staging.py").read_text(encoding="utf-8")
    assert "after_flush_resilience" in src or "discard_stage_writes" in src
    assert "pending" in src


def smoke_d05_manual_producer_pin(_ctx: Any = None) -> None:
    """D-05: premature_cap / seed pin helpers exist for consumer-first thrash."""
    src = (ROOT / "src/interview_mux/delivery_guardrails.py").read_text(encoding="utf-8")
    assert "def premature_cap_hard_pin" in src or "premature_cap_hard_pin(" in src


def smoke_g03_preclean_optional_copy(_ctx: Any = None) -> None:
    """G-03: Preclean optional copy + Skip CTA; optimizer surfaces auto_started."""
    card = (ROOT / "frontend/src/components/gates/PrecleanOfferCard.tsx").read_text(
        encoding="utf-8"
    )
    assert "Optional" in card
    assert "Skip" in card
    opt = (ROOT / "frontend/src/components/gates/TimelineOptimizerPanel.tsx").read_text(
        encoding="utf-8"
    )
    assert "auto_started" in opt


INLINE_SMOKES: dict[str, Callable[..., None]] = {
    "smoke_f02_vernacular_shadow_ledger": smoke_f02_vernacular_shadow_ledger,
    "smoke_f03_invent_obligation": smoke_f03_invent_obligation,
    "smoke_f04_air_fail_open_auto": smoke_f04_air_fail_open_auto,
    "smoke_f05_mix_overlay_authority": smoke_f05_mix_overlay_authority,
    "smoke_f06_refine_stage_retired": smoke_f06_refine_stage_retired,
    "smoke_f07_pending_read_rules": smoke_f07_pending_read_rules,
    "smoke_b02_delivery_residual_ledger": smoke_b02_delivery_residual_ledger,
    "smoke_b03_junction_family_budget": smoke_b03_junction_family_budget,
    "smoke_d05_manual_producer_pin": smoke_d05_manual_producer_pin,
    "smoke_g03_preclean_optional_copy": smoke_g03_preclean_optional_copy,
}


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

DONE_WHEN_CATALOG: dict[str, dict[str, Any]] = {
    "A-01": {
        "finding": "XC-HOLLOW / research thin marks done",
        "done_when": (
            "Shape/gap consumers refuse seed_complete on shape-core (W1–3) thin "
            "under defaults (no LLM/consumers_bind gate); W4–W8 thin at Pass1 OK"
        ),
        "proofs": [
            _pytest("tests/test_narrative_excellence.py::test_research_rollup_fail_open"),
            _pytest(
                "tests/test_narrative_excellence.py::"
                "test_a01_shape_core_complete_allows_shape_despite_late_waves_thin"
            ),
        ],
    },
    "A-02": {
        "finding": "SYN-SCHEMA-02 hollow [] validates complete",
        "done_when": "Empty primary arrays → incompleteness where content expected",
        "proofs": [
            _pytest(
                "tests/test_artifact_completeness.py::test_a02_hollow_primary_arrays_incompleteness"
            ),
        ],
    },
    "A-03": {
        "finding": "SYN-SHAPE-01 soft-gate pretends complete",
        "done_when": (
            "Default production config: soft-gate never stamps authoritative "
            "plan_status=complete; complete only from successful Shape LLM when "
            "shape.llm.enabled; hybrid bind requires complete; consumers_bind stays false"
        ),
        "proofs": [
            _pytest(
                "tests/test_a03_mastering_llm_cutover.py::"
                "test_a03_defaults_soft_gate_never_complete"
            ),
            _pytest(
                "tests/test_a03_mastering_llm_cutover.py::"
                "test_a03_hybrid_bind_requires_complete"
            ),
            _pytest(
                "tests/test_residual_cluster_hardening.py::"
                "test_a03_soft_gate_cannot_claim_complete_when_llm_on"
            ),
        ],
    },
    "A-04": {
        "finding": "SYN-DELIGHT-01 unattended waiver greens ship",
        "done_when": "waived_unattended alone ≠ delight-OK / ship_path_ready",
        "proofs": [
            _pytest(
                "tests/test_residual_cluster_hardening.py::"
                "test_a04_telemetry_waiver_not_music_delight_ok"
            ),
            _pytest(
                "tests/test_delivery_guardrails.py::"
                "test_a04_waived_unattended_alone_not_delivery_stable_or_ship"
            ),
        ],
    },
    "A-05": {
        "finding": "SYN-SHARED-01 shared writers leave stale stage_done",
        "done_when": "Rewrite restamps producer + reconciles co-producer done",
        "proofs": [
            _pytest(
                "tests/test_shared_path_authority.py::test_a05_reanchor_keeps_upstream_content_context_done"
            ),
            _pytest(
                "tests/test_shared_path_authority.py::test_a05_same_fingerprint_no_unmark_thrash"
            ),
        ],
    },
    "B-01": {
        "finding": "DEEP-RESPLIT wide clear_from wipe",
        "done_when": "seg_resplit_heal only; no delivery/EDL in clear window",
        "proofs": [
            _pytest(
                "tests/test_residual_cluster_cb.py::"
                "test_b01_seg_resplit_heal_profile_excludes_delivery"
            ),
            _pytest(
                "tests/test_residual_cluster_cb.py::"
                "test_b01_apply_seg_resplit_heal_unmarks_consumers_only"
            ),
        ],
    },
    "B-02": {
        "finding": "DEEP-FUSE unlimited fuse rounds",
        "done_when": "Config 0 → finite defaults; hard caps",
        "proofs": [
            _pytest(
                "tests/test_residual_cluster_hardening.py::"
                "test_b02_fuse_zero_config_resolves_to_finite_defaults"
            ),
            _inline("smoke_b02_delivery_residual_ledger"),
            _pytest(
                "tests/test_residual_six_gaps.py::"
                "test_b02_fuse_oscillation_residual_blocks_ship"
            ),
            _pytest(
                "tests/test_residual_wave9.py::"
                "test_b02_ssot_ledger_blocks_ship_pmq_and_publishability"
            ),
            _pytest(
                "tests/test_residual_wave9.py::"
                "test_b02_ssot_junction_findings_alone_block_via_view"
            ),
        ],
    },
    "B-03": {
        "finding": "DEEP-JUNCTION remaster↔hitch↔fuse ping-pong",
        "done_when": "One FAMILY_JUNCTION budget; no osc re-arm",
        "proofs": [
            _inline("smoke_b03_junction_family_budget"),
            _pytest(
                "tests/test_anti_footgun_hardening.py::"
                "test_junction_budget_exhaust_pins_not_soft_pass"
            ),
            _pytest(
                "tests/test_residual_six_gaps.py::"
                "test_b03_junction_family_in_halt_and_classify"
            ),
        ],
    },
    "B-04": {
        "finding": "XC-IDENT identical×3 miss",
        "done_when": "Structural signature includes predicate; unified ledger",
        "proofs": [
            _pytest(
                "tests/test_residual_cluster_cb.py::"
                "test_b04_structural_failure_signature_includes_predicate"
            ),
        ],
    },
    "B-05": {
        "finding": "DEEP-HITCH nuclear clear mid-delivery",
        "done_when": "Hitch profiles forbid late edl/mix/mmaudio archive",
        "proofs": [
            _pytest(
                "tests/test_residual_cluster_cb.py::"
                "test_b05_hitch_profiles_forbid_late_delivery"
            ),
        ],
    },
    "B-06": {
        "finding": "XC-INV heal vs structural disagree",
        "done_when": "All heal clears via profiles; unknown profile errors",
        "proofs": [
            _pytest(
                "tests/test_residual_cluster_hardening.py::test_w0_unknown_profile_raises"
            ),
            _pytest(
                "tests/test_execution_invalidation_profiles.py::"
                "test_unknown_profile_raises"
            ),
        ],
    },
    "B-07": {
        "finding": "XC-REMUTATE-02 story → mix-only dead end",
        "done_when": "Axis→producer law; recommendability maps to other dims",
        "proofs": [
            _pytest(
                "tests/test_residual_cluster_cb.py::"
                "test_b07_recommendability_maps_to_other_failing_dim"
            ),
            _pytest(
                "tests/test_residual_cluster_cb.py::"
                "test_b07_apply_uses_bounded_delight_axis"
            ),
        ],
    },
    "C-01": {
        "finding": "DEEP-VO-01 G1↔synth circular chase",
        "done_when": "Owner table drives stability / incompleteness / resume",
        "proofs": [
            _pytest(
                "tests/test_residual_cluster_cb.py::"
                "test_c01_vo_line_owners_and_resume_stick_synth"
            ),
        ],
    },
    "C-02": {
        "finding": "DEEP-VO-FIN finalize before synth",
        "done_when": "Finalize after synth; refuse mark_done without vo_bridge WAVs",
        "proofs": [
            _pytest(
                "tests/test_residual_cluster_cb.py::"
                "test_c02_finalize_after_vo_synthesize_in_delivery_order"
            ),
            _pytest(
                "tests/test_residual_cluster_cb.py::"
                "test_c02_vo_finalize_refuses_mark_done_when_vo_bridge_missing_wav"
            ),
        ],
    },
    "C-03": {
        "finding": "XC-SEED-01 G1 exception → rewind True",
        "done_when": "Sealed + no VO evidence → rewind False",
        "proofs": [
            _pytest(
                "tests/test_delivery_thrash_hardening.py::"
                "test_may_rewind_c03_sealed_exception_no_evidence_refuses"
            ),
        ],
    },
    "C-04": {
        "finding": "GATE-G1-01 skip vs seat floor fight",
        "done_when": "Sticky XOR: skip ⇒ hosted framing floor waived",
        "proofs": [
            _pytest(
                "tests/test_residual_cluster_cb.py::"
                "test_c04_g1_skip_waives_hosted_framing_floor"
            ),
        ],
    },
    "C-05": {
        "finding": "layup DEPTH conductor advances on thin layup",
        "done_when": "Synth blocked unless seed_stage_complete(layup) with coverage floors",
        "proofs": [
            _pytest(
                "tests/test_delivery_guardrails.py::"
                "test_vo_synth_blocked_when_layup_seed_incomplete_despite_file"
            ),
        ],
    },
    "D-01": {
        "finding": "SYN-MODE Partial copy only G0+S3 lie",
        "done_when": "Must-act SSOT equals Partial waits (G0 + g_publish)",
        "proofs": [
            _vitest("frontend/src/utils/partialAcceleratedGuard.test.ts"),
            _pytest(
                "tests/test_partial_auto_mode.py::"
                "test_automation_driver_run_includes_partial_and_full"
            ),
        ],
    },
    "D-02": {
        "finding": "SYN-GUI-01 POST + advance race",
        "done_when": "Partial: POST+refresh only; Manual keeps advance",
        "proofs": [
            _vitest("frontend/src/utils/gateAdvance.test.ts"),
            _vitest("frontend/src/utils/partialAcceleratedGuard.test.ts"),
        ],
    },
    "D-03": {
        "finding": "SYN-GUI-02 unguarded mutators",
        "done_when": "Mutating gate paths guard with shouldBlockOperatorActionsForJob",
        "proofs": [
            _vitest("frontend/src/utils/gateAdvance.test.ts"),
            _vitest("frontend/src/utils/partialAcceleratedGuard.test.ts"),
        ],
    },
    "D-04": {
        "finding": "GUI-START dual driver / wrong mode",
        "done_when": "Cross-run conflict 409; same-run attach OK",
        "proofs": [
            _pytest(
                "tests/test_full_auto_launch_api.py::"
                "test_create_run_refuses_when_driver_already_running"
            ),
        ],
    },
    "D-05": {
        "finding": "GUI-PIPE run consumer while producer incomplete",
        "done_when": "Execute returns pin; premature_cap safe pin",
        "proofs": [
            _inline("smoke_d05_manual_producer_pin"),
            _pytest(
                "tests/test_delivery_guardrails.py::test_premature_cap_pins_not_advances"
            ),
        ],
    },
    "D-06": {
        "finding": "GATE-G0/GPUB mode consent honesty",
        "done_when": "Partial never auto-G0/S3 without consent",
        "proofs": [
            _pytest(
                "tests/test_partial_auto_mode.py::test_complete_g0_skipped_when_partial"
            ),
            _pytest(
                "tests/test_partial_auto_mode.py::"
                "test_partial_never_syncs_s3_without_g_publish_consent"
            ),
        ],
    },
    "D-07": {
        "finding": "SYN-GFR posture ignored; sticky lie",
        "done_when": "Recommended framing honors LLM no/sparse; sticky Yes/No",
        "proofs": [
            _pytest(
                "tests/test_partial_auto_mode.py::"
                "test_recommended_framing_honors_llm_no_and_sparse"
            ),
        ],
    },
    "D-08": {
        "finding": "XC-PREMATURE exception → consumer resume",
        "done_when": "Exception → last safe pin; never consumer fallthrough",
        "proofs": [
            _pytest(
                "tests/test_delivery_guardrails.py::"
                "test_premature_cap_heal_exception_never_falls_to_consumer"
            ),
        ],
    },
    "E-01": {
        "finding": "SYN-PACK LLM sees stage_done stamps",
        "done_when": "LLM conductor view has zero denylist keys",
        "proofs": [
            _pytest(
                "tests/test_cluster_e_hardening.py::"
                "test_e01_llm_conductor_view_strips_denylist_keys"
            ),
        ],
    },
    "E-02": {
        "finding": "PSM-NO-PRIMARY missing STAGE_PRIMARY_IDS",
        "done_when": "Every LLM-bound schema stage has primary ID",
        "proofs": [
            _pytest(
                "tests/test_cluster_e_hardening.py::"
                "test_e02_llm_bound_schemas_subset_of_primary_ids"
            ),
        ],
    },
    "E-03": {
        "finding": "SYN-RETRY feel ladder attempts=3",
        "done_when": "Junction feel ≤ v2.llm_max_attempts (2)",
        "proofs": [
            _pytest(
                "tests/test_cluster_e_hardening.py::"
                "test_e03_feel_ladder_respects_llm_max_attempts"
            ),
        ],
    },
    "E-04": {
        "finding": "CFG-01 e2e_soft softens quality",
        "done_when": "Critical residual soften only if quality waivers on",
        "proofs": [
            _pytest(
                "tests/test_cluster_e_hardening.py::"
                "test_e04_soft_vs_quality_waivers_matrix"
            ),
        ],
    },
    "E-05": {
        "finding": "H010-DISPATCH illegal next burns budget",
        "done_when": "Illegal seed → pin before LLM burn",
        "proofs": [
            _pytest(
                "tests/test_cluster_e_hardening.py::"
                "test_e05_dispatch_seed_pin_before_stage_burn"
            ),
        ],
    },
    "F-01": {
        "finding": "DEEP-CUTS eval exception writes coarse boundaries",
        "done_when": "quality_eval_failed skips boundary bind",
        "proofs": [
            _pytest(
                "tests/test_residual_wave9.py::"
                "test_f01_quality_eval_exception_skips_boundary_write"
            ),
        ],
    },
    "F-02": {
        "finding": "DEEP-VERNACULAR unstaged / silent must_keep drop",
        "done_when": "stage_key writes; must_keep drop → ledger even in shadow",
        "proofs": [
            _inline("smoke_f02_vernacular_shadow_ledger"),
            _pytest(
                "tests/test_residual_six_gaps.py::test_f02_shadow_must_keep_drop_ledgers"
            ),
            _pytest(
                "tests/test_residual_six_gaps.py::test_f02_shadow_must_keep_block_restores"
            ),
        ],
    },
    "F-03": {
        "finding": "DEEP-SONIC empty palettes → heuristic policy",
        "done_when": "Deferred needs invent obligation; unpaid ⇒ incomplete",
        "proofs": [
            _inline("smoke_f03_invent_obligation"),
            _pytest(
                "tests/test_residual_six_gaps.py::"
                "test_f03_invent_gate_blocks_heuristic_beds"
            ),
        ],
    },
    "F-04": {
        "finding": "DEEP-AIR fail-open / hollow seats progress",
        "done_when": "Full-auto: fail_open false under auto; hollow seats incompleteness",
        "proofs": [
            _pytest(
                "tests/test_residual_wave9.py::"
                "test_f04_air_cfg_fail_open_false_under_auto_env"
            ),
            _pytest(
                "tests/test_residual_wave9.py::"
                "test_f04_compose_raises_under_auto_does_not_swallow"
            ),
            _pytest(
                "tests/test_residual_wave9.py::"
                "test_f04_hollow_seats_incompleteness_blocks_seed"
            ),
            _inline("smoke_f04_air_fail_open_auto"),
        ],
    },
    "F-05": {
        "finding": "DEEP-MIX overlay authority + lying stats",
        "done_when": "overlay_authority stamp + truthful missing_assets",
        "proofs": [
            _pytest(
                "tests/test_residual_wave9.py::"
                "test_f05_sdp_missing_wav_uses_placeholders_not_legacy"
            ),
            _pytest(
                "tests/test_residual_wave9.py::"
                "test_f05_sdp_plan_empty_realized_no_legacy_invent"
            ),
            _pytest(
                "tests/test_residual_wave9.py::"
                "test_f05_no_sdp_may_use_legacy_fallback"
            ),
            _inline("smoke_f05_mix_overlay_authority"),
        ],
    },
    "F-06": {
        "finding": "DEEP-REFINE no-op refine looks real",
        "done_when": "Not dispatchable; StageRetired for ghost refine",
        "proofs": [
            _inline("smoke_f06_refine_stage_retired"),
            _pytest("tests/test_f06_retired_refine_ghosts.py::test_f06_retired_set_membership"),
            _pytest(
                "tests/test_f06_retired_refine_ghosts.py::"
                "test_f06_run_ranking_refine_raises_stage_retired"
            ),
            _pytest(
                "tests/test_f06_retired_refine_ghosts.py::"
                "test_f06_run_single_stage_ranking_refine_raises"
            ),
        ],
    },
    "F-07": {
        "finding": "XC-STAGING pending shadows consumers",
        "done_when": "Committed when done; pending only same-producer write-approval",
        "proofs": [
            _inline("smoke_f07_pending_read_rules"),
            _pytest(
                "tests/test_write_staging.py::"
                "test_read_path_ignores_other_stage_incomplete_pending"
            ),
        ],
    },
    "G-01": {
        "finding": "GUI-BANNER banner ≠ waiting gate",
        "done_when": "Kind from structured gate/blocking; visible while gate",
        "proofs": [
            _vitest("frontend/src/utils/resolveReviewGate.test.ts"),
        ],
    },
    "G-02": {
        "finding": "GUI-QC QC overstates ship",
        "done_when": "blocksShip iff !publish_allowed; display states honest",
        "proofs": [
            _vitest("frontend/src/utils/qcSummaryState.test.ts"),
        ],
    },
    "G-03": {
        "finding": "OFFER-* preclean Required; optimizer lie",
        "done_when": "Optional copy + Skip; optimizer shows auto_started",
        "proofs": [
            _inline("smoke_g03_preclean_optional_copy"),
            _vitest("frontend/src/utils/preclean.test.ts"),
        ],
    },
}


DILUTION_WATCH: list[dict[str, Any]] = [
    {
        "id": "DW-01",
        "parent": "A-01",
        "watch": (
            "Shape/gap seed_complete refuses shape-core (W1–3) thin under defaults; "
            "not global majority thin; not LLM-flag gated"
        ),
    },
    {
        "id": "DW-02",
        "parent": "A-03",
        "watch": (
            "Soft-gate never stamps authoritative complete under defaults; "
            "hybrid bind requires plan_status=complete"
        ),
    },
    {
        "id": "DW-03",
        "parent": "A-04",
        "watch": "waived_unattended ≠ delight-OK unless quality_waived or seed_complete",
    },
    {
        "id": "DW-04",
        "parent": "C-05",
        "watch": "seed_stage_complete(layup) includes coverage floors, not file-exists",
    },
    {
        "id": "DW-05",
        "parent": "D-01",
        "watch": "Must-act SSOT must equal driver wait set (no third reality)",
    },
    {
        "id": "DW-06",
        "parent": "F-02",
        "watch": "Staging alone ≠ closed: shadow must_keep drop needs ledger or block",
    },
    {
        "id": "DW-07",
        "parent": "F-03",
        "watch": "soundscape_policy/plan invent must check invent obligation",
    },
    {
        "id": "DW-08",
        "parent": "B-02",
        "watch": "Residual ledger visible to ship/junction consumers (B-02/B-03)",
        "also_parents": ["B-03"],
    },
    {
        "id": "DW-09",
        "parent": "B-02",
        "watch": (
            "Residual SSOT: ship ≡ PMQ ≡ publishability ≡ delight on critical "
            "residual count (critical_residual_view)"
        ),
        "also_parents": ["F-01", "F-04", "F-05"],
    },
]


def catalog_surfaces() -> dict[str, str]:
    """Optional stage hint for RC-DW cells (best-effort)."""
    return {
        "A-01": "mastering_research_rollup",
        "A-02": "content_context",
        "A-03": "mastering_plan_synthesize",
        "A-04": "listen_delight_audit",
        "A-05": "content_brief_reanchor",
        "B-01": "boundary_topic_resplit",
        "B-02": "connector_fuse_pass",
        "B-03": "junction_snip_qa",
        "B-04": "edl",
        "B-05": "chapter_close_hitch",
        "B-06": "boundary_topic_resplit",
        "B-07": "listen_delight_audit",
        "C-01": "vo_synthesize",
        "C-02": "sound_design_vo_finalize",
        "C-03": "vo_synthesize",
        "C-04": "vo_synthesize",
        "C-05": "nugget_layup_compose",
        "D-01": "transcript_review_build",
        "D-02": "framing_posture_decide",
        "D-03": "listen_delight_audit",
        "D-04": "podcast_publish",
        "D-05": "edl",
        "D-06": "transcript_review_build",
        "D-07": "framing_posture_decide",
        "D-08": "master_finalize",
        "E-01": "speaker_roles",
        "E-02": "speaker_roles",
        "E-03": "junction_snip_qa",
        "E-04": "junction_snip_qa",
        "E-05": "vo_synthesize",
        "F-01": "ideal_cuts_materialize",
        "F-02": "vernacular_segment_sanitize",
        "F-03": "soundscape_policy_build",
        "F-04": "air_script_compose",
        "F-05": "mix",
        "F-06": "sfx_prompt_craft",
        "F-07": "edl",
        "G-01": "transcript_review_build",
        "G-02": "listen_delight_audit",
        "G-03": "audio_preclean",
    }


def run_inline_smoke(name: str, ctx: Any = None) -> None:
    fn = INLINE_SMOKES.get(name)
    if fn is None:
        raise KeyError(f"unknown inline smoke: {name}")
    fn(ctx)


def run_all_inline_smokes(ctx: Any = None) -> list[str]:
    ran: list[str] = []
    for name in sorted(INLINE_SMOKES):
        INLINE_SMOKES[name](ctx)
        ran.append(name)
    return ran


def inline_names_for(catalog_id: str) -> list[str]:
    row = DONE_WHEN_CATALOG.get(catalog_id) or {}
    return [
        str(p["nodeid"])
        for p in (row.get("proofs") or [])
        if p.get("kind") == "inline" and p.get("nodeid")
    ]


def proof_notes(catalog_id: str) -> list[str]:
    row = DONE_WHEN_CATALOG.get(catalog_id) or {}
    notes: list[str] = []
    for p in row.get("proofs") or []:
        kind = p.get("kind")
        if kind == "pytest":
            notes.append(f"pytest:{p.get('nodeid')}")
        elif kind == "vitest":
            notes.append(f"vitest:{p.get('path')}")
        elif kind == "inline":
            notes.append(f"inline:{p.get('nodeid')}")
    return notes
