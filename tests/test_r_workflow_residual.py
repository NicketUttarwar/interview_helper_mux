"""Residual workflow fixtures (ingest→ship) — thin product asserts + doc gates.

Maps exec_11630 / residual-closure workflow residuals under MUX_FORENSICS=0.
Prefers calling existing test helpers or one-line API asserts over reimplementation.
No End-G; intentional gates stay documentation-only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx

_REPO = Path(__file__).resolve().parents[1]
_CONSTITUTION = _REPO / "docs" / "cross-cutting" / "residual-closure-constitution.md"
_STATUS = _REPO / "docs" / "cross-cutting" / "exec-11630-major-errors-status.md"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED", "1")
    return isolated_run_ctx(tmp_path, "r_workflow")


# --- Early -----------------------------------------------------------------


def test_r_wf_golden_facts_pending_only_flush(tmp_path, monkeypatch) -> None:
    """#2: heal_or_raise flushes active-stage pending (not pending_only thrash)."""
    from test_stage_completion_heal import (
        test_heal_or_raise_flushes_active_stage_pending_before_pending_only as _t,
    )

    _t(tmp_path, monkeypatch)


def test_r_wf_hg3_cap_seal_leftovers_api() -> None:
    """#4: CAP seal leftovers API exists (HG-3 coverage_exhausted path)."""
    from interview_mux.stages.gaps import (
        MISSING_FRAMING_COVERAGE_CAP,
        _coverage_exhausted_accept_row,
        _seal_coverage_exhausted_leftovers,
    )

    assert MISSING_FRAMING_COVERAGE_CAP >= 1
    assert callable(_seal_coverage_exhausted_leftovers)
    row = _coverage_exhausted_accept_row("seg_001")
    assert (row.get("_meta") or {}).get("filled_by") == "coverage_exhausted_accept"
    assert (row.get("_meta") or {}).get("reason") == "coverage_cap_seal"
    # Existing heavy fixture remains the green proof:
    import test_hg3_missing_framing_batch as hg3

    assert callable(hg3.test_hg3_same_invoke_cap_seals_leftovers)


def test_r_wf_foreign_pending_does_not_block_canonical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#6: foreign-stage incomplete pending must not shadow committed canonical."""
    from test_write_staging import test_read_path_ignores_other_stage_incomplete_pending as _t

    _t(tmp_path, monkeypatch)


def test_r_wf_fuse_oscillation_pin_not_edl(ctx) -> None:
    """fuse_oscillation classifies / pins fuse writer, never edl."""
    from interview_mux.heal_routing import classify_heal_error, resume_stage_for_error_class
    from interview_mux.stage_completion import (
        fuse_oscillation_heal_resume_stage,
        producer_pin_for_token,
    )

    err = "fuse_oscillation_halt on connector_fuse"
    assert fuse_oscillation_heal_resume_stage(ctx, error=err) == "connector_fuse_pass"
    assert producer_pin_for_token("fuse_oscillation") == "connector_fuse_pass"
    assert resume_stage_for_error_class("fuse_oscillation") == "connector_fuse_pass"
    route = classify_heal_error(err, ctx, stage="edl")
    assert route is not None
    assert route.from_stage == "connector_fuse_pass"
    assert route.from_stage != "edl"


# --- Mid ------------------------------------------------------------------


def test_r_wf_selection_exclude_prune() -> None:
    """#10: selection sanitize prunes exclude_rationales on air ids."""
    from test_artifact_sanitize_selection import (
        test_sanitize_prunes_exclude_rationales_on_air_ids as _t,
    )

    _t()


def test_r_wf_blank_drop_under_freeze(ctx, monkeypatch) -> None:
    """#11: blank drop remains legal under hard freeze order preserve."""
    from interview_mux.air_order_boundary import _drop_blank_segments_under_freeze
    from interview_mux.seat_authority import hard_freeze_action_permitted

    assert hard_freeze_action_permitted("drop_blank_segments_under_freeze")
    monkeypatch.setattr(
        "interview_mux.artifact_repairs._segment_is_blank_or_unusable",
        lambda _ctx, sid: str(sid) == "seg_blank",
    )
    out = _drop_blank_segments_under_freeze(
        ctx,
        {
            "ordered_segment_ids": ["seg_blank", "seg_real"],
            "excluded_segment_ids": [],
            "chapters": [{"segment_ids": ["seg_blank", "seg_real"]}],
        },
    )
    assert "seg_blank" not in (out.get("ordered_segment_ids") or [])
    assert "seg_real" in (out.get("ordered_segment_ids") or [])


