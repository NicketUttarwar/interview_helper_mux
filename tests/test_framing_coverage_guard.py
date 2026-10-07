"""Tests for deterministic framing ranking guards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.framing_coverage_guard import enforce_framing_ranking, validate_framing_ranking
from interview_mux.gap_framing import build_gap_framing_plan, normalize_interviewer_line
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, minimal_gap_line, minimal_manifest, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_framing_guard", create=True)
    init_run_meta_for_test(run)
    run.write_json("segments/manifest.json", minimal_manifest("seg_001", "seg_002", "seg_003"), skip_handoff=True)
    lines = [
        normalize_interviewer_line(
            {
                "line_id": "vo_sum_1",
                "line_category": "segment_summary",
                "text": "Summary of setup.",
                "targets_segment_id": "seg_002",
                "replaces_source_segments": ["seg_001"],
            },
            eligible="spk_0",
            delivery="synthesize",
        )
    ]
    plan = build_gap_framing_plan(run, lines)
    run.path("understanding").mkdir(parents=True, exist_ok=True)
    run.path("master").mkdir(parents=True, exist_ok=True)
    run.path("understanding", "gap_framing_plan.json").write_text(
        json.dumps(plan) + "\n", encoding="utf-8"
    )
    run.path("understanding", "gap_report.json").write_text(
        json.dumps({"interviewer_lines": lines}) + "\n", encoding="utf-8"
    )
    run.path("master", "coverage_audit.json").write_text(
        json.dumps({"topic_segment_map": [{"topic_id": "origins", "segment_ids": ["seg_001"]}]})
        + "\n",
        encoding="utf-8",
    )
    return run


def test_validate_blocks_primary_impact_exclusion(ctx: RunContext) -> None:
    selection = {
        "ordered_segment_ids": ["seg_002"],
        "excluded_segment_ids": [{"segment_id": "seg_002", "reason": "covered_by_framing_vo"}],
    }
    issues = validate_framing_ranking(ctx, selection)
    assert any("never_exclude_primary_impact" in i for i in issues)


def test_enforce_warns_on_primary_lock(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    """Advisory since ISSUES 185: logged, not raised."""
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {"analysis": {"flow_hardening": {"strict_critical_stages": True}}},
    )
    selection = {
        "ordered_segment_ids": ["seg_003"],
        "excluded_segment_ids": [{"segment_id": "seg_002", "reason": "covered_by_framing_vo"}],
    }
    out = enforce_framing_ranking(ctx, selection)
    assert out["ordered_segment_ids"]


def test_blank_primary_impact_exclude_allowed(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank/unusable primary sources may stay excluded — never force dead air on-air."""
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {"analysis": {"flow_hardening": {"strict_critical_stages": True}}},
    )
    # Avoid unrelated ratio/topic survival trips for this blank-exempt case.
    ctx.path("master", "coverage_audit.json").write_text(
        json.dumps(
            {
                "topic_segment_map": [
                    {"topic_id": "origins", "segment_ids": ["seg_001", "seg_002", "seg_003"]}
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection = {
        "ordered_segment_ids": ["seg_001", "seg_003"],
        "excluded_segment_ids": [
            {"segment_id": "seg_002", "reason": "blank_or_unusable_answer_audio"}
        ],
    }
    issues = validate_framing_ranking(ctx, selection)
    assert not any("never_exclude_primary_impact" in i for i in issues)
    out = enforce_framing_ranking(ctx, selection)
    assert "seg_002" not in [str(s) for s in (out.get("ordered_segment_ids") or [])]
    excl = {
        str(r.get("segment_id"))
        for r in (out.get("excluded_segment_ids") or [])
        if isinstance(r, dict)
    }
    assert "seg_002" in excl


def test_enforce_framing_does_not_restore_media_ip_cta_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CTA / never-touch primaries stay excluded (exec_13198 seg_070 thrash)."""
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_framing_cta_primary", create=True)
    init_run_meta_for_test(ctx)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest("seg_010", "seg_070"),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_framing_plan.json",
        {
            "acts": [
                {
                    "act_id": "act_1",
                    "impact_blocks": [
                        {"source_segment_ids": ["seg_070"]},
                    ],
                }
            ]
        },
        skip_handoff=True,
    )
    # Stamp never-touch so restore path treats CTA as unenforceable.
    ctx.write_json(
        "mastering/media_ip_cta.json",
        {
            "version": 1,
            "never_touch_segment_ids": ["seg_070"],
            "dropped_segment_ids": ["seg_070"],
        },
        skip_handoff=True,
    )
    selection = {
        "ordered_segment_ids": ["seg_010"],
        "excluded_segment_ids": [
            {
                "segment_id": "seg_070",
                "reason": "media_ip_cta:empty/heavily degraded transcript",
            }
        ],
        "exclude_rationales": {
            "seg_070": "media_ip_cta:empty/heavily degraded transcript",
        },
    }
    issues = validate_framing_ranking(ctx, selection)
    assert not any("never_exclude_primary_impact" in i for i in issues)
    out = enforce_framing_ranking(ctx, selection)
    assert "seg_070" not in [str(s) for s in (out.get("ordered_segment_ids") or [])]
    assert "seg_010" in (out.get("ordered_segment_ids") or [])


def test_enforce_framing_does_not_restore_ghost_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hitch-stale impact ids absent from the live manifest must not re-enter order."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_framing_ghost_primary", create=True)
    init_run_meta_for_test(ctx)
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest("seg_010", "seg_039"),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_framing_plan.json",
        {
            "acts": [
                {
                    "act_id": "act_1",
                    "impact_blocks": [
                        {"source_segment_ids": ["seg_039", "seg_041"]},
                    ],
                }
            ]
        },
        skip_handoff=True,
    )
    selection = {
        "ordered_segment_ids": ["seg_010"],
        "excluded_segment_ids": [
            {"segment_id": "seg_039", "reason": "pacing"},
            {"segment_id": "seg_041", "reason": "pacing"},
        ],
    }
    issues = validate_framing_ranking(ctx, selection)
    assert not any("seg_041" in i and "never_exclude_primary_impact" in i for i in issues)
    out = enforce_framing_ranking(ctx, selection)
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or [])]
    assert "seg_041" not in ordered
    assert "seg_039" in ordered
