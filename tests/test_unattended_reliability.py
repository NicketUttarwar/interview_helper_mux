"""Unattended Full-auto reliability: report, identical-failure halt, repairs, catalog."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.e2e_soft import e2e_quality_waivers_enabled, e2e_soft_enabled
from interview_mux.execution_report import (
    REPORT_MD_REL,
    build_execution_report,
    write_execution_report,
)
from interview_mux.identical_failures import (
    clear_all_halts,
    clear_edl_repair_halts,
    clear_halts_matching,
    failure_signature,
    forensics_mode,
    halt_after,
    is_halted,
    normalize_reason,
    record_identical_failure,
    sync_identical_halts_with_product,
    upsert_fail_key,
)
from interview_mux.opening_adjacency_repair import (
    drop_orphan_opening_vo_when_native_orients,
    suppress_opening_layup_when_orientation_owns_slot,
)
from interview_mux.stage_families import source_profile_recipe
from interview_mux.unattended_resume import resume_producer_for_block

from run_fixtures import isolated_run_ctx, mark_done_raw


def test_e2e_quality_waivers_off_even_when_soft(monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    monkeypatch.delenv("INTERVIEW_MUX_E2E_QUALITY_WAIVERS", raising=False)
    assert e2e_soft_enabled() is True
    assert e2e_quality_waivers_enabled() is False
    monkeypatch.setenv("INTERVIEW_MUX_E2E_QUALITY_WAIVERS", "1")
    assert e2e_quality_waivers_enabled() is True


def test_identical_failure_collapses_naked_seam_pair_ids():
    a = "assembly_ledger: 2 naked seam(s): seg_012 → seg_044 hitch missing"
    b = "assembly_ledger: 2 naked seam(s): seg_001 → seg_070 hitch missing"
    assert normalize_reason(a) == normalize_reason(b)
    assert "<pair>" in normalize_reason(a)
    assert failure_signature(failed_stage="edl", producer="master/assembly_ledger.json", reason=a) == (
        failure_signature(failed_stage="edl", producer="master/assembly_ledger.json", reason=b)
    )


def test_naked_seam_gate_halts_at_three(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_naked_seam_halt")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    last = None
    for i, pair in enumerate(("seg_001 → seg_002", "seg_010 → seg_011", "seg_020 → seg_021")):
        last = record_identical_failure(
            ctx,
            failed_stage="edl",
            producer="master/assembly_ledger.json",
            reason=f"naked seam(s): {pair}",
            resume_attempted="edl",
        )
    assert last is not None
    assert last["count"] == 3
    assert last["halt"] is True


def test_identical_failure_collapses_rotating_never_touch_seg_ids():
    a = "Nugget layup QC failed: never_touch_cta[seg_041]: lay-up reuses dropped CTA wording"
    b = "Nugget layup QC failed: never_touch_cta[seg_008]: lay-up reuses dropped CTA wording"
    assert normalize_reason(a) == normalize_reason(b)
    assert "[<seg>]" in normalize_reason(a)
    assert failure_signature(failed_stage="nugget_layup_compose", reason=a) == failure_signature(
        failed_stage="nugget_layup_compose", reason=b
    )


def test_identical_failure_halts_at_three(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_ident_halt")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    assert halt_after() >= 3
    last = None
    for _ in range(3):
        last = record_identical_failure(
            ctx,
            failed_stage="edl_narrative_audit",
            producer="understanding/gap_report.json",
            reason="opening orientation and opening layup both target seg_001",
        )
    assert last is not None
    assert last["count"] == 3
    assert last["halt"] is True
    stored = json.loads(
        (ctx.run_dir / "operator" / "identical_failures.json").read_text(encoding="utf-8")
    )
    assert stored["signatures"][last["signature"]]["count"] == 3


def test_clear_halts_matching_resets_g1_edl_signature(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_clear_g1_halt")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    last = None
    for _ in range(3):
        last = record_identical_failure(
            ctx,
            failed_stage="edl",
            reason="Stage 'edl' blocked — G1 VO pickup missing for: ['vo_layup_seg_009']",
        )
    assert last is not None
    assert last["halt"] is True
    n = clear_halts_matching(
        ctx,
        failed_stage="edl",
        reason_substr="g1 vo pickup missing",
        force=True,
    )
    assert n == 1
    stored = json.loads(
        (ctx.run_dir / "operator" / "identical_failures.json").read_text(encoding="utf-8")
    )
    row = stored["signatures"][last["signature"]]
    assert row["halt"] is False
    assert row["count"] == 0


def test_clear_edl_repair_halts_resets_edl_narrative_fail_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MUX_FORENSICS", raising=False)
    ctx = isolated_run_ctx(tmp_path, "exec_clear_edl_chain")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    upsert_fail_key(
        ctx,
        "edl_narrative:opening orientation",
        3,
        failed_stage="edl_narrative_audit",
        producer="understanding/gap_report.json",
    )
    sig = failure_signature(
        failed_stage="edl_narrative_audit",
        producer="understanding/gap_report.json",
        reason="chapter references segments missing from edl speech clips",
    )
    for _ in range(3):
        record_identical_failure(
            ctx,
            failed_stage="edl_narrative_audit",
            producer="understanding/gap_report.json",
            reason="chapter references segments missing from edl speech clips",
        )
    assert is_halted(ctx, sig)
    n = clear_edl_repair_halts(ctx)
    assert n >= 2
    assert not is_halted(ctx, sig)


def test_forensics_mode_suppresses_all_stage_halts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MUX_FORENSICS", "1")
    ctx = isolated_run_ctx(tmp_path, "exec_forensics_no_halt")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    for stage in ("edl_narrative_audit", "topic_coverage_audit", "nugget_layup_compose"):
        sig = failure_signature(
            failed_stage=stage,
            producer="understanding/gap_report.json",
            reason=f"blocked at {stage}",
        )
        for _ in range(3):
            record_identical_failure(
                ctx,
                failed_stage=stage,
                producer="understanding/gap_report.json",
                reason=f"blocked at {stage}",
            )
        assert forensics_mode() is True
        assert not is_halted(ctx, sig)


def test_clear_all_halts_resets_every_signature(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MUX_FORENSICS", raising=False)
    ctx = isolated_run_ctx(tmp_path, "exec_clear_all")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    sig_a = failure_signature(failed_stage="edl", reason="a")
    sig_b = failure_signature(failed_stage="topic_coverage_audit", reason="b")
    for _ in range(3):
        record_identical_failure(ctx, failed_stage="edl", reason="a")
        record_identical_failure(ctx, failed_stage="topic_coverage_audit", reason="b")
    assert is_halted(ctx, sig_a)
    assert is_halted(ctx, sig_b)
    from interview_mux.identical_failures import clear_all_halts

    n = clear_all_halts(ctx)
    assert n == 2
    assert not is_halted(ctx, sig_a)
    assert not is_halted(ctx, sig_b)


def test_sync_identical_halts_with_product_on_forensics_restart(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MUX_FORENSICS", "1")
    ctx = isolated_run_ctx(tmp_path, "exec_sync_forensics")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    sig = failure_signature(
        failed_stage="edl",
        producer="master/assembly_ledger.json",
        reason="naked seam(s): seg_001 → seg_002",
    )
    for _ in range(3):
        record_identical_failure(
            ctx,
            failed_stage="edl",
            producer="master/assembly_ledger.json",
            reason="naked seam(s): seg_001 → seg_002",
        )
    assert is_halted(ctx, sig) is False  # forensics suppresses is_halted
    stored = json.loads(
        (ctx.run_dir / "operator" / "identical_failures.json").read_text(encoding="utf-8")
    )
    assert stored["signatures"][sig]["halt"] is True
    result = sync_identical_halts_with_product(ctx, forensics=True)
    assert result["cleared"] >= 1
    assert result["scope"] == "all"
    stored = json.loads(
        (ctx.run_dir / "operator" / "identical_failures.json").read_text(encoding="utf-8")
    )
    assert stored["signatures"][sig]["halt"] is False
    assert stored["signatures"][sig]["count"] == 0
    meta = json.loads((ctx.run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta.get("identical_halts_product_fingerprint")


def test_upsert_fail_key_survives_absolute_counts(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_ident_upsert")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    row = upsert_fail_key(ctx, "partial_artifact:content_brief.json", 2, failed_stage="sonic_context_build")
    assert row["count"] == 2
    assert row["halt"] is False
    row = upsert_fail_key(ctx, "partial_artifact:content_brief.json", 3, failed_stage="sonic_context_build")
    assert row["halt"] is True


def test_execution_report_written_on_halt(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_report_halt")
    (ctx.run_dir / "run_meta.json").write_text(
        json.dumps(
            {
                "homunculus_version": "0.1.0",
                "full_auto": True,
                "journey_milestones": {"g0_complete": True},
            }
        ),
        encoding="utf-8",
    )
    record_identical_failure(
        ctx,
        failed_stage="topic_coverage_audit",
        producer="understanding/gap_evaluations.json",
        reason="gap_evaluations.json pending",
    )
    record_identical_failure(
        ctx,
        failed_stage="topic_coverage_audit",
        producer="understanding/gap_evaluations.json",
        reason="gap_evaluations.json pending",
    )
    record_identical_failure(
        ctx,
        failed_stage="topic_coverage_audit",
        producer="understanding/gap_evaluations.json",
        reason="gap_evaluations.json pending",
    )
    report = write_execution_report(
        ctx,
        outcome="halted_identical_failure",
        halt_stage="topic_coverage_audit",
        root_cause="gap_evaluations.json pending after rewind",
        decisions=[{"severity": "major", "action": "pause"}],
    )
    assert report["outcome"] == "halted_identical_failure"
    assert report["g0"]["accepted_unreviewed"] is False
    assert report["research_next"]
    md = ctx.run_dir / REPORT_MD_REL
    assert md.is_file()
    text = md.read_text(encoding="utf-8")
    assert "halted_identical_failure" in text
    assert "topic_coverage_audit" in text


def test_execution_report_complete_ship_bar(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_report_ok")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    master = ctx.run_dir / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "master.wav").write_bytes(b"RIFF" + b"\x00" * 2000)
    pub = ctx.run_dir / "publish"
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "cover.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 100)
    (pub / "audio.mp3").write_bytes(b"ID3" + b"\x00" * 100)
    report = build_execution_report(ctx, outcome="complete")
    assert report["ship"]["master"]["present"] is True
    assert report["ship"]["cover"]["present"] is True


def test_opening_adjacency_keeps_orientation_suppresses_layup(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_open_adj")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "understanding").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "selection.json").write_text(
        json.dumps({"ordered_segment_ids": ["seg_001", "seg_002"]}),
        encoding="utf-8",
    )
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_001",
                "origin": "nugget_layup",
                "targets_segment_id": "seg_001",
                "placement": "before",
                "text": "What should we listen for next?",
            },
            {
                "line_id": "vo_preface_episode_orientation",
                "episode_orientation": True,
                "targets_segment_id": "seg_001",
                "placement": "before",
                "text": "Before the science, meet the founder.",
            },
        ]
    }
    (ctx.run_dir / "understanding" / "gap_report.json").write_text(
        json.dumps(gap), encoding="utf-8"
    )
    changed = suppress_opening_layup_when_orientation_owns_slot(ctx)
    assert "vo_layup_seg_001" in changed
    out = json.loads((ctx.run_dir / "understanding" / "gap_report.json").read_text(encoding="utf-8"))
    by_id = {ln["line_id"]: ln for ln in out["interviewer_lines"]}
    assert by_id["vo_layup_seg_001"].get("skipped_optional") is True
    assert by_id["vo_preface_episode_orientation"].get("skipped_optional") is not True


def test_native_orient_drops_orphan_opening_wav(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_open_omit")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    (ctx.run_dir / "understanding").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "vo_pickup").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "vo_pickup" / "vo_preface_opening.wav").write_bytes(b"RIFF" + b"\x00" * 64)
    gap = {
        "opening_orientation": {
            "omitted": True,
            "required": False,
            "omit_reason": "native_open_self_orients",
            "target_segment_id": "seg_002",
        },
        "interviewer_lines": [
            {
                "line_id": "vo_preface_opening",
                "targets_segment_id": "seg_002",
                "placement": "before",
                "text": "Welcome back.",
            }
        ],
    }
    (ctx.run_dir / "understanding" / "gap_report.json").write_text(
        json.dumps(gap), encoding="utf-8"
    )
    dropped = drop_orphan_opening_vo_when_native_orients(ctx)
    assert "vo_preface_opening" in dropped
    assert not (ctx.run_dir / "vo_pickup" / "vo_preface_opening.wav").is_file()
    out = json.loads((ctx.run_dir / "understanding" / "gap_report.json").read_text(encoding="utf-8"))
    by_id = {ln["line_id"]: ln for ln in out["interviewer_lines"]}
    assert by_id["vo_preface_opening"].get("skipped_optional") is True


def test_drop_late_intro_reset_keeps_open_drops_mid_arc_welcome(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_late_intro")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "understanding").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "segments").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "selection.json").write_text(
        json.dumps(
            {
                "ordered_segment_ids": [
                    "seg_002",
                    "seg_054",
                    "seg_003a",
                    "seg_003k",
                    "seg_067",
                ]
            }
        ),
        encoding="utf-8",
    )
    (ctx.run_dir / "segments" / "manifest.json").write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "segment_id": "seg_002",
                        "text": "Amr, we've got Mohan on the show today.",
                    },
                    {
                        "segment_id": "seg_054",
                        "text": "By that time the tumor has progressed.",
                    },
                    {
                        "segment_id": "seg_003a",
                        "text": "And what is OneCell.ai?",
                    },
                    {
                        "segment_id": "seg_003k",
                        "text": "let's welcome Mohan to the show.",
                    },
                    {
                        "segment_id": "seg_067",
                        "text": "Regulators, it's going to be more about the trials.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    from interview_mux.opening_adjacency_repair import drop_late_intro_reset_from_selection

    dropped = drop_late_intro_reset_from_selection(ctx)
    assert "seg_003a" in dropped and "seg_003k" in dropped
    assert "seg_002" not in dropped
    sel = json.loads((ctx.run_dir / "master" / "selection.json").read_text(encoding="utf-8"))
    assert sel["ordered_segment_ids"] == ["seg_002", "seg_054", "seg_067"]


def test_drop_late_intro_reset_keeps_opening_recut_cluster(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_open_recut")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "segments").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "selection.json").write_text(
        json.dumps(
            {
                "ordered_segment_ids": [
                    "seg_001c",
                    "seg_001d",
                    "seg_001k",
                    "seg_003",
                    "seg_070",
                ]
            }
        ),
        encoding="utf-8",
    )
    (ctx.run_dir / "segments" / "manifest.json").write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "segment_id": "seg_001c",
                        "text": "Amr, we've got Mohan on the show today.",
                    },
                    {
                        "segment_id": "seg_001d",
                        "text": "Who is Mohan? Mohan is a biotech entrepreneur.",
                    },
                    {
                        "segment_id": "seg_001k",
                        "text": "And what are you hoping to hear from Mohan today?",
                    },
                    {
                        "segment_id": "seg_003",
                        "text": "Thank you for inviting me here.",
                    },
                    {
                        "segment_id": "seg_070",
                        "text": "Regulators, it's going to be more about the trials.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    from interview_mux.opening_adjacency_repair import drop_late_intro_reset_from_selection

    dropped = drop_late_intro_reset_from_selection(ctx)
    assert dropped == []
    sel = json.loads((ctx.run_dir / "master" / "selection.json").read_text(encoding="utf-8"))
    assert sel["ordered_segment_ids"][0:3] == ["seg_001c", "seg_001d", "seg_001k"]


def test_drop_post_coda_reverse_jump_drops_early_tail(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_post_coda")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "segments").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "selection.json").write_text(
        json.dumps(
            {
                "ordered_segment_ids": [
                    "seg_003",
                    "seg_070",
                    "seg_073",
                    "seg_004",
                    "seg_005",
                    "seg_009",
                ]
            }
        ),
        encoding="utf-8",
    )
    (ctx.run_dir / "segments" / "manifest.json").write_text(
        json.dumps(
            {
                "segments": [
                    {"segment_id": "seg_003", "start_ms": 80_000, "end_ms": 90_000, "text": "open"},
                    {"segment_id": "seg_070", "start_ms": 3_193_240, "end_ms": 3_274_380, "text": "adoption"},
                    {"segment_id": "seg_073", "start_ms": 3_373_040, "end_ms": 3_502_960, "text": "regulators coda"},
                    {"segment_id": "seg_004", "start_ms": 165_300, "end_ms": 184_340, "text": "cancer is deadly"},
                    {"segment_id": "seg_005", "start_ms": 184_340, "end_ms": 263_860, "text": "historically"},
                    {"segment_id": "seg_009", "start_ms": 471_720, "end_ms": 524_600, "text": "liquid biopsy"},
                ]
            }
        ),
        encoding="utf-8",
    )
    from interview_mux.opening_adjacency_repair import drop_post_coda_reverse_jump_from_selection

    dropped = drop_post_coda_reverse_jump_from_selection(ctx)
    assert dropped == ["seg_004", "seg_005", "seg_009"]
    sel = json.loads((ctx.run_dir / "master" / "selection.json").read_text(encoding="utf-8"))
    assert sel["ordered_segment_ids"] == ["seg_003", "seg_070", "seg_073"]
    reasons = {
        str(r.get("segment_id")): r.get("reason")
        for r in (sel.get("excluded_segment_ids") or [])
        if isinstance(r, dict)
    }
    assert reasons["seg_004"] == "post_coda_reverse_jump"


def test_resume_producer_for_topic_coverage_missing_gaps(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_resume_prod")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    resume = resume_producer_for_block(
        ctx,
        consumer_stage="topic_coverage_audit",
        message="P0 spine incomplete: understanding/gap_evaluations.json missing",
    )
    assert resume == "missing_framing"


def test_mark_done_refuses_partial_llm_artifact(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_mark_partial")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    (ctx.run_dir / "understanding").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "understanding" / "speakers.json").write_text(
        json.dumps({"speakers": []}),
        encoding="utf-8",
    )
    ctx.mark_done("speaker_roles")
    assert not ctx.is_done("speaker_roles")
    mark_done_raw(ctx, "speaker_roles")
    assert not ctx.is_done("speaker_roles")


def test_source_profile_recipe_noisy_mono():
    recipe = source_profile_recipe("noisy_mono")
    assert recipe.get("diarization_retry") == 2
    assert recipe.get("preclean_aggressiveness") == "high"


def test_unattended_defaults_follow_full_auto_env(monkeypatch, tmp_path: Path):
    from interview_mux.stage_resilience import unattended_defaults_enabled

    monkeypatch.delenv("MUX_FULL_AUTO", raising=False)
    monkeypatch.delenv("MUX_PARTIAL_AUTO", raising=False)
    monkeypatch.delenv("MUX_RUN_MODE", raising=False)
    monkeypatch.delenv("INTERVIEW_MUX_AUTO_ACCEPT_GATES", raising=False)
    ctx = isolated_run_ctx(tmp_path, "exec_unattended_off")
    (ctx.run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    assert unattended_defaults_enabled(ctx) is False
    monkeypatch.setenv("MUX_FULL_AUTO", "1")
    assert unattended_defaults_enabled(ctx) is True
    monkeypatch.delenv("MUX_FULL_AUTO", raising=False)
    monkeypatch.setenv("MUX_PARTIAL_AUTO", "1")
    assert unattended_defaults_enabled(ctx) is True


def test_catalog_unattended_breakpoints_nonempty():
    import sys
    from pathlib import Path as P

    root = P(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    import catalog_unattended_breakpoints as cat

    catalog = cat.build_catalog()
    assert catalog["pipeline_stages"] == 72
    assert catalog["breakpoint_count"] > 50
    kinds = {row["kind"] for row in catalog["breakpoints"]}
    assert "completeness_gap_rule" in kinds
    assert "stage_contract" in kinds
    assert "driver_fail_key" in kinds