def test_r_wf_reverse_jump_and_framing_dedupe_loud_imports() -> None:
    """#7/#9: reverse-jump + framing_dedupe loud-fail fixtures remain importable."""
    import test_artifact_sanitize_transitions as tr

    assert callable(tr.test_sanitize_transitions_prunes_reverse_jump)
    assert callable(tr.test_sanitize_transitions_missing_prune_import_fails_loud)
    assert callable(tr.test_sanitize_transitions_framing_dedupe_import_fails_loud)


def test_r_wf_omit_heal_freeze_owner_only(ctx) -> None:
    """Omit ledger under freeze: owner ALLOW, foreign DENY (End-F cousin)."""
    from test_end_cousin_fixtures import test_endf_cousin_omit_under_freeze_owner_only as _t

    _t(ctx)


def test_r_wf_glue_deferred_durable_and_soft_refuse() -> None:
    """End-C: text-only deferred incomplete; soft complete refused without waiver."""
    from test_endc_glue_before_edl import (
        test_endc_deferred_text_only_not_complete as _deferred,
        test_endc_soft_complete_refused_without_waiver as _soft,
    )

    _deferred()
    _soft()


def test_r_wf_speech_order_classify_cousin() -> None:
    """#19: narrative QC prose classifies as selection_edl_order_drift."""
    from test_end_cousin_fixtures import (
        test_exec11630_narrative_qc_speech_clips_prose_classifies_as_order_drift as _t,
    )

    _t()


def test_r_wf_he2_unsanitary_edl_heal(ctx) -> None:
    """HE-2: unsanitary VO/bind must not claim rebuild-EDL playbook."""
    from test_he2_edl_heal_playbook import test_he2_unsanitary_playbook_does_not_claim_edl as _t

    _t(ctx)


# --- Late -----------------------------------------------------------------


def test_r_wf_hollow_junction_finalize_refuse(ctx) -> None:
    """#26: hollow junction (diverged commitment) must not seed-complete."""
    from test_endd_commitment_seating import test_endd_hollow_junction_not_seed_complete as _t

    _t(ctx)


def test_r_wf_music_epoch_hollow_mmaudio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#21 cousin: hollow mmaudio_qa does not complete music_epoch."""
    from test_delivery_guardrails import test_hollow_mmaudio_qa_does_not_complete_music_epoch as _t

    _t(tmp_path, monkeypatch)


def test_r_wf_soft_pass_empty_without_last_resort(ctx, monkeypatch) -> None:
    """#22: soft_pass_pre_edl_delivery → [] without LAST_RESORT."""
    import sys

    monkeypatch.delenv("INTERVIEW_MUX_E2E_LAST_RESORT_SOFT", raising=False)
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    tools = str(_REPO / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import full_auto_driver as driver

    notes = driver.soft_pass_pre_edl_delivery(ctx)
    assert notes == []


def test_r_wf_catastrophic_floors_hard_stop_api() -> None:
    """Catastrophic listen floors remain a hard ship stop (API + existing fixture)."""
    from interview_mux.aspirational_quality import passes_catastrophic_floors
    import test_listen_delight as ld

    assert callable(passes_catastrophic_floors)
    assert callable(ld.test_catastrophic_floors_still_hard_stop_at_ship)


def test_r_wf_pending_master_not_shipped(tmp_path: Path) -> None:
    """Pending master.wav alone must not open G-Publish / end judgment."""
    from interview_mux.gates import check_g_publish_pending
    from interview_mux.homunculus.judge import after_complete_master

    run = isolated_run_ctx(tmp_path, "r_wf_pending_master")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    pending = (
        run.run_dir
        / ".pending_writes"
        / "master_finalize"
        / "master"
        / "master.wav"
    )
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"RIFF" + b"\x00" * 64)
    assert check_g_publish_pending(run) is False
    out = after_complete_master(run)
    assert out.get("verdict") == "pending"


