"""Refinement gate — full-auto activate|skip decisions; blacklist always wins."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import interview_mux.refinement_catalog as refinement_catalog
from interview_mux.config import merged_config
from interview_mux.refinement_gate import decide_pass
from interview_mux.run_context import RunContext
from interview_mux.refinement_gate import compute_input_hash
from run_fixtures import isolated_run_ctx, patch_executions_root, mark_done_raw, write_fixture_json


def _plant_snapshot(ctx: RunContext, pass_id: str, rel_paths: list[str]) -> str:
    digest = compute_input_hash(ctx, rel_paths)
    write_fixture_json(
        ctx,
        f"understanding/refinement_snapshots/{pass_id}/meta.json",
        {
            "paths": [{"rel": rel, "present": ctx.artifact_exists(rel)} for rel in rel_paths],
            "input_hash": digest,
        },
    )
    return digest


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return isolated_run_ctx(tmp_path, "exec_gate_test")


def _raw_write(ctx: RunContext, rel: str, data: dict[str, Any]) -> None:
    """Write JSON straight to disk, bypassing schema validation for test fixtures."""
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _patch_refinement_cfg(monkeypatch: pytest.MonkeyPatch, refinement_passes: dict[str, Any]) -> None:
    base = merged_config()
    cfg = {
        **base,
        "analysis": {**base["analysis"], "refinement_passes": refinement_passes},
    }
    monkeypatch.setattr(refinement_catalog, "merged_config", lambda: cfg)


def test_disabled_config_skips_everything(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_refinement_cfg(monkeypatch, {"enabled": False})
    decision = decide_pass(ctx, "gap_framing_recompose")
    assert decision["status"] == "skip"
    assert decision["reason_code"] == "disabled"


def test_blacklist_wins_over_whitelist(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    """A pass_id that is both blacklisted and whitelisted must be skipped — blacklist wins."""
    _patch_refinement_cfg(
        monkeypatch,
        {
            "enabled": True,
            "blacklist": {"stage_ids": ["ranking_refine"], "cfi_ids": [], "module_path_prefixes": []},
            "whitelist": {"pass_ids": ["ranking_refine"]},
        },
    )
    decision = decide_pass(ctx, "ranking_refine")
    assert decision["status"] == "skip"
    assert decision["gate"] == "blacklist"
    assert decision["reason_code"] == "blacklist"


def test_not_whitelisted_pass_is_skipped(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_refinement_cfg(
        monkeypatch,
        {
            "enabled": True,
            "blacklist": {"stage_ids": [], "cfi_ids": [], "module_path_prefixes": []},
            "whitelist": {"pass_ids": []},
        },
    )
    decision = decide_pass(ctx, "ranking_refine")
    assert decision["status"] == "skip"
    assert decision["reason_code"] == "not_whitelisted"


def test_missing_required_artifacts_skips(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_refinement_cfg(
        monkeypatch,
        {
            "enabled": True,
            "blacklist": {"stage_ids": [], "cfi_ids": [], "module_path_prefixes": []},
            "whitelist": {"pass_ids": ["narrative_arc_refine"]},
        },
    )
    decision = decide_pass(ctx, "narrative_arc_refine")
    assert decision["status"] == "skip"
    assert decision["reason_code"] == "missing_artifacts"


def test_activates_when_eligible_and_artifacts_present(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_refinement_cfg(
        monkeypatch,
        {
            "enabled": True,
            "blacklist": {"stage_ids": [], "cfi_ids": [], "module_path_prefixes": []},
            "whitelist": {"pass_ids": ["narrative_arc_refine"]},
        },
    )
    _raw_write(ctx, "master/narrative_plan.json", {"acts": []})
    _raw_write(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_1", "seg_2"]})
    ctx.write_json(
        "understanding/refinement_agenda.json",
        {
            "run_id": ctx.run_id,
            "schema_version": 1,
            "phase": "confirm",
            "tape_character": ["asymmetric_technical"],
            "eligible_classes": ["narrative"],
            "ineligible_classes": [],
            "succession_hints": [],
            "policy_pack_id": "asymmetric_technical",
            "prior_bias_applied": False,
        },
    )
    decision = decide_pass(ctx, "narrative_arc_refine")
    assert decision["status"] == "activate"
    assert decision["cfi_id"]
    assert decision["agenda_class"] == "narrative"


def test_agenda_ineligible_class_skips(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_refinement_cfg(
        monkeypatch,
        {
            "enabled": True,
            "blacklist": {"stage_ids": [], "cfi_ids": [], "module_path_prefixes": []},
            "whitelist": {"pass_ids": ["narrative_arc_refine"]},
        },
    )
    _raw_write(ctx, "master/narrative_plan.json", {"acts": []})
    _raw_write(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    ctx.write_json(
        "understanding/refinement_agenda.json",
        {
            "run_id": ctx.run_id,
            "schema_version": 1,
            "phase": "confirm",
            "tape_character": ["short_clean"],
            "eligible_classes": [],
            "ineligible_classes": [{"class_id": "narrative", "reason": "not_selected_for_tape"}],
            "succession_hints": [],
            "policy_pack_id": "short_clean",
            "prior_bias_applied": False,
        },
    )
    decision = decide_pass(ctx, "narrative_arc_refine")
    assert decision["status"] == "skip"
    assert decision["gate"] == "agenda"


def test_ledger_cap_skips_second_run(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.refinement_identity import cfi_for_pass
    from interview_mux.refinement_ledger import record_call

    _patch_refinement_cfg(
        monkeypatch,
        {
            "enabled": True,
            "blacklist": {"stage_ids": [], "cfi_ids": [], "module_path_prefixes": []},
            "whitelist": {"pass_ids": ["narrative_arc_refine"]},
        },
    )
    _raw_write(ctx, "master/narrative_plan.json", {"acts": []})
    _raw_write(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    cfi = cfi_for_pass("narrative_arc_refine")
    assert cfi is not None
    record_call(
        ctx,
        cfi_id=cfi.cfi_id,
        human_key=cfi.human_key,
        stage_id="narrative_arc_refine",
        pass_id="narrative_arc_refine",
        pass_index=2,
        kind="refinement",
        outcome="ok",
    )
    decision = decide_pass(ctx, "narrative_arc_refine")
    assert decision["status"] == "skip"
    assert decision["reason_code"] == "cap"


def test_decide_pass_always_returns_activate_or_skip(ctx: RunContext) -> None:
    """Full auto: decide_pass must never return a pending/pause status."""
    decision = decide_pass(ctx, "gap_framing_recompose")
    assert decision["status"] in ("activate", "skip")


def test_input_hash_skips_when_no_new_evidence_since_prior_snapshot(
    ctx: RunContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pass already done with an unchanged input snapshot must skip as no_new_evidence."""
    _patch_refinement_cfg(
        monkeypatch,
        {
            "enabled": True,
            "blacklist": {"stage_ids": [], "cfi_ids": [], "module_path_prefixes": []},
            "whitelist": {"pass_ids": ["narrative_arc_refine"]},
        },
    )
    req = ["master/narrative_plan.json", "master/selection.json"]
    _raw_write(ctx, "master/narrative_plan.json", {"acts": []})
    _raw_write(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    write_fixture_json(
        ctx,
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        stage_key="gap_framing_compose",
    )
    _plant_snapshot(ctx, "narrative_arc_refine", req)
    mark_done_raw(ctx, "narrative_arc_refine")

    decision = decide_pass(ctx, "narrative_arc_refine")

    assert decision["status"] == "skip"
    assert decision["gate"] == "input_hash"
    assert decision["reason_code"] == "no_new_evidence"


def test_input_hash_activates_again_when_inputs_change_after_prior_snapshot(
    ctx: RunContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changed required artifacts since the last snapshot must re-activate the pass."""
    _patch_refinement_cfg(
        monkeypatch,
        {
            "enabled": True,
            "blacklist": {"stage_ids": [], "cfi_ids": [], "module_path_prefixes": []},
            "whitelist": {"pass_ids": ["narrative_arc_refine"]},
        },
    )
    req = ["master/narrative_plan.json", "master/selection.json"]
    _raw_write(ctx, "master/narrative_plan.json", {"acts": []})
    _raw_write(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    write_fixture_json(
        ctx,
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        stage_key="gap_framing_compose",
    )
    _plant_snapshot(ctx, "narrative_arc_refine", req)
    mark_done_raw(ctx, "narrative_arc_refine")

    # New evidence: selection changed since the frozen snapshot.
    _raw_write(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_1", "seg_2"]})

    decision = decide_pass(ctx, "narrative_arc_refine")

    assert decision["status"] == "activate"