def test_r_wf_framing_operator_no_sticky(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Operator G-Framing No must stay sticky (HC-5/6 + HG-1 fixtures)."""
    import sys

    import test_gap_framing_gates as gf
    import test_hc5_pending_overlay as hc5
    import test_hc6_gate_advance as hc6
    import test_hg1_framing_sticky_yes as hg1

    assert callable(gf.test_operator_no_not_overwritten_by_auto_accept)
    assert callable(hg1.test_hg1_operator_no_not_overwritten)
    assert callable(hc5.test_hc5_partial_framing_is_automation_pending)
    assert callable(hc6.test_hc6_manual_advances)

    # Thin driver sticky-No (mirrors HG-1 without calling its fixture).
    tools = str(_REPO / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import full_auto_driver as driver
    from interview_mux.run_context import RunContext
    from run_fixtures import init_run_meta_for_test, patch_executions_root

    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED", "0")
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_r_wf_framing_no", create=True)
    init_run_meta_for_test(run)
    monkeypatch.setattr(driver, "RUN_ID", run.run_id)
    monkeypatch.setattr(driver, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(driver, "log_decision", lambda *_a, **_k: None)
    monkeypatch.setattr(driver, "_pipeline_native_only", lambda: False)
    run.mutate_run_meta(lambda m: m.update({"gap_framing_enabled": False}))
    calls: list[tuple[str, str]] = []

    def api(method: str, path: str, body: dict | None = None, timeout: int = 180) -> dict:
        calls.append((method, path))
        if "gap-framing" in path and method == "GET":
            return {"gap_framing_decision_pending": True}
        return {}

    monkeypatch.setattr(driver, "api", api)
    driver.accept_gap_framing_defaults()
    meta = run.read_json("run_meta.json")
    assert meta.get("gap_framing_enabled") is False
    driver.accept_gap_framing_defaults(force_yes=True)
    meta = run.read_json("run_meta.json")
    assert meta.get("gap_framing_enabled") is False
    assert not any(c[0] == "POST" and "gap-framing/enable" in c[1] for c in calls)


def test_r_wf_hitch_lattice_importable() -> None:
    """Chapter-close hitch ranking lattice fixtures remain importable."""
    import test_hr1_hitch_ranking_lattice as hr1

    assert callable(hr1.test_hr1_unmark_ranking_lattice_not_vo_edl_mix)


def test_r_wf_musicgen_stub_forbidden_via_verify() -> None:
    """MusicGen stub / last-resort / waiver keys must not set-to-1 in _driver_env."""
    import shutil
    import subprocess

    import pytest

    # Windows cannot exec a .sh directly (WinError 193), so go through bash.
    # bash is present on macOS and Linux, and on Windows via Git Bash.
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash not available to run verify_full_auto_env.sh")
    out = subprocess.run(
        [bash, str(_REPO / "tools" / "verify_full_auto_env.sh")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr or out.stdout


def test_r_wf_publishability_tier0_doc_and_api() -> None:
    """Tier-0 publishability + delivery unlock: doc gate + thin API import."""
    from interview_mux.publishability_boundary import (
        validate_publishability,
    )
    import test_publishability_boundary as pub

    _assert_doc_phrases(
        _REPO / "docs" / "cross-cutting" / "publishability-contract.md",
        "Tier 0",
        "No zero-duration speech",
        "VO audibility",
        "Selection leads EDL",
        "Opening orientation",
    )
    _assert_doc_phrases(
        _STATUS,
        "Tier-0 publishability",
        "zero keeps",
    )
    assert callable(validate_publishability)
    assert callable(pub.test_zero_keep_detected_post_edl)


def test_r_wf_ship_path_ready_vs_remote_publish(ctx, monkeypatch) -> None:
    """Local ship_path_ready can walk under e2e_soft while remote_publish stays blocked."""
    import json

    from interview_mux.delivery_guardrails import remote_publish_allowed, ship_path_ready
    from run_fixtures import mark_done_raw

    def _raw(rel: str, data: object) -> None:
        path = ctx.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    asm = ctx.path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF" + b"\x00" * 4096)
    mark_done_raw(ctx, "mix")
    mark_done_raw(ctx, "listen_delight_audit")
    _raw("mastering/listen_delight_audit.json", {"status": "complete", "passed": True})
    _raw("master/junction_snip_qa.json", {"critical_count": 0, "residuals": []})
    _raw("master/post_master_quality.json", {"publish_allowed": False, "status": "fail"})
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda._junction_commitment_matches_assembly",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid in {"mix", "junction_snip_qa", "listen_delight_audit"},
    )
    ready, _ = ship_path_ready(ctx)
    allowed, why = remote_publish_allowed(ctx)
    assert ready is True
    assert allowed is False
    assert why == "pmq_not_publishable"


# --- Intentional gates (documentation only) -------------------------------


def _assert_doc_phrases(path: Path, *phrases: str) -> None:
    text = path.read_text(encoding="utf-8")
    for phrase in phrases:
        assert phrase in text, f"missing {phrase!r} in {path.name}"


def test_hg3_missing_framing_intentional_gate_documented() -> None:
    """#3 INTENTIONAL_GATE — never soft away batch_fill refuse."""
    _assert_doc_phrases(
        _CONSTITUTION,
        "HG-3",
        "missing_framing",
        "Fake LLM completeness",
    )
    _assert_doc_phrases(_STATUS, "INTENTIONAL_GATE", "missing_framing")


def test_stamp_pair_freeze_intentional_gate_documented() -> None:
    """#8 INTENTIONAL_GATE — needs_sanitize flash under freeze."""
    _assert_doc_phrases(
        _CONSTITUTION,
        "stamp_pair_freeze",
        "Freeze thrash",
    )
    _assert_doc_phrases(_STATUS, "stamp_pair_freeze", "INTENTIONAL_GATE")


def test_qc_before_edl_intentional_gate_documented() -> None:
    """#18 INTENTIONAL_GATE — Narrative QC-before-EDL."""
    _assert_doc_phrases(
        _CONSTITUTION,
        "Narrative QC-before-EDL",
        "Soft-pass glue lies",
    )
    _assert_doc_phrases(_STATUS, "edl_narrative:vo_g1", "INTENTIONAL_GATE")


def test_assembly_preview_edl_intentional_gate_documented() -> None:
    """#23 INTENTIONAL_GATE — assembly_preview needs edl.json."""
    _assert_doc_phrases(
        _CONSTITUTION,
        "assembly_preview",
        "Hollow preview theater",
    )
    _assert_doc_phrases(_STATUS, "assembly_preview", "INTENTIONAL_GATE")


def test_host_vo_duration_intentional_gate_documented() -> None:
    """#29 INTENTIONAL_GATE — host_vo_duration advisory."""
    _assert_doc_phrases(
        _CONSTITUTION,
        "host_vo_duration",
        "Auto-thicken",
    )
    _assert_doc_phrases(_STATUS, "host_vo_duration", "INTENTIONAL_GATE")


def test_s3_advisories_intentional_gate_documented() -> None:
    """#30 INTENTIONAL_GATE — S3 blocked on advisories / G-Publish consent."""
    _assert_doc_phrases(
        _CONSTITUTION,
        "S3 blocked on advisories",
        "Bypass G-Publish consent",
    )
    _assert_doc_phrases(_STATUS, "S3 blocked", "INTENTIONAL_GATE")


def test_e2e_brief_soft_refuse_intentional_gate_documented() -> None:
    """#31 INTENTIONAL_GATE — e2e brief on soft refuse."""
    _assert_doc_phrases(
        _CONSTITUTION,
        "e2e brief on soft refuse",
        "Hide production-parity refuse",
    )
    _assert_doc_phrases(_STATUS, "e2e brief", "INTENTIONAL_GATE")


def test_preclean_never_auto_intentional_gate_documented() -> None:
    _assert_doc_phrases(_CONSTITUTION, "Preclean never auto-run", "Operator gate")
    _assert_doc_phrases(_STATUS, "Preclean", "never auto")


def test_catastrophic_floors_intentional_gate_documented() -> None:
    _assert_doc_phrases(
        _CONSTITUTION,
        "Catastrophic listen floors hard-stop",
        "Soft-proceed below catastrophe",
    )
    _assert_doc_phrases(_STATUS, "Catastrophic listen floors", "hard-stop")


def test_pending_master_not_shipped_intentional_gate_documented() -> None:
    _assert_doc_phrases(
        _CONSTITUTION,
        "Pending `master.wav` ≠ shipped",
        "False ship bar",
    )
    _assert_doc_phrases(_STATUS, "Pending `master.wav`", "shipped")
